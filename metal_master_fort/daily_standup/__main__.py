"""Print the bundled morning digest."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from daily_standup.digest import build_digest, load_incidents, render_markdown

ROOT = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    del argv
    cards = json.loads((ROOT / "fixtures" / "cards.json").read_text(encoding="utf-8"))
    roll_call = json.loads((ROOT / "fixtures" / "roll_call.json").read_text(encoding="utf-8"))
    incidents = load_incidents(ROOT / "fixtures" / "incidents.jsonl")
    digest = build_digest(cards, roll_call, incidents)
    sys.stdout.write(render_markdown(digest))
    return 0


if __name__ == "__main__":
    sys.exit(main())
