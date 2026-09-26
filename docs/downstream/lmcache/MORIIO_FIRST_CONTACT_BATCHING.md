# MoRIIO first-contact batching audit

Source pin: `68e0df5e7cc0e9eff9b5f8155ddb99bdcb43b32e`.

## Two independent bugs in the current batch path

`start_load_kv()` uses one scalar `need_handshake` and one last `remote_engine_id` for an entire metadata batch. Every first-contact request can enqueue a ready item, but the post-loop handoff consumes exactly **one** item and breaks.

That means a batch containing two first-contact engines can reach:

```
ready queue = [request A, request B]
load_ready_flag = {engine A, engine B}
```

and issue only request A. Request B remains in the private queue; a later `start_load_kv()` call does not drain old entries unless that later call itself sets `need_handshake`.

A second issue appears when two same-batch requests target the same new engine. The outer readiness check uses `<engine>_dp0`, but the lock-protected inner check uses the unsuffixed `<engine>`. Before the first asynchronous group publishes `_remote_agents[<engine>_dp0]`, both requests can start their own handshake group.

Neither behavior requires an RDMA transfer to reproduce; both are request/handshake bookkeeping defects.

## Minimal downstream candidate

Branch `fix/moriio-first-contact-batching`, candidate `d08978baab82d2ffedc8247987ba75e9ee002514`.

The candidate keeps first-contact requests in the current `start_load_kv()` call rather than routing them through a cross-thread ready queue:

- collect every request that needs first contact;
- start at most one handshake group per unique engine in that batch;
- wait for every unique engine in that batch to reach a handshake terminal flag;
- issue every pending request whose engine is ready;
- keep the established-peer direct-read path unchanged.

The now-unused `_ready_requests` queue and `queue` import are removed. The handshake executor remains single-threaded; no new concurrency or retry policy is introduced.

This candidate intentionally does **not** solve failed-handshake semantics. That is L1 on the separate `fix/moriio-handshake-failure-terminal` branch. The two changes must be composed only after each contract is independently green, because a failed engine needs all of its pending requests to receive a terminal failure rather than simply being skipped.

## Deterministic CPU contract

Three cases use the real `start_load_kv()` method and replace only the external handshake/read effects:

1. two requests to two different first-contact engines — original issues only one; candidate must issue both;
2. two requests to the same first-contact engine — original starts two handshake groups; candidate must start one and issue both requests;
3. already-known peer — both original and candidate must take the direct-read path without another handshake.

[Hosted red/green/red run](https://github.com/kvnloo/ATOM/actions/runs/36210740265) is queued. No result is claimed while queued.

## Interaction with L1

The clean combined contract should eventually be:

- one handshake group per unique engine per batch;
- all requests waiting on a successful engine are released;
- all requests waiting on a failed engine report `failed_recving`;
- no request is issued against partial peer state;
- known peers remain direct;
- ordinary success remains compatible with the legacy completion tuple.

Do not merge the branches mechanically until a combined test covers success and failure with multiple waiting requests.

There is one additional composition edge: L1 writes `load_ready_flag[engine] = False` on failure, while L2 treats presence of an engine key as a terminal handshake observation. A later retry must clear or generation-scope that stale terminal **before** starting the new group; otherwise the caller can observe the old `False`, skip waiting for the retry, and strand that request. This is an L4 test requirement, not a reason to weaken either independent gate.

## Out-of-scope follow-up

The handshake RPC itself currently has no bounded receive timeout visible in the MoRIIO wrapper path, and `start_load_kv()` busy-spins while waiting. That is a separate liveness question: solving it requires an explicit timeout value and a terminal-failure contract, not merely adding a sleep.

_AI-assisted source analysis and downstream experiment preparation. No hardware result claimed._
