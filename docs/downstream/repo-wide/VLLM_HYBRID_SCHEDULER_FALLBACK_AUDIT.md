# vLLM hybrid scheduler fallback audit

Source pin: `68e0df5e7cc0e9eff9b5f8155ddb99bdcb43b32e`.

This audit asks one cross-feature question: when ATOM installs a correctness shim for an upstream framework gap, when is it safe to silently fall back if installing the shim itself fails?

## Current contract

`atom.plugin.vllm.scheduler` documents why ATOM supplies a scheduler subclass:

- upstream vLLM's load-failure recovery contains a single-KV-group unpack;
- a hybrid model can have multiple KV groups;
- with `kv_load_failure_policy=recompute`, an actual failed external load reaches that recovery path;
- the wrong scheduler can raise inside EngineCore rather than merely lose an optimization.

`select_scheduler_cls()` already contains a good **stand-down** rule: it inspects the live upstream method and returns `None` when the single-group expression is gone. It also preserves an explicitly selected scheduler and chooses a sync/async subclass matching vLLM's resolved scheduler mode.

The caller in `atom.plugin.vllm.platform._select_hybrid_aware_scheduler()`, however, wraps import + selection in `except Exception` and continues with vLLM's scheduler:

```python
try:
    from atom.plugin.vllm.scheduler import select_scheduler_cls
    chosen = select_scheduler_cls(sc)
except Exception:
    logger.warning(...)
    return
```

That fallback is intentionally broad: at this early platform hook the final KV cache groups have not been built, so a failure to install ATOM's subclass is harmless for workloads that never reach the hybrid failed-load path.

## The unsafe cell is narrower than “any selection failure”

The fallback becomes correctness-relevant only when all of the following are true:

1. an external KV connector is configured;
2. failed loads are allowed to recover through vLLM rather than terminate before that path;
3. the eventual KV layout has multiple groups whose invalid blocks require group-aware recovery;
4. upstream vLLM still has the single-group implementation;
5. ATOM failed to install the replacement scheduler.

Making **every** selection exception fatal would broaden startup failures for non-hybrid models and for configurations that never use recompute. Keeping every exception nonfatal can hide the exact cell the shim exists to protect.

Current recipes for GLM-5.2, GLM-5.3 and Kimi-K3 LMCache explicitly use `kv_load_failure_policy=recompute`; Kimi-K3 is the clearest multi-group case. This is a source/config fact, not a new runtime reproduction.

## Existing ownership / collision check

[#2369](https://github.com/ROCm/ATOM/pull/2369) owns several hybrid offload regressions and `tests/plugin/test_vllm_hybrid_kv_load_failure.py`, but its current changed-file set does **not** include `atom/plugin/vllm/platform.py` or `atom/plugin/vllm/scheduler.py`. Do not compete with its SeqView/lifetime changes; reuse its hybrid test surface if a later fix is warranted.

No open PR found in the first-pass collision sweep specifically changing the scheduler-selection fallback.

## Disposition

**No production patch yet.** The platform hook does not know enough to decide “hybrid correctness dependency” safely without either model-specific guessing or a later verification point.

The smallest useful next experiment is to prove whether ATOM has a later point, after `kv_cache_groups` exist but before requests are admitted, where it can assert:

> if upstream still needs the hybrid fix and this engine has multiple relevant KV groups under recompute, the selected scheduler must be ATOM's hybrid-aware class.

That would turn the fallback into:
- permissive during early framework compatibility probing;
- fail-closed only once the correctness dependency is observable.

If no such stable hook exists, the bounded maintainer question is whether the early selector should become fatal only for the explicitly supported ATOM offload connector + `recompute` recipes.

Do not add another monkeypatch, scheduler service, or model-name allowlist merely to close this audit.

_AI-assisted source review. No failed-load GPU run is claimed._
