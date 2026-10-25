"""House rules that have to stay true in the tree itself."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {"target", "__pycache__", ".pytest_cache", ".git"}


def _needles():
    return (
        "".join(("192.168.0.", "123")),
        "".join(("AI", "Dev")),
        "".join(("son", "'s PC")),
        "".join(("son", "'s pc")),
    )


def test_swarm_names_are_not_joined_by_anything_else():
    text = (ROOT / "house_policy.py").read_text(encoding="utf-8")
    assert 'SELF_AWARE = "selfaware"' in text
    assert 'FUZZY66 = "fuzzy66"' in text
    assert "SWARM = (SELF_AWARE, FUZZY66)" in text


def test_collectors_do_not_import_a_client():
    for relative in (
        "anomaly_harness/collectors/thermal.py",
        "anomaly_harness/collectors/trader.py",
        "anomaly_harness/collectors/network.py",
        "anomaly_harness/harness.py",
        "game_world/schedule.c",
    ):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "import socket" not in text
        assert "urllib" not in text
        assert "requests" not in text


def test_tree_does_not_name_a_forbidden_host():
    needles = tuple(needle.casefold() for needle in _needles())
    offenders = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in SKIP for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8").casefold()
        except (UnicodeDecodeError, OSError):
            continue
        for needle in needles:
            if needle in text:
                offenders.append(f"{path.relative_to(ROOT)} contains a forbidden host token")
    assert offenders == []
