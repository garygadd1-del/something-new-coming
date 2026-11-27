# Metal Master Fort

AGIOS scaffold. The anomaly harness is live and unchanged. The other five components are local modules with schemas and tests. Nothing in this tree is a service, a deploy, or a copy onto a machine.

Live home, when a human puts it there:

```
C:\AGIOS\Sandbox\Metal_Master_Fort
```

That path is on selfaware. This repo does not copy itself there, and it does not start anything on that host.

## Swarm and ceilings

### Hardware inventory

Owner-stated machines. A blank ceiling is **OPEN**: this tree does not invent one.

| Machine | GPU | Observed | Ceiling |
| --- | --- | --- | --- |
| Throne | RX 7900 XTX | 86 C core / 88 C hotspot / 80% load | OPEN |
| SelfAware | RX 9070 | 85 C core. Hotspot and load were not given. | OPEN |
| SelfAware | GTX 1650 | 80 C core. Hotspot and load were not given. | OPEN |
| Fuzzy 66 | RX 7900 GRE, plus older cards the owner did not name | Temps were not given. | OPEN |

A config that loosens a ceiling is refused. A tighter ceiling is allowed. An OPEN ceiling is not a number, so these modules do not enforce a new limit for that card.

Throne is in this inventory. The planted swarm list used by the harness, the masks, and the scheduler is still `selfaware` and `fuzzy66`. Whether Throne joins that list is OPEN.

### Planted harness seed

The live anomaly harness is unchanged. Its policy seed still reads:

| Seed key | Numbers | Authority recorded on the seed |
| --- | --- | --- |
| `selfaware_rx_7900_xtx` | 80 C core / 88 C hotspot | gary |
| `fuzzy66_rx_6600_cheap_pass` | 70 C core / 80 C hotspot | fort default until Gary writes it |

Those labels do not match the hardware inventory above. Re-planting the seed is OPEN. Until the owner says the post moved, the masks and the scheduler keep enforcing this planted pair: tighter than the seed is allowed, looser than the seed is refused.

## What is live

| # | Piece | State |
| --- | --- | --- |
| 1 | Anomaly harness | Live, unchanged. `baseline-init`, `collect`, `check`, `report`. Thermal, trader, and network read local fixtures. |
| 2 | Parameter masks | Runs. One brain, four masks, job upgrades. |
| 3 | Rust wrapper | Runs. `mask_guard` validates a masked brain, including the four masks, and reroutes when one is sideways. The other languages are seats in `rust_wrappers/LANGUAGES.md`. |
| 4 | Medic bot | Runs. Classifies a crash, a config typo, or a real bug from a report or a local log. Rename proposals stay in memory. |
| 5 | Daily standup | Runs. One morning digest from local fixture files. Roll call is not an Approval Gate grant. |
| 6 | Game-world jobs | Runs. Hundreds of shift jobs, blank seats, names left blank. A C scheduler assigns minutes, including minutes on blank seat ids. |

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

- **Mayor** keeps the civic stack: governance, diplomacy, resource allocation, plus speech and memory. Combat and threat are stripped. The `hold_thermal_budget` job upgrades resource allocation with the planted seed above, not with a new hardware ceiling.
- **Warrior** is stripped down to combat and threat. Doctrine stays `defense_only`.
- **Medic** keeps triage and memory. `patch_typo` records what that job is allowed to close.
- **Librarian** is the little mask: catalog and memory. `emergent` is true. Behavior past shelve, recall, and lend stays inside those two parameters. A stripped parameter that appears mid-task is sideways.

`commit_mask` writes the masked brain and runs `mask_guard`. Invalid JSON, a raid doctrine, a leader voice other than `when_called`, a stripped parameter on one of the four masks, a thermal number above the planted seed, or a missing binary raises `Reroute`. The task stops.

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

The medic reads a JSON report or a local log / traceback. It never sets `forward_to_harness`. A closed typo is a rename proposal held in memory (`RenameLedger`). Nothing writes that rename to disk. A crash or a real bug is escalated into an incident the digest can list. The morning command reads `daily_standup/fixtures/outbox`. Roll call `grants` stay empty unless a human record already put something there. Presence is not approval.

## Game world

Trades × streets × shifts expand to 825 jobs, plus 24 blank seats that rotation will not fill. Fifty bots, up to three hats each, distinct trades. Street name while clocked in. Real name when clocked out. The roster starts blank; `pick_name` refuses to invent a name.

```bash
python -m game_world
gcc -std=c11 -Wall -Wextra -Werror -o /tmp/mmf-schedule game_world/schedule.c
/tmp/mmf-schedule game_world/fixtures/rendering_now.txt
```

A `rendering` goal gives `game_dev` 40 minutes on selfaware (inside the planted 80/88 seed) or 20 minutes on fuzzy66 (cheap-pass 70/80 seed). Another role asking for rendering is rerouted. A thermal line that loosens a planted ceiling is rerouted and does not change the number. A tighter line is kept.

A `seat` line assigns minutes to a blank job id (`blank.001` and the rest). The line has no name field. An extra token is refused, and the seat stays unnamed. The minute cap in `schedule.c` (`BLANK_MINUTES_CAP`, 45) is an EXAMPLE until the owner sets a blank-seat budget.

## Tests

No live GPU, broker, or network interface:

```bash
python -m pytest -q
```

Pytest also builds the C scheduler and runs `cargo test` / `cargo build` for `mask_guard`. `gcc` and `rustc` 1.83 (or newer) need to be on the path. The Rust crate does not download dependencies.

— Grokbot
