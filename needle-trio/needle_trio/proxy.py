"""OpenAI- and Kobold-compatible proxy sketch.

Default is dry-run: the route is computed and returned, and nothing is sent
to a model. Live HTTP is a single POST to the configured local inference base
(default http://127.0.0.1:5001) and only when live mode is explicitly on.
This process never launches or stops KoboldCpp, Hermes, gpt-oss, or Bonsai.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .experts import load_experts
from .settings import Settings, assert_bind_allowed, assert_inference_allowed, settings_from_env
from .trio import decide, render_answer

MAX_BODY = 1_000_000


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "redirect refused", headers, fp)


def default_transport(url: str, payload: dict, timeout: float) -> dict:
    """POST JSON with content type and a local user agent. Redirects are refused."""
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "needle-trio/0.1"},
        method="POST",
    )
    opener = urllib.request.build_opener(_NoRedirect)
    with opener.open(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8", "replace")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw[:2000]}
    if not isinstance(parsed, dict):
        return {"raw": raw[:2000]}
    return parsed


def user_text(kind: str, body: dict) -> str:
    if kind == "kobold":
        prompt = body.get("prompt")
        if isinstance(prompt, str):
            return prompt
        text = body.get("text")
        return text if isinstance(text, str) else ""
    messages = body.get("messages") or []
    if not isinstance(messages, list):
        return ""
    for message in reversed(messages):
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, str):
                    parts.append(part)
                elif isinstance(part, dict) and part.get("type") == "text":
                    parts.append(str(part.get("text") or ""))
            return "\n".join(parts)
    return ""


def _openai_envelope(decision: dict, content: str) -> dict:
    return {
        "id": "needle-trio-%s" % decision["id"],
        "object": "chat.completion",
        "model": "needle-trio",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "needle_trio": decision,
    }


def _kobold_envelope(decision: dict, content: str) -> dict:
    return {"results": [{"text": content}], "needle_trio": decision}


def _forward_url(kind: str, base: str) -> str:
    root = base.rstrip("/")
    if kind == "kobold":
        return root + "/api/v1/generate"
    return root + "/v1/chat/completions"


def _forward_payload(kind: str, body: dict, decision: dict) -> dict:
    note = render_answer(decision)
    if kind == "kobold":
        prompt = user_text("kobold", body)
        payload = dict(body)
        payload["prompt"] = note + "\n\n" + prompt
        payload.setdefault("max_length", 256)
        payload.setdefault("temperature", 0)
        return payload
    messages = body.get("messages") if isinstance(body.get("messages"), list) else []
    payload = {
        "model": body.get("model") or "koboldcpp",
        "temperature": body.get("temperature", 0),
        "max_tokens": body.get("max_tokens", 256),
        "messages": [{"role": "system", "content": note}, *messages],
    }
    return payload


def fulfill(
    kind: str,
    body: dict,
    settings: Settings | None = None,
    transport=None,
    needles=None,
    index=None,
    experts=None,
) -> tuple[int, dict]:
    """Route one completion. Live POST happens only when settings.live is true and a model is required."""
    settings = settings or Settings()
    query = user_text(kind, body if isinstance(body, dict) else {})
    decision = decide(query, needles=needles, index=index, settings=settings, experts=experts)
    status = 200
    content = render_answer(decision)
    if settings.live and decision["needs_model"]:
        try:
            assert_inference_allowed(settings.inference_base, allow_remote=settings.allow_remote_hosts)
        except ValueError as exc:
            decision["inference"]["error"] = str(exc)
            content = render_answer(decision)
        else:
            url = _forward_url(kind, settings.inference_base)
            payload = _forward_payload(kind, body if isinstance(body, dict) else {}, decision)
            caller = transport or default_transport
            try:
                upstream = caller(url, payload, settings.request_timeout_s)
                if not isinstance(upstream, dict):
                    upstream = {"raw": str(upstream)[:500]}
            except Exception as exc:  # noqa: BLE001 — return the decision with the upstream error
                decision["inference"]["error"] = str(exc)[:300]
                decision["inference"]["url"] = url
                status = 502
                content = render_answer(decision)
            else:
                decision["dry_run"] = False
                decision["inference"]["called"] = True
                decision["inference"]["url"] = url
                content = _upstream_text(kind, upstream) or content
                decision["inference"]["upstream_id"] = upstream.get("id") if isinstance(upstream, dict) else None
    envelope = _kobold_envelope(decision, content) if kind == "kobold" else _openai_envelope(decision, content)
    return status, envelope


def _upstream_text(kind: str, upstream: dict) -> str:
    if kind == "kobold":
        results = upstream.get("results") or []
        if results and isinstance(results[0], dict):
            return str(results[0].get("text") or "")
        return ""
    choices = upstream.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return ""
    message = choices[0].get("message") or {}
    if isinstance(message, dict) and message.get("content"):
        return str(message["content"])
    if choices[0].get("text"):
        return str(choices[0]["text"])
    return ""


def models_payload(settings: Settings | None = None) -> dict:
    settings = settings or Settings()
    experts = load_experts(settings.experts_path, allow_remote=settings.allow_remote_hosts)
    data = [
        {
            "id": "needle-trio",
            "object": "model",
            "owned_by": "local",
            "inference_base": settings.inference_base,
            "dry_run_default": not settings.live,
        }
    ]
    for expert in experts:
        data.append(
            {
                "id": expert.name,
                "object": "model",
                "owned_by": "local",
                "port": expert.port,
                "role": expert.role,
                "depth": expert.depth,
                "dial_host": expert.dial_host,
            }
        )
    return {"object": "list", "data": data}


def health_payload(settings: Settings | None = None) -> dict:
    settings = settings or Settings()
    return {
        "ok": True,
        "dry_run": not settings.live,
        "inference_base": settings.inference_base,
        "listen": "%s:%s" % (settings.listen_host, settings.listen_port),
        "live": settings.live,
    }


def dispatch(
    method: str,
    path: str,
    body: dict | None = None,
    settings: Settings | None = None,
    transport=None,
    needles=None,
) -> tuple[int, dict]:
    settings = settings or Settings()
    if method == "GET" and path in {"/health", "/v1/health"}:
        return 200, health_payload(settings)
    if method == "GET" and path == "/v1/models":
        return 200, models_payload(settings)
    if method == "POST" and path == "/v1/chat/completions":
        return fulfill("openai", body or {}, settings=settings, transport=transport, needles=needles)
    if method == "POST" and path == "/api/v1/generate":
        return fulfill("kobold", body or {}, settings=settings, transport=transport, needles=needles)
    return 404, {"error": "not found", "path": path}


class TrioHandler(BaseHTTPRequestHandler):
    settings: Settings = Settings()
    transport = None
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        # Stdlib logs the request line to stderr. Keep the sketch quiet.
        return

    def _send(self, status: int, payload: dict) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self) -> dict | None:
        length = int(self.headers.get("Content-Length") or "0")
        if length > MAX_BODY:
            self._send(413, {"error": "body too large"})
            return None
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send(400, {"error": "invalid json"})
            return None
        if not isinstance(parsed, dict):
            self._send(400, {"error": "json object required"})
            return None
        return parsed

    def do_GET(self):
        status, payload = dispatch(self.command, self.path.split("?", 1)[0], settings=self.settings)
        self._send(status, payload)

    def do_POST(self):
        body = self._read_json()
        if body is None:
            return
        status, payload = dispatch(
            self.command,
            self.path.split("?", 1)[0],
            body,
            settings=self.settings,
            transport=self.transport,
        )
        self._send(status, payload)


def serve(settings: Settings | None = None, transport=None) -> ThreadingHTTPServer:
    settings = settings or settings_from_env()
    assert_bind_allowed(settings.listen_host, settings.listen_port)
    if settings.live:
        assert_inference_allowed(settings.inference_base, allow_remote=settings.allow_remote_hosts)
    TrioHandler.settings = settings
    TrioHandler.transport = transport
    server = ThreadingHTTPServer((settings.listen_host, settings.listen_port), TrioHandler)
    return server


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="needle-trio-proxy", description="Dry-run needle-trio proxy (local only).")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--live", action="store_true", help="POST to the local KoboldCpp base when a model is required.")
    args = parser.parse_args(argv)
    settings = settings_from_env()
    updates = {}
    if args.host:
        updates["listen_host"] = args.host
    if args.port:
        updates["listen_port"] = args.port
    if args.live:
        updates["live"] = True
    if updates:
        settings = settings.with_updates(**updates)
    try:
        server = serve(settings)
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}))
        return 2
    print(
        json.dumps(
            {
                "listen": "http://%s:%s" % (settings.listen_host, settings.listen_port),
                "dry_run": not settings.live,
                "inference_base": settings.inference_base,
            }
        )
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
