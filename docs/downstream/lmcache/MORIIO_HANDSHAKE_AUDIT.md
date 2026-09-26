# MoRIIO background-handshake audit

Source pin: `68e0df5e7cc0e9eff9b5f8155ddb99bdcb43b32e`. The same aggregate callback behavior is still present on draft #1594 head `67b4a46185306715d42ad6b810a7108ebe838f98`.

## L1 — failed aggregate handshake is currently promoted to ready

Current `_initiate_background_handshake()` submits one future for every remote DP rank and then a `_wait_all()` future that calls `f.result()` on each. If any child handshake fails, the aggregate future is failed.

The callback attached to that aggregate future does **not** inspect its result. It unconditionally:

1. logs “All handshakes completed”;
2. enqueues the request in `_ready_requests`;
3. sets `load_ready_flag[remote_engine_id] = True`;
4. sets `write_ready_flags[remote_engine_id] = True`.

`start_load_kv()` then dequeues that request and calls `_issue_read_for_req()` against whatever partial remote metadata happened to be established.

This is a source-level control-flow defect. It does **not** prove a production incident rate.

## Existing failure plumbing should be reused

The worker API already permits `KVConnectorOutput` rather than the legacy `(done_sending, done_recving)` tuple. `ModelRunner`, `MultiConnectorWorker`, TP aggregation and the scheduler already understand `failed_recving`. The scheduler consumes a failed remote receive by leaving `WAITING_FOR_REMOTE_KVS` and returning the request to local work rather than treating it as a successful remote receive.

Therefore the smallest failure semantics are:

- do not enqueue a failed handshake group for RDMA reads;
- make the synchronous handoff loop exit for that attempt;
- publish the request id in `failed_recving`;
- preserve the legacy tuple on ordinary success so unrelated callers do not change shape.

No new retry service or exception hierarchy is required.

Downstream candidate: `fix/moriio-handshake-failure-terminal` @ `3e82901784dc289495516e5dee60e54ece1dd8c2`. The production change is based on `222a5a0d`; the later commit only removes a test-induced module reload.

Prepared deterministic CPU cases:

- two-DP group where rank 0 succeeds and rank 1 raises: no read, no ready queue, failed receive reported once;
- all handshakes succeed: one read and the ordinary legacy completion shape remain unchanged.

The test uses a synchronous fake executor and does not import or emulate MoRI RDMA. It exercises the real ATOM handshake orchestration methods.

[Queued evidence run](https://github.com/kvnloo/ATOM/actions/runs/36209914696). No result is claimed while queued.

## L2 — separate batching race found, not mixed into L1

There is another independent source issue in `start_load_kv()`:

- every request whose first peer handshake is still in flight can start its own handshake group;
- `need_handshake` is one boolean;
- `remote_engine_id` retains only the **last** request's peer;
- after handshakes complete, the loop consumes **one** item from `_ready_requests` and immediately breaks.

So two same-step requests that both require a first-time handshake can leave a second ready request stranded in the queue. A later step with no new handshake does not drain that queue.

This should be a separate candidate because fixing it requires explicit accounting for all handshake-waiting requests, and it must compose with L1's success/failure terminals. Do not hide it inside the failure patch.

A useful next deterministic test should hold two handshake futures incomplete until both requests have been admitted, complete both, and require two reads or two explicit failures—never one read plus a stranded queue entry.

## Interaction with partial peer state

When one remote DP handshake succeeds and another fails, `_remote_agents` may contain a partial peer set. L1 prevents the current request from reading through that partial state. A later retry policy must explicitly decide whether to reuse, clear, or re-register partial peer state; this is another reason not to turn the minimal terminal fix into an implicit retry framework.

## Harness correction learned from current downstream runs

The first MoRIIO CPU harnesses re-imported `atom.kv_transfer.disaggregation.moriio.moriio_connector` by deleting it from `sys.modules`. ATOM's normal `tests/conftest.py` correctly rejects this because it creates duplicate class identities.

The actual causal assertions still behaved as intended in the downloaded JUnit:
- completion original/restored: the two out-of-order cases fail; candidate assertions pass;
- local geometry original/restored: four missing-rejection cases fail; candidate assertions pass;
- index-state original/restored: two missing-rejection cases fail; candidate assertions pass;
- peer-layout original/restored: three missing-rejection cases fail; candidate assertions pass.

But the candidate arms also had one teardown error, so those runs are **not green evidence**. The test branches now preserve the canonical module identity and fresh reruns are required. No production assertion was weakened.

_AI-assisted source analysis and test-harness review. No hardware result claimed._
