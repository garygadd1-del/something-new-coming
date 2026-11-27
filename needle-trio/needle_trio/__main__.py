"""CLI: print one dry-run decision as JSON.

    python -m needle_trio "what port is hermes on"

``--live`` is accepted only as an explicit request. The CLI still refuses
non-loopback and cloud inference bases. It never starts a model process.
"""

from __future__ import annotations

import argparse
import json
import sys

from .index import NeedleIndex
from .proxy import fulfill
from .settings import assert_inference_allowed, settings_from_env


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="needle-trio")
    parser.add_argument("query", nargs="*", help="Query text. Dry-run unless --live.")
    parser.add_argument("--live", action="store_true", help="Allow one POST to the local inference base.")
    parser.add_argument("--index", default=None, help="Read-only SQLite FTS needle index.")
    args = parser.parse_args(argv)
    settings = settings_from_env()
    updates = {}
    if args.live:
        updates["live"] = True
    if args.index:
        updates["index_path"] = args.index
    if updates:
        settings = settings.with_updates(**updates)
    if settings.live:
        try:
            assert_inference_allowed(settings.inference_base, allow_remote=settings.allow_remote_hosts)
        except ValueError as exc:
            print(json.dumps({"error": str(exc)}, indent=2))
            return 2
    query = " ".join(args.query)
    index = NeedleIndex(settings.index_path) if settings.index_path else None
    status, payload = fulfill(
        "openai",
        {"messages": [{"role": "user", "content": query}]},
        settings=settings,
        index=index,
    )
    json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0 if status < 500 else 1


if __name__ == "__main__":
    raise SystemExit(main())
