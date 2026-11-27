# UNDO

This scaffold does not install a service, a cron job, a credential, or a copy on selfaware. It does not change the Kalwi seats. It does not open a socket.

## This increment

Branch `cursor/fort-working-modules-8ca1` turns the five local modules on (masks, `mask_guard` coverage of those masks, medic, morning digest, C scheduler), records Gary's standing caps from 2026-11-25, and re-plants the harness policy seed as `throne_rx_7900_xtx`. It does not install a service, open a socket, or copy files onto a machine.

To undo only this increment:

1. Close its pull request without merging.
2. Delete the branch `cursor/fort-working-modules-8ca1`.

The scaffold removal steps below still apply to the whole tree.

To remove it:

1. Close the draft pull request without merging.
2. Delete the branch `cursor/metal-master-fort-39db`.
3. Or revert the commit that adds `metal_master_fort/` and `.github/workflows/metal-master-fort.yml`.

Local leftovers, if you ran the CLI or the tests in this tree:

- `metal_master_fort/anomaly_harness/events/*.jsonl`
- `metal_master_fort/anomaly_harness/events/streaks.json`
- `metal_master_fort/rust_wrappers/target/`
- `metal_master_fort/**/__pycache__/`

Those paths are gitignored. Deleting `metal_master_fort/` removes them.

`baseline-init` rewrites `baselines.json` only when you point it at that file. The committed seed is the policy post. If you re-planted it from samples and want the seed back, check the file out of git.

No network endpoint was opened by the harness, the medic, the digest, or the scheduler.

— Grokbot
