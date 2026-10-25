# needle-trio

Dry-run **coder-trio needle** router for the AGIOS hive. Three local coder agents each cast one needle. Kleene **T / U / F** gates accept / hold / reject. Nothing in this package launches a model, opens a secret, or calls a cloud LLM API.

The verbal rules below are Gary's coder-trio definition from **2026-10-24 ~11:33 PM EDT**. Pointer search and the T/U/F claim merge are adapted from the staged needle router and `trinary.py` (2026-10-20 / 2026-10-21). The older Needle-MOE port ladder is not the decision function.

## Rules

Each coder owns one **trinary depth**. Depth is ordered like Kleene's F < U < T, and it is not itself a truth value:

| Depth | Rank | Kleene parallel | Coder | Default expert |
| --- | --- | --- | --- | --- |
| shallow | 0 | F | `coder-shallow` | Bonsai 8B |
| mid | 1 | U | `coder-mid` | gpt-oss 20B |
| deep | 2 | T | `coder-deep` | Hermes 14B |

1. **Thickness** of each needle is a number in **[0, 1]**. Empty search is 0. A shallow window is a thin slice; a deep window is wider.
2. **Merge coder results only past a complexity threshold** (default `0.50`). Below it, one depth answers and the other two are recorded, not blended.
3. **Each coder votes a confidence in [0, 1].** If `max - min` is at least `0.35`, the action is **argue** and the gate is HOLD. Nothing is committed.
4. **T against F** on the same statement merges to **U** (unknown). That is a hold, not a silent overwrite. A claim cannot be T without a source.
5. **Cross-checked facts** (at least two sourced coders agree on T or on F, and that statement is not also disputed) raise confidence to at least `0.90` when the result is actually committed. A disputed statement is a hold, not a high-confidence fact.

Precedence when those fire together:

1. Wide confidence spread → argue, no commit (even if the facts agree).
2. Else a T/F contradiction → hold, truth U, no commit, and no model call.
3. Else if complexity is under the threshold → do not merge; keep the single depth for that category.
4. Else merge the shared statement.
5. If that commit is cross-checked → high confidence.

`decide()` never performs HTTP. The proxy calls a model only when live mode is explicitly on **and** the action still needs a completion. Argue and hold do not call a model.

## Ports

Inference target for the live sketch is local KoboldCpp:

`http://127.0.0.1:5001`

This process does **not** bind `5001`. The proxy listens on `127.0.0.1:5031` unless you pick another free loopback port.

| Role | Port | Dial host in this package | Notes |
| --- | --- | --- | --- |
| KoboldCpp inference target | 5001 | 127.0.0.1 | Live POST target. Never bound here. Never started or stopped here. |
| Proxy listen (this sketch) | 5031 | 127.0.0.1 | Dry-run unless `--live` or `NEEDLE_TRIO_LIVE=1`. |
| Hermes 14B, deep coder | 5021 | 127.0.0.1 | Configured host in the Fuzzy66 file is `192.168.0.193`. Dial stays loopback unless remote hosts are explicitly allowed. Persona / deep reasoning. Keywords: why, explain, reason, plan, feel, philosophy. |
| gpt-oss 20B, mid coder | 5032 | 127.0.0.1 | Research and sourced summaries. Keywords: research, source, compare, summarize, history, facts. |
| Ternary-Bonsai 8B, shallow coder | 5033 | 127.0.0.1 | Small talk, short transforms, classify. Keywords: hi, hello, rewrite, shorten, classify, list. |

Protected bind list (the proxy refuses these): `5001`, `5002`, `5011`, `5021`, `5032`, `5033`, `18830`, `18850`, `18860`, `18871`, `27300`, `27301`.

Keyword match picks the suggested expert. If nothing matches, the expert follows the selected depth. Suggestion is not a launch instruction. Live forwarding goes to the KoboldCpp base on port **5001**, not to the expert ports and not to `192.168.0.193`.

## Layout

```
needle-trio/
  needle_trio/trinary.py    Kleene T/U/F and Claim.merge
  needle_trio/trio.py       three needles, votes, merge, argue
  needle_trio/index.py      read-only SQLite FTS pointers
  needle_trio/experts.py    Fuzzy66 trio loader
  needle_trio/proxy.py      OpenAI / Kobold sketch
  config/experts.fuzzy66.json
  tests/
```

Model paths in the JSON are labels copied from the staged config. This package does not open those files and does not vendor weights. The staged `koboldcpp.exe` path is intentionally not stored here.

## Run the tests

From this directory, stdlib `unittest` only:

```bash
cd needle-trio
python -m unittest discover -s tests -v
```

The tests cover the Kleene table, `Claim.merge` contradictions becoming U, and a mocked needle path (injected votes plus a temporary FTS index). They do not load a GGUF and they do not call port 5001.

## Dry-run a decision

```bash
python -m needle_trio "hello"
python -m needle_trio "survey papers and cite sources in the literature"
```

Stdout is one JSON chat envelope. `needle_trio.dry_run` is true and `inference.called` is false.

Build a local index only when you mean to (the router never writes one):

```python
from needle_trio.index import init_index, NeedleIndex
from needle_trio.trio import decide

init_index("needle.sqlite", [{"path": "notes/ports.md", "title": "ports", "body": "proxy listen port 5031"}])
print(decide("what port does the proxy listen on", index=NeedleIndex("needle.sqlite")))
```

Search reads the SQLite body. It does not open the path named in a pointer, so an index row cannot be used to pull a secret file.

## Proxy sketch

```bash
python -m needle_trio.proxy
# listens on http://127.0.0.1:5031
# GET /health
# GET /v1/models
# POST /v1/chat/completions
# POST /api/v1/generate
```

Live mode is off unless you pass `--live` or set `NEEDLE_TRIO_LIVE=1`. Live mode POSTs to `NEEDLE_TRIO_INFERENCE_BASE` (default `http://127.0.0.1:5001`) with no `Authorization` header. Redirects are refused. Cloud hosts such as `api.openai.com` are refused even if remote dialing is on.

| Variable | Meaning |
| --- | --- |
| `NEEDLE_TRIO_LIVE` | `1` turns on live POST. Default off. |
| `NEEDLE_TRIO_INFERENCE_BASE` | Default `http://127.0.0.1:5001`. |
| `NEEDLE_TRIO_ALLOW_REMOTE` | `1` allows a non-loopback inference host. Cloud LLM hosts stay blocked. |
| `NEEDLE_TRIO_MERGE_THRESHOLD` | Default `0.50`. |
| `NEEDLE_TRIO_WIDE_SPREAD` | Default `0.35`. |
| `NEEDLE_TRIO_LISTEN_HOST` / `NEEDLE_TRIO_LISTEN_PORT` | Proxy bind. Loopback only. Default `127.0.0.1:5031`. |
| `NEEDLE_TRIO_INDEX` | Optional read-only SQLite FTS path. |
| `NEEDLE_TRIO_EXPERTS` | Optional JSON path. Default is `config/experts.fuzzy66.json`. |
| `NEEDLE_TRIO_LOG_DIR` | Optional JSONL directory. Logs votes and actions, not query text or snippets. Default off. |

No environment variable in this package is an API key. `NEEDLE_BONSAI_KEY` is not read.

## Hard rules

- **Never launch, stop, or unload** KoboldCpp, Hermes, gpt-oss, Bonsai, or any other model process.
- **Never open secrets** (`.env`, key files, credential stores) and never send an `Authorization` header.
- **No cloud LLM APIs.** The only inference sketch is local KoboldCpp at `http://127.0.0.1:5001`.
- **No production deploy.** This is a draft package and a dry-run proxy.
- **Do not bind** the inference port or the expert ports.
- **Do not invent weights.** Configured GGUF paths are names, not files this repo ships.
- **Dry-run is the default.** A decision is not a completion.

## What this draft leaves out

The staged needle router also had a Windows VRAM probe, a PowerShell cutover, a Bonsai classifier that needed a bearer key, and an escalate ladder `needle → Bonsai 1.7B → Bonsai 8B → gpt-oss → Hermes`. Those are not ported. Depth, thickness, the complexity gate, the confidence spread, and cross-checked claims replace that ladder. Optional sentence-transformer embeddings are not included; the default path is SQLite FTS5 plus the rule classifier.
