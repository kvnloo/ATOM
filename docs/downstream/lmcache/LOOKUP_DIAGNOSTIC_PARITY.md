# Lookup diagnostic parity audit

Source pin: `68e0df5e7cc0e9eff9b5f8155ddb99bdcb43b32e`. This is a source-contract audit only; it does not amend #2406 or claim maintainer preference for a broader patch.

## Dense reference

[#2406](https://github.com/ROCm/ATOM/pull/2406) keeps the existing optional-lookup fallback and exception message and adds `error_type=<class>` to the two dense startup warnings. The candidate does not change roles, warning level, lookup construction, valid `None`, or startup configuration validation.

## M3

`M3OffloadConnector.register_kv_caches()` performs all PAGE-region validation, codec construction, fused-staging validation, LMCache engine construction and chunk-size setup **before** its optional lookup-server `try`. The `try` contains only the lookup factory import plus `create_lookup_server(engine, meta)`.

Its warning is currently the same message-only form as dense:

```
LMCache offload: lookup server not started: %s
```

A returned `None` does not enter the exception path. The worker therefore has the same relevant diagnostic contract as dense: adding the exception class while retaining the message changes observability only.

`M3OffloadScheduler` subclasses `DenseOffloadScheduler` unchanged, so #2406 already covers its scheduler/client warning. A separate M3 scheduler edit would be duplicate work.

**Disposition:** M3 worker parity is source-proven; hold any edit until #2406 establishes upstream preference. If accepted, the smallest follow-up is one worker warning + focused regression, not a new helper.

## DSV4

`DSV4OffloadConnector.register_kv_caches()` keeps required configuration outside the optional service boundary:

- LMCache config and DSV4 profile construction;
- PAGE/SLOT geometry validation;
- codec/fused-staging validation;
- engine creation;
- backend validation;
- required SLOT sidecar initialization and component checks.

Only the lookup factory import and `create_lookup_server(engine, meta)` are inside the optional lookup-server `try`. A returned `None` remains valid because only exceptions emit the warning.

`DSV4OffloadScheduler.__init__()` similarly builds the required LMCache config, DSV4 profile, world size and metadata before entering the lookup-client `try`. Only the factory import plus `create_lookup_client(cfg, meta)` are optional. Its fallback remains `_lookup_client=None`.

Both warnings use the same message-only formatting as the dense reference.

**Disposition:** DSV4 worker/server and scheduler/client boundaries are source-equivalent for this narrow diagnostic change. Do not touch PAGE/SLOT lifetimes, storage validation, publication policy, or lookup fallback. Hold implementation until #2406 feedback rather than sending a sibling PR concurrently.

## Shared helper decision

Do **not** extract a helper yet. There are now three concrete implementations, but only dense has an upstream review surface. A helper would alter imports/call sites and broaden review without changing behavior. Revisit only if maintainers accept #2406 and prefer a common formatter.

## What this audit does not prove

- that every exception message is safe to expose;
- that lookup availability should become mandatory;
- that all hybrid connectors share identical lifecycle semantics beyond startup warning formatting;
- any real LMCache, server, model, GPU or performance behavior.

_AI-assisted source analysis; no runtime result claimed._
