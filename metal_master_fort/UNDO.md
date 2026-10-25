# UNDO

This scaffold does not install a service, a cron job, a credential, or a copy on selfaware. It does not change the Kalwi seats. It does not open a socket.

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
