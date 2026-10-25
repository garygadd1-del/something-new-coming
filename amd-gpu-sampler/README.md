# AMD / Windows GPU health sampler

Read-only health feed for Ara's inner world on Gary's Fuzzy66 and selfaware machines. The Python sampler watches Windows performance counters and an existing thermal file. The PowerShell poller writes `gpu_state_<machine>.json` for GPU_Pipes.

This package does not deploy anything. It does not call AMD control APIs, load a model, or open key files.

## What it will not do

- No AMD set / fan / clock / power calls.
- No model load and no GPU compute.
- No reads of key, token, secret, or certificate files.
- No network except the documented loopback paths below.
- No deletion. `STOP` and `sampler.pid` are renamed when the rules below say so. Their bytes stay on disk. Other files in the work directory are left alone.

Loopback only:

- Signed messages go to Godot through `ara_pipe.send(..., via="udp")`. The client is documented as UDP `127.0.0.1:18840`. This package does not choose a host and does not read the signing key. The feed stays off until the running Godot process started after `godot_handler_installed.json`.
- `--bridge-port` serves `GET /api/body/derived` on `127.0.0.1` only. It is off unless you set a port.

`typeperf` is started with a fixed argument list and `shell` is not used.

## Layout

| Path | Role |
| --- | --- |
| `amd_gpu_sampler/` | Sampler, hash chain, schemas |
| `poller.ps1` | GPU util / VRAM / temp writer |
| `sampler_config.example.json` | Gary's 78C pause rule as config |
| `tests/` | Mocked counters. No GPU required |

## Run the sampler on Windows

Python 3.11 or newer. From this directory:

```powershell
python -m amd_gpu_sampler --dir C:\AGIOS\inner_world --config .\sampler_config.example.json
```

`--dir` is required for a live run. The sampler creates `log\` under that directory and replaces `state.json` about once a second. Do not keep notes in `state.json`.

Useful flags:

```powershell
python -m amd_gpu_sampler --dir C:\AGIOS\inner_world --no-pipe
python -m amd_gpu_sampler --verify-log C:\AGIOS\inner_world\log
```

`--no-pipe` keeps the local snapshot and the hash chain, and does not push to Godot.

The thermal file defaults to `C:\AGIOS\Ara_Brain\state\ara_thermal.json`. The signed-pipe directory defaults to `C:\AGIOS\ara_body\link`. Override both in the config file. A thermal document looks like:

```json
{
  "t": 1761360000.0,
  "gpu": {"edge_c": 71.0, "junction_c": 86.0, "power_w": 140.0, "vram_total_mb": 24560},
  "cpu": {"cores_c": [68.0, 74.0, 77.5]}
}
```

`vram_total_mb_fallback` (24560) is used only when that file has no total. It is not a live probe.

Live counters need Windows `typeperf`. `python -m amd_gpu_sampler` on any other OS exits with code 2. `--verify-log` works anywhere.

## Run the poller on Windows

PowerShell 5.1. LibreHardwareMonitor supplies temperatures when its WMI provider is running. Missing temperatures are reported as unavailable. They do not invent a number.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\poller.ps1 `
  -Machine selfaware `
  -Role "traces+spectral" `
  -OutDir C:\AGIOS\GPU_Pipes `
  -Interval 5 `
  -ThermalPauseC 78 `
  -ThermalResumeC 75
```

Fuzzy66 uses the same command with `-Machine fuzzy66`. `-Once` writes a single snapshot and exits. An optional `lock_<machine>.json` may contain a `job` string. The poller only copies that field.

The file `gpu_state_<machine>.json` uses schema `gpu_state/1`: `util_pct`, `vram_used_gb`, `vram_used_mb`, `temp_c`, `core_temp_c`, `reporting_paused`, and the pause threshold. GPU_Pipes should skip a snapshot whose `reporting_paused` is true.

Utilization is the higher of the summed 3D engines and the summed compute engines, capped at 100. The Python sampler reports per-engine maxima instead. Both numbers are in their own files.

## STOP file

Sampler work directory, and the poller's `-OutDir`, use the same idea.

- While the process is running, creating a regular file named `STOP` ends the loop.
- That `STOP` file is left in place so the request stays visible.
- On the next start, a leftover `STOP` is renamed to `STOP.<unix>.done`. The bytes are kept.
- A symlink or directory named `STOP` is refused.
- The sampler writes `sampler.pid` while it runs and renames it to `sampler.pid.stopped` on exit.
- If `sampler.pid` names a process that is still alive, a second sampler does not start and does not rewrite that file.
- End the process from Task Manager only when you cannot create `STOP`.

## Thermal pause (78C)

Gary's pause rule is configuration, not a kill.

| Setting | Default | Meaning |
| --- | --- | --- |
| `thermal_pause_celsius` / `-ThermalPauseC` | 78 | Pause outbound reporting at or above this core temperature |
| `thermal_resume_celsius` / `-ThermalResumeC` | 75 | Resume only at or below this temperature |
| `thermal_max_age_s` | 30 | Ignore undated or older thermal-file readings for the pause decision |
| `thermal_sensors` | `gpu_edge_c`, `cpu_core_c` | Pause inputs |

Junction / hotspot is still recorded. It can raise the watch / warn / critical ladder (85C / 90C / 100C on junction). It is not a default pause input, because a 7900-class junction runs hotter than the core and would pause a healthy card. Add `gpu_junction_c` to `thermal_sensors`, or pass `-IncludeJunction` on the poller, only when that is really what you want.

What "pause" means:

- The sampler stops pushing inner-world messages to Godot.
- `state.json` and `gpu_state_<machine>.json` keep updating, with `reporting: "paused"` or `reporting_paused: true`, so the reason stays visible.
- The local hash chain keeps an audit record, including `thermal_pause` and `thermal_resume`.
- The process keeps running. It does not stop a workload, change a fan, or exit because of temperature.
- A stale thermal file does not start a new pause. If reporting is already paused and the sensor disappears, it stays paused until a fresh reading cools to the resume line.

A paused snapshot can still show level `ok` or `watch`. The pause flag is separate from the stall ladder.

## Hash chain

Each day file is `log/health_YYYYMMDD.jsonl`. Records carry `seq`, `ts`, `unix`, `type`, `data`, `prev`, and `hash`.

```text
hash = sha256(previous_hash + "|" + canonical_json_without_hash)
```

Canonical JSON is UTF-8, sorted keys, and compact separators. Sequence 1 anchors at 64 zero hex digits. The sequence continues across midnight. The sampler refuses to append when the existing log does not verify, and it leaves that file untouched.

```powershell
python -m amd_gpu_sampler --verify-log C:\AGIOS\inner_world\log
```

A good log prints `ok records=N head=<sha256>`. A bad log prints the mismatch and exits 1.

## Schemas

- Sampler snapshot: `inner_world/1` in `state.json`. This is the original inner-world picture plus `reporting`, `pause`, and the configured thresholds under `sampler`.
- Poller snapshot: `gpu_state/1`.

`amd_gpu_sampler.schema` checks both. `build_gpu_state` is the tested specification the poller follows.

## Tests

No AMD GPU and no Windows host are required. Counters are mocked.

```powershell
python -m pip install pytest
python -m pytest
```

CI runs that same command from this directory on Ubuntu.

## Not in this change

This is a draft package for review. It does not merge, does not copy itself onto Fuzzy66 or selfaware, and does not start a scheduled task.
