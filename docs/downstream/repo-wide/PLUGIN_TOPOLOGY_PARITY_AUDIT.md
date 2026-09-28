# Plugin topology/config-shape parity audit

ATOM source pin: `68e0df5e7cc0e9eff9b5f8155ddb99bdcb43b32e`.

External RTP-LLM source checked at public head `382e155932e3bec7c58dc5c6b220773d66db9d9a` only to establish its constructor/config contract. This audit is source-only.

## vLLM

`_generate_atom_config_from_vllm_config()` reads the fields that define ATOM topology directly from vLLM's structured configs:

- `parallel_config.tensor_parallel_size`
- scheduler/cache fields from their owning configs
- the original `parallel_config` is retained on ATOM's projected config.

A missing TP field therefore raises instead of silently becoming TP1. This is the right behavior for a required topology contract.

The earlier LMCache world-size bug (#2282) was a different seam: a helper later read PP/TP from the wrong **level** of `VllmConfig`. That path now explicitly understands the nested shape.

**Disposition:** no generic vLLM config-shape patch.

## SGLang

SGLang plugin translation does more than copy a scalar. It reads live global `ServerArgs`, the actual TP rank and attention TP/CP groups, then normalizes them through `_normalize_sglang_parallel_config()`.

The normalizer already rejects inconsistent topology such as:

- PCP with unsupported DP;
- invalid PCP size/divisibility;
- attention TP not equal to `tp_size / attn_cp_size`;
- DP-attention world not divisible by DP size.

The resulting ATOM `Config.tensor_parallel_size` is written explicitly from that normalized result.

The later GLM DSA helper still uses `getattr(atom_config, "tensor_parallel_size", 1)`, but on the real plugin construction path this field is always produced by `Config`. Treating that local default as a standalone bug would ignore the owning config contract.

**Disposition:** covered by the construction boundary; no patch.

## RTP-LLM

ATOM's RTP adapter currently reads:

```python
rtpllm_parallelism_config = getattr(config, "parallelism_config", None)
tp_size = getattr(rtpllm_parallelism_config, "tp_size", 1)
tp_rank = getattr(rtpllm_parallelism_config, "tp_rank", 0)
```

At first glance this looks like the same silent-default class as #2282.

The upstream RTP-LLM model contract changes the conclusion:

- `BaseModel.__init__` requires a `ParallelismConfig`;
- model constructors in the current Python model path also take `parallelism_config: ParallelismConfig`;
- engine/cache/model code treats the object as a real required topology object rather than an optional compatibility hint.

So a normal RTP external-model instance reaching ATOM should already own `parallelism_config`. The fallback-to-1/0 only matters if the framework contract itself drifts or a nonstandard fake object calls the translator directly.

**Disposition:** do not patch an impossible normal-entry state without a reproduction. A future RTP API/version bump should instead add a version-compat test that passes a real RTP model/config object through this projection.

## Cross-framework table

| field/contract | vLLM | SGLang | RTP-LLM | disposition |
|---|---|---|---|---|
| TP size | required structured field | derived from live ServerArgs/groups | required by BaseModel contract | no new defaulting patch |
| rank | vLLM parallel config | live distributed group | ParallelismConfig | framework-owned |
| DP/CP interpretation | vLLM object preserved | explicitly normalized/validated | RTP ParallelismConfig | do not mechanically copy semantics |
| missing topology | raises on required vLLM attrs | raises on invalid live layout | ATOM helper has fallback, but normal RTP contract supplies object | audit on RTP version drift |
| compatibility alias/default | only where explicitly supported | old/new PCP flag bridge | fallback currently defensive only | must not be promoted to observed topology |

## Reusable rule

A `getattr(..., default)` is not automatically a bug. Ask whether the owning entry path guarantees the field first.

- If the owner guarantees it, a default may be unreachable compatibility code.
- If multiple real config shapes exist, normalize them at the boundary.
- If absence would silently change distributed geometry on a reachable path, fail closed.

That is the distinction between the real #2282 defect and the RTP source pattern above.

_AI-assisted source review; no RTP-LLM runtime was executed._
