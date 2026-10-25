"""Proxy sketch: dry-run by default, local KoboldCpp only when live is on."""

from __future__ import annotations

import json
import socket
import sys
import threading
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from needle_trio.proxy import dispatch, fulfill, serve  # noqa: E402
from needle_trio.settings import Settings, assert_bind_allowed  # noqa: E402
from needle_trio.trio import Needle  # noqa: E402
from needle_trio.trinary import T, Claim  # noqa: E402


def _boom(*_args, **_kwargs):
    raise AssertionError("live HTTP should not run")


def _wide_needles():
    fact = "survey papers disagree on the listen port"
    needles = []
    for depth, confidence in (("shallow", 0.95), ("mid", 0.40), ("deep", 0.15)):
        needles.append(
            Needle(
                depth,
                0.8,
                confidence=confidence,
                claim=Claim(fact, T, confidence, depth + ".txt"),
            )
        )
    return needles


class ProxyTests(unittest.TestCase):
    def test_health_and_models_are_local(self):
        status, health = dispatch("GET", "/health")
        self.assertEqual(status, 200)
        self.assertTrue(health["ok"])
        self.assertTrue(health["dry_run"])
        self.assertEqual(health["inference_base"], "http://127.0.0.1:5001")
        status, models = dispatch("GET", "/v1/models")
        self.assertEqual(status, 200)
        names = {item["id"] for item in models["data"]}
        self.assertIn("needle-trio", names)
        self.assertIn("hermes14b", names)
        hermes = next(item for item in models["data"] if item["id"] == "hermes14b")
        self.assertEqual(hermes["port"], 5021)
        self.assertEqual(hermes["dial_host"], "127.0.0.1")

    def test_dry_run_chat_and_kobold_do_not_call_transport(self):
        status, chat = dispatch(
            "POST",
            "/v1/chat/completions",
            {"messages": [{"role": "user", "content": "hello"}]},
            transport=_boom,
        )
        self.assertEqual(status, 200)
        self.assertIn("choices", chat)
        self.assertTrue(chat["needle_trio"]["dry_run"])
        self.assertFalse(chat["needle_trio"]["inference"]["called"])
        self.assertIn("Dry-run", chat["choices"][0]["message"]["content"])

        status, kobold = dispatch(
            "POST",
            "/api/v1/generate",
            {"prompt": "hello"},
            transport=_boom,
        )
        self.assertEqual(status, 200)
        self.assertIn("results", kobold)
        self.assertTrue(kobold["needle_trio"]["dry_run"])

    def test_live_posts_only_to_loopback_kobold(self):
        calls = []

        def transport(url, payload, timeout):
            calls.append({"url": url, "payload": payload, "timeout": timeout})
            return {"id": "local-1", "choices": [{"message": {"content": "ok"}}]}

        settings = Settings(live=True)
        status, payload = fulfill(
            "openai",
            {"messages": [{"role": "user", "content": "implement a python function to add integers"}]},
            settings=settings,
            transport=transport,
        )
        self.assertEqual(status, 200)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["url"], "http://127.0.0.1:5001/v1/chat/completions")
        self.assertNotIn("Authorization", json.dumps(calls[0]["payload"]))
        self.assertEqual(payload["choices"][0]["message"]["content"], "ok")
        self.assertFalse(payload["needle_trio"]["dry_run"])
        self.assertTrue(payload["needle_trio"]["inference"]["called"])

    def test_live_argue_does_not_call_the_model(self):
        settings = Settings(live=True)
        status, payload = fulfill(
            "openai",
            {"messages": [{"role": "user", "content": "survey papers and cite sources in the literature"}]},
            settings=settings,
            transport=_boom,
            needles=_wide_needles(),
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["needle_trio"]["action"], "argue")
        self.assertFalse(payload["needle_trio"]["inference"]["called"])
        self.assertTrue(payload["needle_trio"]["dry_run"])

    def test_live_refuses_a_cloud_base_without_calling_it(self):
        settings = Settings(live=True, inference_base="https://api.openai.com/v1", allow_remote_hosts=True)
        status, payload = fulfill(
            "openai",
            {"messages": [{"role": "user", "content": "implement a python function to add integers"}]},
            settings=settings,
            transport=_boom,
        )
        self.assertEqual(status, 200)
        self.assertIn("cloud", payload["needle_trio"]["inference"]["error"])
        self.assertFalse(payload["needle_trio"]["inference"]["called"])

    def test_upstream_failure_is_a_502_and_does_not_invent_text(self):
        def transport(url, payload, timeout):
            raise TimeoutError("kobold down")

        settings = Settings(live=True)
        status, payload = fulfill(
            "kobold",
            {"prompt": "rewrite this sentence into a shorter line"},
            settings=settings,
            transport=transport,
        )
        self.assertEqual(status, 502)
        self.assertIn("kobold down", payload["needle_trio"]["inference"]["error"])
        self.assertFalse(payload["needle_trio"]["inference"]["called"])
        self.assertIn("/api/v1/generate", payload["needle_trio"]["inference"]["url"])

    def test_protected_ports_are_not_bound(self):
        with self.assertRaises(ValueError):
            assert_bind_allowed("127.0.0.1", 5001)
        with self.assertRaises(ValueError):
            assert_bind_allowed("0.0.0.0", 5031)
        assert_bind_allowed("127.0.0.1", 5031)
        with self.assertRaises(ValueError):
            serve(Settings(listen_port=5021))

    def test_http_server_dry_run_round_trip(self):
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        settings = Settings(listen_host="127.0.0.1", listen_port=port, live=False)
        server = serve(settings)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urllib.request.urlopen("http://127.0.0.1:%s/health" % port, timeout=2) as response:
                health = json.loads(response.read().decode("utf-8"))
            self.assertTrue(health["dry_run"])
            body = json.dumps({"messages": [{"role": "user", "content": "hello"}]}).encode("utf-8")
            request = urllib.request.Request(
                "http://127.0.0.1:%s/v1/chat/completions" % port,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(payload["needle_trio"]["suggested_expert"]["name"], "bonsai8b")
            self.assertFalse(payload["needle_trio"]["inference"]["called"])
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
