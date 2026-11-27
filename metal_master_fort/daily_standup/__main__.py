"""Print one morning digest from the local fixture files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from daily_standup.digest import build_digest, load_cards, load_incidents, render_markdown

ROOT = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="daily_standup")
    parser.add_argument("--cards", type=Path, default=ROOT / "fixtures" / "outbox")
    parser.add_argument("--roll", type=Path, default=ROOT / "fixtures" / "roll_call.json")
    parser.add_argument("--incidents", type=Path, default=ROOT / "fixtures" / "incidents.jsonl")
    args = parser.parse_args(argv)
    cards = load_cards(args.cards)
    roll_call = json.loads(args.roll.read_text(encoding="utf-8"))
    incidents = load_incidents(args.incidents)
    digest = build_digest(cards, roll_call, incidents)
    sys.stdout.write(render_markdown(digest))
    return 0


if __name__ == "__main__":
    sys.exit(main())
