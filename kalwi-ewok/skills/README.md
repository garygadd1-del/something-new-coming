# Baked skill stubs

These hooks ship inside the Kalwi Ewok image. Each one is a no-op: it exits 0 and starts no child process.

| Role | Hook | What the stub is for |
| --- | --- | --- |
| `kalwi-render` | `hooks/kalwi-render/00-stub.sh` | Render seat placeholder. Godot and GPU work hand off to No-Limit Local / Game Dev. |
| `kalwi-ledger` | `hooks/kalwi-ledger/00-stub.sh` | Work-memory placeholder. It does not send money or set a price. |
| `kalwi-scout` | `hooks/kalwi-scout/00-stub.sh` | Observation placeholder. It does not open a socket or scan a network. |

The entrypoint runs the hook for `KALWI_ROLE` and then exits. A hook in this package stays a stub. Real render, ledger, or scout behavior belongs in a later human-gated change, outside this image.
