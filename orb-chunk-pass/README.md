# Orb-and-chunk pass

Portable plan for the AGIOS landfall chunk queue and the globe tile runner.
The Python CLI prints Godot arguments. It has no execute command. The Windows
runner dry-runs unless the operator passes `-Execute` or `--execute`.

**No-Limit Local** owns the live GPU queue. Run renders on that seat only.
This folder does not deploy anything and does not store secrets.

The pass order, chunk ids, and seat handoff are in [PASS_PLAN.md](PASS_PLAN.md).

## Layout

| Path | Role |
| --- | --- |
| `queues/queue_v2.json` | Fuzzy66 capture (`Render_Chunks_20261022`), byte-for-byte, including the UTF-8 BOM |
| `queues/queue_v2.normalized.json` | Same queue with camera, site, t0, and flags lifted out of `args` |
| `schema/legacy_queue.schema.json` | Schema for the captured array |
| `schema/chunk_queue.schema.json` | Schema for the normalized document (`execute` is always false) |
| `scripts/globe_runner.ps1` | Globe tile runner. Dry-run by default |
| `orb_chunk/` | Validator and planners |

Camera pass (`wide` / `close` / `mid`) is not Godot `--stage`. In this capture `--stage` is showcase index `5` (`render_stage`).

## Setup

Python 3.11 or newer.

```bash
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -v
```

From this directory:

```bash
python3 -m orb_chunk validate
python3 -m orb_chunk list --camera wide
python3 -m orb_chunk dry-run --order camera --id lf_s07_wide_t0
python3 -m orb_chunk preflight
python3 -m orb_chunk globe-dry-run
```

`dry-run` and `globe-dry-run` accept `--format json`. `--godot` only changes the name printed in `argv`.

Globe tiles that already exist can be omitted with a read-only scan:

```bash
python3 -m orb_chunk globe-dry-run --out-root /path/to/out/globe
```

## Globe runner

On the render seat, from this directory:

```powershell
powershell -NoProfile -File .\scripts\globe_runner.ps1
```

That prints the plan and returns. Godot starts only with the execute gate and an explicit binary:

```powershell
powershell -NoProfile -File .\scripts\globe_runner.ps1 -Execute -Godot C:\path\to\Godot.exe -Passes trace
```

`--execute` is the same gate. The recorded Fuzzy66 binary is documented in the script and in PASS_PLAN.md. It is not a default, and the script does not search `PATH`.

Single-seat work uses `-Passes trace,shade` (the default). Two-seat work is `selfaware` + `trace` and `throne` + `shade`. Do not run shade on both seats. Node `aidev` does not update the status markdown.
