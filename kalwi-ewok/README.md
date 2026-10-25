# Kalwi Docker-Ewok

Short-lived isolated agent containers for the AGIOS hive.

A seat is one container, one task, then exit. The launcher’s default is a dry-run. A real seat exists only after `--execute`, and that run removes the container it created. Nothing here is a production deploy, a payment, or a GPU worker.

Source: Gary’s verbal spec, 2026-10-24. Approval Gate item #6 granted Go.

These seats are isolation shells for hive work. They do not walk human doors (domain, bank, legal). Render work that needs Godot or a GPU goes to **No-Limit Local / Game Dev**. This package only scaffolds the isolation.

## Lifecycle

```
spawn
  -> private Linux netns (loopback only)
  -> container as uid 1001, read-only root, caps dropped
  -> entrypoint runs the baked skill stub
  -> exit 0
  -> remove that container
  -> delete that named netns, when one was created
```

Host logs land in `kalwi-ewok/runs/`. That directory is gitignored and excluded from the image. It is not a container volume. The seat itself does not keep processes or volumes.

## Threat model

**Goals**

- One seat cannot see another seat’s processes. It is a separate container with a pid limit, dropped capabilities, and `no-new-privileges`.
- One seat cannot open a host or bridge interface. Its network namespace has loopback only.
- One seat cannot write the image or the host tree. The root filesystem is read-only, there is no volume mount, and `/tmp` is a small tmpfs that dies with the container.
- Skill stubs are baked at build time. The host launcher, role files, and tests are not copied into the image.
- Resource caps come from the role file (CPU, memory, pids) and are applied on the run command.
- Kalwi-Render does not request a GPU. Real Godot or GPU work is handed off to No-Limit Local / Game Dev.

**What this holds against**

- A casual invocation. Dry-run is the default, so looking at a role does not create a container or a netns.
- A role file that asks for a GPU, a volume, host networking, a cloud API host, or a secret-shaped value. Loading that file fails.
- An image tag that points at a registry (`/` in the name) or `:latest`. The launcher refuses it and passes `--pull=never`.
- Credentials in the build context. `.dockerignore` excludes `.env`, keys, pem files, and `.npmrc`. The Dockerfile has no `ARG` or `ENV` for a secret.

**Residual risk**

- Containers share the host kernel. This is a hive seat boundary, not a VM boundary against a hostile kernel exploit.
- Whoever can already talk to the host container socket can start privileged containers on their own. This launcher does not mount that socket into the seat.
- Alpine still includes busybox. The stub hooks do not call it for the network, and `--network=none` gives those applets no route. We keep the shell because the entrypoint is a script.
- `podman-netns` needs `CAP_SYS_ADMIN` to create a named netns. Rootless isolation is `docker` or `podman-none`, both of which use `--network=none`.
- `--execute` with a 30s cap will `docker rm -f` / `podman rm -f` **only the container name this run created**, and `ip netns delete` **only the netns this run created**. It does not prune the host.

## Roles

| Role | CPU | Memory | PIDs | Network | GPU |
| --- | --- | --- | --- | --- | --- |
| `kalwi-render` | 0.50 | 256 MB | 64 | none | off; hand off to No-Limit Local / Game Dev |
| `kalwi-ledger` | 0.25 | 128 MB | 32 | none | off |
| `kalwi-scout` | 0.25 | 128 MB | 32 | none | off |

- **Kalwi-Render** runs the `render-stub` hook and exits. It does not seize a GPU.
- **Kalwi-Ledger** is a work-memory placeholder (the same idea as HVC / FZC notes). It does not send money and it does not promise a price.
- **Kalwi-Scout** stays off the network. A house-LAN scout would be a separate human decision. This package does not scan.

Role files live in `roles/`. The loader accepts only those three filenames.

## Hard gates

- **No prod deploy.** There is no push, no registry tag, and no deploy flag.
- **No money and no sends.** `KALWI_MONEY_SENDS` must be `0`. The ledger hook does not talk to a bank.
- **No secrets baked into images.** Do not put API keys, tokens, or cloud LLM credentials in the Dockerfile, role env, or skill hooks. The seat allowlist has no key field. Host environment variables are not copied into the container.
- **No GPU.** `KALWI_GPU` must be `off`. The run command has no device reservation.
- **No leftover seat by default.** No volumes, `restart` is `no`, and cleanup targets only this run’s container and netns.

## Dry-run

From this directory:

```bash
python -m kalwi_ewok --role kalwi-render
python -m kalwi_ewok --role kalwi-ledger
python -m kalwi_ewok --role kalwi-scout
```

Each command prints the container argv, the cleanup argv, and the log path it would write. It does not create a container, a netns, or a log file. An environment variable cannot turn a dry-run into a real run. Only `--execute` does that.

Other dry-run views:

```bash
python -m kalwi_ewok --role kalwi-scout --runtime podman-none
python -m kalwi_ewok --role kalwi-ledger --runtime podman-netns
```

## Real run

Build the local image first. The tag must stay `kalwi-ewok:local` (or another single-name `kalwi-ewok:<tag>` that is not `latest`).

```bash
docker build -t kalwi-ewok:local .
python -m kalwi_ewok --role kalwi-render --execute
```

Rootless Podman uses the same private netns as Docker, without a named `ip netns`:

```bash
podman build -t kalwi-ewok:local .
python -m kalwi_ewok --role kalwi-scout --runtime podman-none --execute
```

A named netns is optional and needs privileges (`CAP_SYS_ADMIN`). The launcher creates `ewok-<run id>`, joins it with Podman, and deletes that name on exit:

```bash
python -m kalwi_ewok --role kalwi-ledger --runtime podman-netns --execute
```

Logs are written under `runs/`. Cleanup removes the one container even when the task exits nonzero. A container the runtime already removed (`--rm`) is treated as gone. Any other cleanup failure exits 4 so a leftover seat is visible.

`compose.yaml` is a sketch of the same limits (non-root, read-only, `network_mode: none`, caps dropped, no ports, no volumes, no GPU). `docker compose up` starts nothing until a profile is selected. Prefer the launcher: it is what captures logs and removes the seat.

## Tests

No Docker daemon is required:

```bash
python -m unittest discover -s tests -t . -v
```

The tests load the three role files, reject GPU / volume / secret / prod / money mistakes, and run the launcher in dry-run with a fake runtime. `--execute` is covered against that fake runtime, including cleanup when the run fails.

## Layout

```
kalwi-ewok/
  Dockerfile
  compose.yaml
  agent/entrypoint.sh
  skills/                  # baked into the image
  roles/                   # host-side contracts
  kalwi_ewok/              # launcher (not copied into the image)
  tests/
```
