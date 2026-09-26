# MoRIIO handshake liveness audit

Source pin: `68e0df5e7cc0e9eff9b5f8155ddb99bdcb43b32e`.

This is a source-level liveness audit. It does not claim an observed production outage.

## Current blocking chain

A first-contact consumer request reaches:

```
start_load_kv()
  -> _initiate_background_handshake()
     -> _execute_handshake()
        -> DEALER send(GET_META_MSG)
        -> recv_multipart()        # engine metadata
        -> recv_multipart()        # per-layer memory metadata
```

The MoRIIO helper uses ATOM's generic `zmq_socket_ctx()` / `make_zmq_socket()`. Those helpers set HWM/buffer/IPv6/linger options but no `RCVTIMEO` or `SNDTIMEO`.

The connector itself exposes no handshake timeout key. The only timeout-looking constant in `moriio_common.py`, `ABORT_REQUEST_TIMEOUT = 3600`, is unused in the repository and has no documented handshake semantics.

At the caller, `start_load_kv()` waits for a readiness flag with a Python busy loop. The handshake executor has `max_workers=1`.

## Consequence

If a remote endpoint accepts no useful response, disappears after the connect, or a handshake listener stalls before either reply:

1. the worker future can remain blocked in `recv_multipart()`;
2. the one-thread handshake executor cannot advance later handshakes behind it;
3. `start_load_kv()` can spin indefinitely waiting for a flag that is never written;
4. the request cannot reach the existing remote-receive failure path.

This is stronger than “the retry is slow”: the present source provides no connector-local terminal bound at this layer.

## Do not patch this with only a sleep

Adding `time.sleep()` to the busy loop would reduce CPU burn but still leave the request parked forever. Adding an arbitrary socket timeout without failure plumbing would turn a hang into an exception that the current aggregate callback can mis-handle.

L1 and L2 establish the prerequisites:

- **L1:** a failed handshake group needs a real `failed_recving` terminal;
- **L2:** every request waiting on a first-contact engine needs explicit accounting rather than a one-entry ready queue.

Only after those contracts are green should a timeout be added.

## Smallest plausible timeout design

A future candidate should keep timeout scope local to MoRIIO's first-contact DEALER rather than changing ATOM's generic ZMQ helper globally.

Proposed shape for maintainer review:

- explicit connector config such as `handshake_timeout_ms`;
- positive integer validation at startup;
- set `zmq.RCVTIMEO` on the DEALER used by `_execute_handshake()`;
- on `zmq.Again`, raise a typed/clear handshake timeout into the L1 aggregate-failure path;
- every request waiting on that engine receives one failure terminal;
- no partial remote peer is treated as ready;
- established peers remain unaffected.

Whether send timeout is also needed should be decided from real socket behavior; DEALER send can queue locally while disconnected, so receive timeout is the first missing terminal bound.

## Acceptance contract before implementation

1. silent peer: bounded failure, no RDMA read, one receive-failure terminal;
2. first metadata reply but missing second reply: same bounded terminal;
3. successful peer just under the deadline: normal read path;
4. two requests waiting on one timed-out peer: both fail exactly once;
5. one healthy + one timed-out peer in one batch: healthy request reads, failed peer does not block or poison it;
6. no global `make_zmq_socket()` behavior change.

## Disposition

**Source gap confirmed; implementation intentionally not started yet.** Timeout value/default is a user-visible policy choice and should compose with the still-running L1/L2 evidence rather than create a third partially overlapping handshake patch.

_AI-assisted source analysis. No network, RDMA, model, or GPU timeout measurement is claimed._
