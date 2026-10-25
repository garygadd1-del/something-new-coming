# Next wire

The harness runs on local files. The other five pieces run as stubs: schemas, loaders, and smoke tests. Nothing here is a service.

## 1. Anomaly harness — live

Next wire is a file drop, still on the same shapes:

- Thermal: a sensor log on selfaware, CSV or JSON, for the RX 7900 XTX. Fuzzy 66 drops its own cheap-pass log. No second host.
- Trader: a ledger export the scout already wrote. Still no orders from this harness, and still no price promise.
- Network: an uptime ratio the network master already computed. Do not add a ping or a scan.

Re-plant baselines only when Gary says the post moved. Collect must not chase a fault into the baseline.

A bad sample fails the whole `check` batch and does not advance the cursor. That is deliberate.

## 2. Parameter masks — stub

The task runner should call `apply_mask`, then `commit_mask` with `mask_guard`, before every job. `Reroute` stops the task. Send the reason to the medic. Do not catch it and continue.

Little masks (librarian, `emergent: true`) are allowed to be unspecified inside the parameters they kept. They are not allowed to grow a stripped parameter.

## 3. Rust wrapper — runs

Keep the crate dependency-free. Perl is the next language to actually execute, in front of the wrapper, on local text only. Chinese, Arabic, and Greek stay seats until a task needs them. Sanskrit stays emergency-only.

## 4. Medic — stub

Feed it harness `HarnessError` text and local exit records. `apply_proposal` is in memory only. Writing a renamed config to disk waits for a human yes. Escalations append to the standup incident log. Tickets stay `forward_to_harness: false`.

## 5. Daily standup — stub

A morning command reads yesterday's cards from each bot's outbox directory. Roll call does not write Approval Gate grants. An empty `grants` list is the honest state.

## 6. Game-world jobs — stub

Bots call `pick_name` for themselves. The scaffold keeps the roster blank until they do. The C scheduler reads a goals file a bot can edit. Rendering gives `game_dev` a thermal slot inside the house ceilings. There is no 3D client and no robot body in this tree.
