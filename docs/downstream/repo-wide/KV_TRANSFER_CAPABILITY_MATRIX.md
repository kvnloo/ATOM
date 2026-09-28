# KV transfer capability-contract matrix

Source pin: `68e0df5e7cc0e9eff9b5f8155ddb99bdcb43b32e`.

The factory currently exposes two distinct transport capabilities:

- `requires_pd_staging`: whether compressor/P-D staging is required;
- `reads_block_regions`: whether the attention backend's PAGE region map is consumed.

These must not be used as proxies for each other.

| Backend | requires P/D staging | reads block regions | Source disposition |
|---|---:|---:|---|
| `moriio` | true (default) | true (default) | **Declaration is broader than current implementation.** #2354 / Wave 02 isolate this; do not “fix” by flipping the flag alone because the FP4 sparse-indexer gate uses it as a safety refusal. |
| `mooncake` | true (default) | true (default) | Region-map consumer; no mismatch found in first source pass. |
| `lmcache_offload` dense | false | false after layout refinement | Dense codec builds from `KVCacheTensor`; current factory special-case is intentional. |
| `lmcache_offload` hybrid/M3/Kimi | false | true after layout refinement | These layouts source PAGE bytes/state from published regions; current refinement is intentional. |
| `lmcache_mp` | false | true (default) | Important counterexample proving the two flags differ: no P/D staging, but cache views require `KVTransferTensors`. |
| `multi` | true (registration default) | OR of sub-connectors | Region-map result is correctly compositional: one reader means the map must exist. P/D staging is conservatively true for the composite; first pass found no correctness break, only possible over-allocation for unusual offload-only composites. |

## Consumer crosswalk

`topology_reads_block_regions()` is consumed by the FP4 sparse-indexer gate in the attention backend. The gate rejects a transport when the sparse indexer cannot publish the PAGE region representation that transport would read.

`topology_uses_pd_staging()` is consumed by DeepSeek-V4 P/D staging selection. It answers a different memory-layout question.

The repository already includes tests pinning the critical `lmcache_mp` distinction: it declares no P/D staging but still requires the region map. This is good evidence that one generic `supports_regions`/“offload” boolean would be a regression.

## Cross-feature lesson

A capability flag should answer exactly one downstream question. If two consumers ask different questions, split the capabilities even when today's backends correlate them.

This is the same failure class as:
- “lookup configured” vs “lookup actually usable”;
- “store complete” vs “source safe”;
- “framework installed” vs “framework used by this benchmark.”

## New-patch disposition

No new factory refactor in this pass.

The current concrete mismatch remains MoRIIO's declaration vs implementation, and that surface already has an owner/current-main safety lane. The `multi` P/D-staging default may be conservative for unusual compositions, but no measured or semantic failure was established; optimizing it now would be speculation.

Next capability audits should target other registries only when an actual consumer relies on the declaration for correctness or material allocation.

_AI-assisted source review; no runtime transport result claimed._
