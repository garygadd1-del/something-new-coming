"""Triage the bundled fixtures and print the ticket classes."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from medic_bot.triage import triage

ROOT = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    del argv
    for path in sorted((ROOT / "fixtures").glob("*.json")):
        ticket = triage(json.loads(path.read_text(encoding="utf-8")))
        print(f"{path.name}: {ticket['class']} escalate={ticket['escalate']} closed={ticket['closed_here']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
