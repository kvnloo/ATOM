# Cloud + agent research trade route — source map

Upstream source pin: `922b3519628a002ae9dbdd4d30683e17d372ff00`.

This note records source facts behind downstream program #20 and RFCs #21–#24. It is not a statement of requirements from DigitalOcean, Nous Research, or any other organization.

## 1. Cloud serving: ATOMesh already has the right primitives, but admission is global

`atom/mesh/src/core/admission.rs` owns one process-global:

- running semaphore;
- waiting semaphore;
- FIFO turn mutex;
- optional token bucket;
- queue timeout.

`AdmissionController.acquire()` receives only a static ingress label. HTTP middleware always calls `acquire("http")`; ext-proc uses its own static ingress label.

This means current admission can answer “is the service overloaded?” but not “which tenant is allowed to consume how much of the overload budget?”

The current metrics surface is likewise service/model/endpoint-oriented. It does not need raw tenant IDs added to Prometheus; doing that would be a cardinality/privacy regression.

Downstream RFC: #21.

## 2. Agent serving: native Anthropic exists; mesh parity is the remaining seam

Native ATOM now has:

- `POST /v1/messages` in `atom/entrypoints/openai/api_server.py`;
- `serving_anthropic.py`;
- shared `ToolCallStreamParser`;
- tool/reasoning/streaming property tests.

ATOMesh current `server.rs` exposes Chat Completions, Completions, Responses and conversation routes, but a source search under `atom/mesh` finds no `/v1/messages` route.

So ROCm/ATOM#552 is partly stale as a repository-level feature request: the native endpoint exists. The useful remaining integration question is whether routing through the mesh preserves the already-working native wire semantics.

Downstream RFC: #22.

## 3. Research serving: Lumen-RL work already defines the beginnings of a safe online-update contract

ROCm/ATOM#2297 introduces all-rank `collective_rpc` plus capability discovery.

ROCm/ATOM#2298 adds transactional RCCL weight delivery:

- update generation/version;
- begin/apply/commit/abort;
- coverage verification;
- no serving through a partial update;
- fused-parameter accumulation across buckets;
- commit-time finalization.

Its own PR text calls out remaining transport parity: equivalent coverage/transaction semantics for shm/IPC are follow-up work.

ROCm/ATOM#2274 adds Rollout Router Replay (R3), making model-version attribution especially useful: replay evidence is only interpretable when the rollout and the replay refer to the same committed weights.

Downstream RFC: #23.

## 4. Cloud control plane: export stable signals, do not embed another autoscaler

ATOMesh already observes:

- admission queue depth;
- active connections;
- TTFT/TPOT/generation duration;
- input/output token counts;
- worker health/load;
- startup readiness;
- routing/cache locality.

These are enough to build an external scaler, but their measurement boundaries differ. Example: HTTP TTFT is intentionally measured outside the concurrency queue and therefore includes queueing/admission time.

An orchestrator should consume a versioned semantic contract rather than scrape incidental implementation metrics.

Downstream RFC: #24.

## 5. Existing work we must not recreate

- LMCache qualification preparation is closed in #1; external evidence lives in #12.
- #2412 already owns invalid LMCache lookup scope.
- #2442 owns the native-MP timeout documentation follow-up.
- #2274/#2297/#2298 own Lumen-RL route replay / RPC / RCCL updates.
- current ATOMesh already has retries, circuit breakers, global rate limiting, cache-aware routing and worker health/load tracking.
- native tool/reasoning parsing is already extensive; do not build a second parser in Rust just to add a mesh endpoint.

## Priority

1. **#22 protocol parity** — small, user-visible and likely CPU-testable; native implementation already exists.
2. **#21 tenant admission** — high cloud value; start with shadow accounting + bounded identity before fairness policy.
3. **#23 transport-independent weight transaction** — high research value but stacked on active owner PRs, so build conformance tests before refactoring.
4. **#24 autoscaling signal contract** — prepare snapshots/replay, but keep scaling policy outside ATOM.

## Evidence rule

Every branch must end as one of:

- already covered;
- owner already owns it;
- concrete counterexample;
- minimal tested candidate;
- bounded owner question;
- external/hardware dependency.

No result is promoted from source inspection alone.
