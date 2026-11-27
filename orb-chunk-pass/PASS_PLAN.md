# Orb-and-chunk pass plan

No-Limit Local owns execution on the render hardware. This document is the pass order and the handoff. The tools in this folder print planned Godot arguments. They do not start a render, and this repo has no production deploy.

The chunk capture is Fuzzy66 `Render_Chunks_20261022` `queue_v2.json`: 54 landfall jobs. The globe tile runner shipped beside that queue is a separate pass (`scripts/globe_runner.ps1`).

## Chunk contract

Every chunk job shares this contract:

| Field | Value |
| --- | --- |
| Project | `C:\AGIOS\Sandbox\Render_Chunks_20261022\src\landfall` |
| Scene | `res://scenes/showcase.tscn` |
| Resolution | `1280x720` |
| Godot `--stage` (`render_stage`) | `5` (showcase index, not the camera pass) |
| `--seq` | `240` |
| `--fps` | `12` (240/12 = 20 seconds of frames per chunk) |
| Frames | 54 × 240 = 12960 |
| Sites, in queue order | `s07`, `s101`, `s11`, `s23`, `s42`, `s77` (`s101` sorts before `s11`) |
| `t0` | `0`, `20`, `40` |

`t0` steps by 20, the same length as `seq/fps`. Treat each chunk as the next 20 seconds of its plan, and confirm that reading on the render seat before relying on it.

Camera pass:

| Stage | Zoom | Follow | Jobs |
| --- | --- | --- | --- |
| wide | 0.6 | 0 | 18 |
| close | 1.6 | 1 | 18 |
| mid | 1.0 | 1 | 18 |

Plans, one per site, under `C:\AGIOS\Sandbox\Render_Chunks_20261022\plans\`:

- `plan_s07.json`
- `plan_s101.json`
- `plan_s11.json`
- `plan_s23.json`
- `plan_s42.json`
- `plan_s77.json`

Output directory for a job is `C:/AGIOS/Sandbox/Render_Chunks_20261022/out/v2/<id>`. `mk` and `--outdir` are that same directory. Planned argv:

```text
godot --path <project> --resolution 1280x720 res://scenes/showcase.tscn -- --plan=<plan> --stage=5 --seq=240 --fps=12 --t0=<t0> --zoom=<zoom> --follow=<follow> --outdir=<id dir>
```

The chunk CLI does not add `--windowed`. The globe runner does. No-Limit Local adds seat-local window flags if the landfall scene needs them.

## Stage wide

Orb-wide camera. Zoom `0.6`, follow `0`. Eighteen jobs. Run this stage first.

### t0=0

- `lf_s07_wide_t0`
- `lf_s101_wide_t0`
- `lf_s11_wide_t0`
- `lf_s23_wide_t0`
- `lf_s42_wide_t0`
- `lf_s77_wide_t0`

### t0=20

- `lf_s07_wide_t20`
- `lf_s101_wide_t20`
- `lf_s11_wide_t20`
- `lf_s23_wide_t20`
- `lf_s42_wide_t20`
- `lf_s77_wide_t20`

### t0=40

- `lf_s07_wide_t40`
- `lf_s101_wide_t40`
- `lf_s11_wide_t40`
- `lf_s23_wide_t40`
- `lf_s42_wide_t40`
- `lf_s77_wide_t40`

## Stage close

Follow camera. Zoom `1.6`, follow `1`. Eighteen jobs. Run after wide.

### t0=0

- `lf_s07_close_t0`
- `lf_s101_close_t0`
- `lf_s11_close_t0`
- `lf_s23_close_t0`
- `lf_s42_close_t0`
- `lf_s77_close_t0`

### t0=20

- `lf_s07_close_t20`
- `lf_s101_close_t20`
- `lf_s11_close_t20`
- `lf_s23_close_t20`
- `lf_s42_close_t20`
- `lf_s77_close_t20`

### t0=40

- `lf_s07_close_t40`
- `lf_s101_close_t40`
- `lf_s11_close_t40`
- `lf_s23_close_t40`
- `lf_s42_close_t40`
- `lf_s77_close_t40`

## Stage mid

Follow camera. Zoom `1.0`, follow `1`. Eighteen jobs. Run after close.

### t0=0

- `lf_s07_mid_t0`
- `lf_s101_mid_t0`
- `lf_s11_mid_t0`
- `lf_s23_mid_t0`
- `lf_s42_mid_t0`
- `lf_s77_mid_t0`

### t0=20

- `lf_s07_mid_t20`
- `lf_s101_mid_t20`
- `lf_s11_mid_t20`
- `lf_s23_mid_t20`
- `lf_s42_mid_t20`
- `lf_s77_mid_t20`

### t0=40

- `lf_s07_mid_t40`
- `lf_s101_mid_t40`
- `lf_s11_mid_t40`
- `lf_s23_mid_t40`
- `lf_s42_mid_t40`
- `lf_s77_mid_t40`

## Order

Run **wide**, then **close**, then **mid**. Inside a stage, run `t0` 0, then 20, then 40. Inside a `t0`, keep the site order `s07`, `s101`, `s11`, `s23`, `s42`, `s77`.

```bash
python3 -m orb_chunk dry-run --order camera
```

The captured file groups by time slice instead: for each `t0`, wide then close then mid. The seventh job in the file is `lf_s07_close_t0`. Print that order with `--order file` when a slice should be finished at every camera before the offset advances. Both orders cover the same 54 ids.

```bash
python3 -m orb_chunk dry-run --order file
```

## Globe tiles

Separate project and scene from the landfall chunks.

| Field | Value |
| --- | --- |
| Project | `C:\AGIOS\Sandbox\Render_Chunks_20261022\src\ara_body` |
| Scene | `res://refrender/globe_shot.tscn` |
| Resolution | `1024x1024` |
| Tile ids | `A01` through `Z26` (26 rows × 26 columns = 676 tiles) |
| Passes | `trace`, then `shade` |
| PNG | `<Root>\out\globe\<pass>\tile_<id>.png` |
| Process shape | one Godot process per row per pass (52 starts when every PNG is missing) |
| Timeout | 900000 ms (15 minutes) per process, then that child is stopped |
| Thermal fallback | hotspot stop 88°C, core stop 80°C, resume when hotspot is below 78°C, cap 3 hours |
| Priority | BelowNormal |
| Status file | `C:\AGIOS\Ara_Brain\reports\globe_render_queue_2026-10-23.md` (column 4 only, and never when the node is `aidev`) |

676 tiles × 2 passes = 1352 PNGs when both passes are empty. The 3 hour cap is an execute-time stop from `gpu_policy.ps1` (`max_hours`) or the fallback. Dry-run lists the whole grid and does not apply the cap. A full missing grid can hit the cap before Z26.

The runner passes `--tiles=` as one argument (the row's ids joined with commas). Paths in this capture have no spaces.

Flags, in order:

```text
--path <project> --windowed --resolution 1024x1024 res://refrender/globe_shot.tscn -- --worker --no-auto --no-link --pass=<trace|shade> --tiles=<row ids> --outdir=<out/globe/pass>
```

`python3 -m orb_chunk globe-dry-run` assumes every PNG is missing. `scripts/globe_runner.ps1` with no switch checks the seat's `out\globe` tree and skips a row/pass whose PNGs are already there. `globe-dry-run --out-root` does the same scan without starting Godot.

Seat split: one machine may run `trace,shade`. Two machines split the work as `selfaware` + `trace` and `throne` + `shade`. Shade on both seats double-renders the same tiles.

## Handoff for No-Limit Local

You own the live Godot queue. Fuzzy66 is the source of this `queue_v2.json` capture. This repository holds the schema, the dry-run, and this plan. It does not take the GPU.

1. Confirm this seat is the render owner and no other campaign is on the GPU. The globe runner waits while another Godot process has a window that is not Project Manager. It does not stop that other process. The only process it stops is its own child, and only after the 15 minute timeout.
2. Dry-run the chunk list (`validate`, `list`, `dry-run --order camera`) and the globe plan before any `-Execute`.
3. Confirm the six `plan_s*.json` files and both Godot projects (`src\landfall`, `src\ara_body`) on disk. Those files are not in this capture.
4. Pass the Godot binary explicitly. Fuzzy66 recorded `C:\Users\garyg\Tools\Godot_4.7.2\Godot_v4.7.2-stable_win64.exe`. The runner does not use that path unless you pass `-Godot`.
5. Choose the seat split before launching. Default `trace,shade` is the single-seat plan.
6. Thermal policy is `C:\AGIOS\Sandbox\RoomTemp\gpu_policy.ps1` when that file exists (`hotspot_stop_C`, `core_stop_C`, `max_hours`). Otherwise the fallback above is used. Temps come from `<Root>\tools\gputemp.ps1`. If temps stay unreadable, the execute path logs that and proceeds. Put the temp script on the seat when you want the pause to work.
7. Chunk outputs stay under `out\v2\<id>`. Globe PNGs stay under `out\globe\<pass>\`. The status markdown is the globe tile table, not the chunk queue. Chunk ids such as `lf_s07_wide_t0` are not rows in that markdown.
8. Node `aidev` does not write the status markdown. Other nodes write only the status cell (pipe column 4) of matching tile rows.
9. Start globe work only with `-Execute` or `--execute`, on this seat, after the checks above. There is no chunk execute command. Landfall jobs are started by you, from the printed argv, when you choose.

Exit codes on the globe runner: `0` finished or dry-run, `2` Godot exited in under 5 seconds, `3` the hour cap stopped the run.

## Preflight

```bash
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -v
python3 -m orb_chunk validate
python3 -m orb_chunk preflight
python3 -m orb_chunk dry-run --order camera --id lf_s07_wide_t0
python3 -m orb_chunk globe-dry-run
```

```powershell
powershell -NoProfile -File .\scripts\globe_runner.ps1
```

## Out of scope

- Starting Godot, or any GPU render, from this tree.
- Production deploy, CI renderers, or a second writer of the live queue.
- Secrets. Paths in the capture are seat paths, not credentials.
- The landfall plan JSON files, `gpu_policy.ps1`, `gputemp.ps1`, and the Godot projects. They stay on the render seat.
