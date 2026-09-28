# Connector teardown contract audit

ATOM source pin: `aa0c5c3a131d98124726b41ab62342bb8cafb207`.
LMCache public source checked at `e73629e286258f5477f83f6d99de4977ad7b3bf7`.

This audit asks one question: **who proves that background work and external registrations are finished before ModelRunner releases the KV pool?**

## The engine boundary

`ModelRunner.exit()` deliberately calls:

```python
connector = get_kvconnector()
close = getattr(connector, "close", None)
if callable(close):
    close()
# ... then destroy_dist_env() and delete kv_cache
```

The comments name the contract: connector teardown must happen before the distributed environment and the KV tensors disappear.

## Existing connector behavior

| connector | close visible to ModelRunner | meaningful teardown |
|---|---|---|
| in-process `lmcache_offload` | yes | joins save/load executors; dense closes GPU connector; Kimi state tier drains/shuts down |
| `multi` | yes | fans close out to every sub-connector |
| `lmcache_mp` on current main | **no** | adapter shutdown is only used on registration/init failure |
| MoRIIO/Mooncake | no generic close in first pass | separate audit needed; do not infer a defect without their registration lifetime contract |

## Why LMCache MP is different

LMCache's public `AtomMPWorkerAdapter.shutdown()` is not cosmetic client cleanup. It:

1. stops and joins the heartbeat;
2. waits for registration/submission leases;
3. drains tracked operation futures;
4. unregisters the ATOM GPU views from the MP server;
5. closes the transfer context;
6. closes the request client.

ATOM current main creates this adapter and successfully registers KV views, but after that exposes no `close()` on `atom.kv_transfer.offload.mp.worker.LMCacheMPConnector`. The public capability-selecting shell uses `__getattr__`, so it can forward `close` once the selected worker implementation actually provides one.

Without that hook, the engine proceeds directly to distributed-env/KV-pool teardown while the MP adapter still owns registrations whose addresses name that pool.

## Candidate

`fix/lmcache-mp-worker-close` adds the smallest lifecycle bridge:

- `LMCacheMPConnector.close()` calls the selected adapter's `shutdown()`;
- clears the local adapter reference before the call so repeated teardown is idempotent from ATOM's side;
- native-state MP inherits the same worker implementation, so no second close path is needed;
- public shell forwarding is tested explicitly.

This does not introduce a new drain algorithm. It invokes the drain/unregister contract LMCache already implements.

## What is not claimed

- No GPU use-after-free has been reproduced locally.
- No claim is made that MoRIIO or Mooncake require the same hook.
- No scheduler-side cleanup change is bundled here.
- No transfer deadline semantics change.

The source-level invariant is sufficient for CPU qualification:

> if an external adapter registers live GPU views and supplies an explicit shutdown that drains/unregisters them, the engine teardown path must invoke it before releasing those views.

_AI-assisted source review; no GPU runtime result implied._
