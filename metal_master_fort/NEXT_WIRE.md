# Next wire

The harness and the five modules run on local files. Nothing here is a service, a socket, or a copy onto a machine.

## 1. Anomaly harness — live

The policy seed is Gary's standing caps from 2026-11-25. `throne_rx_7900_xtx` is 86 C core / 88 C hotspot / 80% load. `selfaware_rx_9070` is 85 C core. `selfaware_gtx_1650` is 80 C core. Hotspot and load on those two SelfAware cards are OPEN. The RX 7900 GRE has no ceiling in the seed.

`thermal_gate` watches the SelfAware RX 9070 core. Its hotspot warn is OPEN. `fuzzy66_thermal` is the GRE, and both of its warns are OPEN. The planted swarm list is still `selfaware`, `fuzzy66`. Throne is not on it.

Next wire is a file drop, still on the same shapes:

- Thermal: a sensor log the owner chooses, CSV or JSON. No second host is contacted from this tree.
- Trader: a ledger export the scout already wrote. Still no orders from this harness, and still no price promise.
- Network: an uptime ratio the network master already computed. Do not add a ping or a scan.

Re-plant baselines only when the owner says the post moved. Collect must not chase a fault into the baseline.

A bad sample fails the whole `check` batch and does not advance the cursor. That is deliberate.

## 2. Parameter masks — runs

The task runner should call `apply_mask`, then `commit_mask` with `mask_guard`, before every job. `Reroute` stops the task. Send the reason to the medic. Do not catch it and continue.

Little masks (librarian, `emergent: true`) are allowed to be unspecified inside the parameters they kept. They are not allowed to grow a stripped parameter. The wrapper checks that.

`hold_thermal_budget` records the three standing caps. It does not record a GRE ceiling.

## 3. Rust wrapper — runs

`mask_guard` accepts the four masks this tree produces and reroutes a sideways one: stripped parameter, raid doctrine, leader voice other than `when_called`, job the mask does not assign, or a thermal number above a standing cap. A tighter number is allowed. A hotspot or load on the 9070 or the 1650 is refused because those fields are OPEN. A GRE ceiling is refused.

Keep the crate dependency-free. Perl is the next language to actually execute, in front of the wrapper, on local text only. Chinese, Arabic, and Greek stay seats until a task needs them. Sanskrit stays emergency-only.

## 4. Medic — runs

Feed it a JSON report, a local log, a traceback, or harness `HarnessError` text. `apply_proposal` and `RenameLedger` are in memory only. Writing a renamed config to disk waits for a human yes. Escalations append to the standup incident log when a caller asks `log_incident` to. Tickets stay `forward_to_harness: false`.

## 5. Daily standup — runs

`python -m daily_standup` reads `daily_standup/fixtures/outbox`, one card file per bot, plus the roll call and the incident log. Roll call does not write Approval Gate grants. An empty `grants` list is the honest state. A real outbox directory on a host is a later wire. This tree only reads the fixtures.

## 6. Game-world jobs — runs

Bots call `pick_name` for themselves. The scaffold keeps the roster blank until they do. The C scheduler reads a goals file a bot can edit. Rendering gives `game_dev` a thermal slot inside the standing caps. A fuzzy66 thermal line is refused. A `seat` line assigns caller-supplied minutes to a blank id and refuses a name. There is no 3D client and no robot body in this tree.

## OPEN — needs the owner

1. Whether Throne joins the planted swarm list. The list is still `selfaware`, `fuzzy66`. The XTX cap names Throne. A bot line may not use that host.
2. SelfAware RX 9070 hotspot and load.
3. SelfAware GTX 1650 hotspot and load.
4. Fuzzy 66 RX 7900 GRE core, hotspot, load, and ceiling.
5. Whether a second harness bot should watch the GTX 1650. `thermal_gate` watches the RX 9070 core only.
6. Blank-seat minute cap. `BLANK_MINUTES_CAP` 45 is an EXAMPLE, the longest role slot already in the scheduler. The owner has not set a blank-seat budget.
7. Any mask name beyond mayor, warrior, medic, and librarian.
8. Any job name beyond the jobs already in the mask files and `game_world/jobs_spec.json`.
9. Real bot names. `pick_name` refuses to invent one. The roster stays blank.
10. Whether a rename proposal may be written to a config file. It stays in memory until a human yes.
11. The real morning-outbox directories on the hosts. The digest reads only the fixture outbox.
