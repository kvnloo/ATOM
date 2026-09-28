# Non-MoRIIO liveness sweep — wave 02

Source pin: `68e0df5e7cc0e9eff9b5f8155ddb99bdcb43b32e`.

This pass deliberately looked outside the existing MoRIIO handshake work.

## OpenAI stream collector — covered/no patch

`StreamOutputCollector` initially looks like a one-item-drain risk:

```python
while not self._pending:
    await self._ready.wait()
tag, chunk = next(iter(self._pending.items()))
del self._pending[tag]
if not self._pending:
    self._ready.clear()
```

The ownership model makes the usual lost-wake race inapplicable:

- `put_nowait()` and `get()` mutate `_pending` / the asyncio `Event` on the same event loop;
- pending work is keyed by fan-out tag, so siblings do not merge together;
- when more entries remain, the event stays set;
- `StreamBatchDispatcher._deliver()` intentionally delivers one whole engine step in one callback.

The dispatcher comment also records a falsified alternative: splitting one step across `call_soon` callbacks allowed step N+1 to interleave before step N's leftovers and could strand a client after terminal output ordering was corrupted.

Existing tests exercise collector fan-out/delivery semantics.

**Disposition:** no concurrency patch. This is a useful “looks suspicious but owner contract already closes it” example.

## KV aggregation — timeout is diagnostic, not a safety terminal

`AsyncIOProcManager.call_func_with_aggregation()` keeps one typed aggregation outstanding until every rank replies. The timeout only logs; it does not discard already-consumed destructive completion reports.

That is intentional. `tests/test_kv_aggregation_timeout.py` explicitly covers:

- delayed/missing ranks without rebroadcast;
- preserving consumed store/retired completions;
- independent store and retirement quorums;
- generation identity;
- later ranks consumed while an earlier rank is missing;
- pipelining exactly one next aggregation.

Turning this timeout into “drop and continue” would violate completion/lifetime safety. A process death is separately monitored by `AsyncIOProcManager.monitor_procs()`, which shuts the manager down.

**Disposition:** covered/no timeout patch.

## Diffusion worker hard exit — concrete liveness gap

Diffusion has good explicit terminals when Python remains alive:

- worker exceptions emit `OutputType.DEAD`;
- engine consumes `DEAD` and fails every nonterminal job;
- startup periodically calls `_assert_workers_alive()`.

After startup, however, `DiffusionCoreManager` has no process monitor. If a worker is terminated by a fatal runtime exit / SIGKILL before its exception handler can emit `DEAD`:

1. the process is dead;
2. no terminal reaches `manager.outputs`;
3. the engine dispatch thread only drains that queue;
4. an in-flight job can remain RUNNING indefinitely unless an external caller supplied a timeout to `wait()`.

That is a different contract from a long-running-but-live GPU kernel: process death is objectively terminal.

Downstream candidate:
- branch `fix/diffusion-hard-worker-exit-terminal`
- head `f166e04b2823299b94b0719c1354d8010bfd21cf`
- manager process monitor converts a hard process exit without a prior terminal into the existing `OutputType.DEAD` path;
- rank is recorded in `_dead_ranks` before enqueue so repeated polls cannot manufacture multiple synthetic terminals;
- normal worker exception reporting remains unchanged.

The deterministic CPU regression uses an already-exited fake process and the real manager detection method. Original source has no post-start detector; candidate must emit one DEAD terminal and never a second.

No GPU-hang timeout is introduced. A live process remains live regardless of how long a kernel takes.

## Reusable liveness rule

Time and liveness are different evidence:

- **process exited** -> terminal fact, safe to fail dependent work;
- **rank has not replied yet** -> unknown, retain destructive completion state;
- **stream has unread queued data** -> drain according to event-loop ownership;
- **elapsed timeout** -> diagnostic unless the subsystem has an explicit cancellation/failure contract.

_AI-assisted source review; no GPU liveness run claimed._
