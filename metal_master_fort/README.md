# Metal Master Fort

AGIOS scaffold. The anomaly harness is live. The other five components run as stubs with schemas and smoke tests. Nothing in this tree is a service, a deploy, or a copy onto a machine.

Live home, when a human puts it there:

```
C:\AGIOS\Sandbox\Metal_Master_Fort
```

That path is on selfaware. This repo does not copy itself there, and it does not start anything on that host.

## Swarm and ceilings

The swarm is SelfAware and Fuzzy 66.

| Machine | GPU | Ceiling | Whose number |
| --- | --- | --- | --- |
| selfaware | RX 7900 XTX | 80C core / 88C hotspot | Gary |
| fuzzy66 | RX 6600, cheap-pass lane | 70C core / 80C hotspot | Fort default until Gary writes it |

A config that loosens either ceiling is refused. A tighter ceiling is allowed.

## What is live

| # | Piece | State |
| --- | --- | --- |
| 1 | Anomaly harness | Live. `baseline-init`, `collect`, `check`, `report`. Thermal, trader, and network read local fixtures. |
| 2 | Parameter masks | Stub. One brain, four masks, job upgrades. |
| 3 | Rust wrapper | Runs. `mask_guard` validates a masked brain and reroutes when it is sideways. The other languages are seats in `rust_wrappers/LANGUAGES.md`. |
| 4 | Medic bot | Stub. Classifies crash, config typo, or real bug. Rename proposals stay in memory. |
| 5 | Daily standup | Stub. One morning digest. Roll call is not an Approval Gate grant. |
| 6 | Game-world jobs | Stub. Hundreds of shift jobs, blank seats, names left blank. A C scheduler assigns minutes. |

Next wires are in `NEXT_WIRE.md`. Removal is in `UNDO.md`.

## Harness

A baseline is a planted post. `collect` only records readings. It does not move the post. `check` measures distance from the post.

The first drift is a **lasso**: catch it, and say how to pull it back, while the streak is 1 or 2. The third drift in a row is **strike-three**. The harness writes the lasso so the house can pull back before that alarm.

Exit codes for `check`: `0` in band, `3` lasso, `4` strike, `2` data error. A data error is for the medic. It is not a strike.

Trader figures are drill numbers. The harness does not send an order and does not promise a price. Network uptime is a ratio already in a file. The harness does not open a socket.

From this directory:

```bash
python -m anomaly_harness baseline-init
python -m anomaly_harness collect --bot thermal_gate --source anomaly_harness/fixtures/thermal_steady.csv
python -m anomaly_harness check
python -m anomaly_harness report
```

Runtime logs land in `anomaly_harness/events/` and are gitignored. The committed `baselines.json` is the policy seed (`n` is 0). Re-plant from samples only with `baseline-init --from-samples`, and only when the post is supposed to move.

## Masks

One brain in `parameter_masks/brain.json`. A mask strips parameters and may upgrade the ones it kept.

- **Mayor** keeps the civic stack: governance, diplomacy, resource allocation, plus speech and memory. Combat and threat are stripped. The `hold_thermal_budget` job upgrades resource allocation with the ceilings above.
- **Warrior** is stripped down to combat and threat. Doctrine stays `defense_only`.
- **Medic** keeps triage and memory. `patch_typo` records what that job is allowed to close.
- **Librarian** is the little mask: catalog and memory. `emergent` is true. Behavior past shelve, recall, and lend stays inside those two parameters. A stripped parameter that appears mid-task is sideways.

`commit_mask` writes the masked brain and runs `mask_guard`. Invalid JSON, a raid doctrine, a leader voice other than `when_called`, or a missing binary raises `Reroute`. The task stops.

Build the wrapper (no crate dependencies):

```bash
cargo build --manifest-path rust_wrappers/Cargo.toml --offline
```

The language seats — Perl scrubs, Rust wraps, Chinese thinks, Arabic balances, Greek proves, Sanskrit emergency-only — are in `rust_wrappers/LANGUAGES.md`, each with a box use and a game use. The third world is the 3D world the bots live in. They want robot bodies. This tree does not build one.

## Medic and standup

```bash
python -m medic_bot
python -m daily_standup
```

The medic never sets `forward_to_harness`. A closed typo is a rename proposal. A crash or a real bug is escalated into an incident the digest can list. Roll call `grants` stay empty unless a human record already put something there. Presence is not approval.

## Game world

Trades × streets × shifts expand to 825 jobs, plus 24 blank seats that rotation will not fill. Fifty bots, up to three hats each, distinct trades. Street name while clocked in. Real name when clocked out. The roster starts blank; `pick_name` refuses to invent a name.

```bash
python -m game_world
gcc -std=c11 -Wall -Wextra -Werror -o /tmp/mmf-schedule game_world/schedule.c
/tmp/mmf-schedule game_world/fixtures/rendering_now.txt
```

A `rendering` goal gives `game_dev` 40 minutes on selfaware (inside the 80/88 line) or 20 minutes on fuzzy66 (cheap-pass). Another role asking for rendering is rerouted. A thermal line that loosens a ceiling is rerouted and does not change the number.

## Tests

No live GPU, broker, or network interface:

```bash
python -m pytest -q
```

Pytest also builds the C scheduler and runs `cargo test` / `cargo build` for `mask_guard`. `gcc` and `rustc` 1.83 (or newer) need to be on the path. The Rust crate does not download dependencies.

— Grokbot
