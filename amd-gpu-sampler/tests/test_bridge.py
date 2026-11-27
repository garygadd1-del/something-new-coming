import json
import urllib.error
import urllib.request

from amd_gpu_sampler.bridge import BRIDGE_HOST, derived_body, start_bridge


def _state():
    return {
        "level": "watch",
        "reporting": "paused",
        "gpu": {"util_pct": 10, "temp_c": 70},
        "cpu": {"util_pct": 20},
        "ram": {"avail_mb": 8192},
    }


def test_derived_body_is_bounded():
    body = derived_body(_state())
    assert body["source"] == "inner_world"
    assert body["heat"] == 0.5
    assert body["reporting"] == "paused"
    assert 0 <= body["distress"] <= 1
    assert BRIDGE_HOST == "127.0.0.1"


def test_bridge_serves_only_loopback():
    server = start_bridge(_state, 0)
    host, port = server.server_address
    try:
        assert host == "127.0.0.1"
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/body/derived", timeout=2) as response:
            body = json.load(response)
        assert body["source"] == "inner_world"
        assert body["reporting"] == "paused"
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/other", timeout=2)
        except urllib.error.HTTPError as exc:
            assert exc.code == 404
        else:
            raise AssertionError("expected 404")
    finally:
        server.shutdown()
        server.server_close()
