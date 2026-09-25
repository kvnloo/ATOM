# Optional lookup warning policy: source-level decision note

Source pin: `68e0df5e7cc0e9eff9b5f8155ddb99bdcb43b32e`. Parent: [RFC lane E #6](https://github.com/kvnloo/ATOM/issues/6).

## Decision to test next

Prefer **exception class plus the existing exception message** for the optional lookup startup warnings, before considering class-only output.

Why:

- The current dense worker/scheduler messages already expose `str(exc)`; preserving it avoids silently reducing operator diagnostics.
- An empty `RuntimeError()` currently produces no failure identity beyond the component prefix. Adding `error_type=RuntimeError` fixes that concrete ambiguity.
- Nearby offload code already uses explicit `error_type=%s` for DSV4 checkpoint/storage and PAGE/SLOT failures, while other ATOM startup warnings retain exception text. Both conventions exist; class + current message is the smallest intersection rather than a new global policy.
- The earlier synthetic-secret fixture proved only that arbitrary exception text is arbitrary. It did **not** establish a real credential leak, so using that fixture to justify class-only logging would overstate the evidence.
- A sanitizer or broad status framework would be substantially larger than this problem and is not proposed.

Candidate shape:

```text
LMCache offload: lookup server not started: error_type=RuntimeError error=
LMCache offload scheduler: lookup client unavailable: error_type=ConnectionError error=<existing message>
```

This retains warning severity, valid non-hosting `None`, configured save/load roles and fallback behavior. Construction still does not prove RPC readiness or cache reuse.

## Scope map

Current exact-message siblings:

- dense worker: raw exception message;
- dense scheduler: raw exception message;
- M3 worker override: raw exception message; M3 scheduler inherits dense;
- DSV4 worker: raw exception message;
- DSV4 scheduler: raw exception message.

Do not change all five sites merely because their strings match. Dense remains the first acceptance slice. M3/DSV4 should follow only after checking whether their optional-service and stateful startup contracts are identical enough to share the wording.

Representative nearby class-only patterns exist in `hybrid/dsv4/codec.py` and parts of `hybrid/dsv4/connector.py`. Representative raw-message/traceback patterns exist elsewhere in ATOM. This mixed house style is another reason not to claim a repository-wide security rule from this local change.

## Acceptance matrix for the dense slice

1. Empty scheduler/client and worker/server exceptions include the correct component and `error_type`.
2. Nonempty exception text remains present exactly as before, with class added.
3. Valid lookup-server factory `None` remains silent.
4. Successful factory objects are retained without a readiness claim.
5. Producer/consumer/both/offload roles are unchanged on success and exception.
6. Existing invalid metadata/configuration still fails outside the optional lookup boundary.
7. Ordinary misses still recompute without a startup warning.
8. Base/test-only -> candidate -> restored comparison must isolate the new assertion; normal ATOM fixtures remain enabled.

No GPU, real LMCache server or model is required for this contract. Any eventual upstream patch should contain only the two dense warning edits plus focused tests; this decision note stays downstream.

AI-assisted source review and drafting.
