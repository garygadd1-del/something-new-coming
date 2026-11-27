Runtime logs land here when you run the CLI against this directory:

- `samples.jsonl` — one sample per line, written by `collect`
- `anomalies.jsonl` — lasso, strike, and release events, written by `check`
- `streaks.json` — consecutive-drift cursor

Those files are gitignored. `check` is safe to run twice: the cursor skips samples it already judged.

The baseline file stays next to `config.json`. Collect does not move it.
