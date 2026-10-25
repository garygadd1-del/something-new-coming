"""Print roster size and job count. The C scheduler is a separate binary."""

from __future__ import annotations

import sys

from game_world.world import expand_jobs, load_spec, make_roster


def main(argv: list[str] | None = None) -> int:
    del argv
    spec = load_spec()
    jobs = expand_jobs(spec)
    roster = make_roster(spec)
    blanks = sum(1 for job in jobs if job["blank"])
    print(f"jobs={len(jobs)} blanks={blanks} bots={len(roster)} max_hats={spec['max_hats']}")
    print("scheduler: game_world/schedule.c")
    return 0


if __name__ == "__main__":
    sys.exit(main())
