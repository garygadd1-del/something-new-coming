"""Optional read-only loopback bridge for Godot's existing derived-body schema.

The listener binds to 127.0.0.1 and serves one GET path. It is off unless a port
is configured. It does not accept another host.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from amd_gpu_sampler.safety import SafetyError

BRIDGE_HOST = "127.0.0.1"
_LEVELS = ("ok", "watch", "warn", "critical")


def _clip(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def derived_body(state: dict) -> dict:
    level = _LEVELS.index(state["level"]) if state.get("level") in _LEVELS else 0
    temp = state["gpu"].get("temp_c")
    junction = float(temp) if isinstance(temp, (int, float)) and not isinstance(temp, bool) else 50.0
    exertion = max(float(state["gpu"]["util_pct"]), float(state["cpu"]["util_pct"])) / 100.0
    return {
        "heat": _clip((junction - 40.0) / 60.0),
        "exertion": _clip(exertion),
        "memory_pressure": _clip(1.0 - float(state["ram"]["avail_mb"]) / 16384.0),
        "fatigue": _clip(exertion * 0.5),
        "distress": level / 3.0,
        "calm": 1.0 - level / 3.0,
        "stale": False,
        "source": "inner_world",
        "reporting": state.get("reporting", "active"),
    }


def start_bridge(get_state, port: int) -> ThreadingHTTPServer:
    """Serve `/api/body/derived` on 127.0.0.1. Port 0 lets the OS pick a free port."""
    if isinstance(port, bool) or not isinstance(port, int) or port < 0 or port > 65535:
        raise SafetyError("bridge port is out of range")

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            return None

        def do_GET(self):  # noqa: N802 - stdlib handler name
            path = self.path.split("?", 1)[0]
            state = get_state()
            if path != "/api/body/derived" or not state:
                body = b""
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                self.wfile.write(body)
                return
            payload = json.dumps(derived_body(state)).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer((BRIDGE_HOST, port), Handler)
    bound_host = server.server_address[0]
    if bound_host not in (BRIDGE_HOST, "127.0.0.1"):
        server.server_close()
        raise SafetyError("bridge left the loopback interface")
    thread = threading.Thread(target=server.serve_forever, name="inner-world-bridge", daemon=True)
    thread.start()
    return server
