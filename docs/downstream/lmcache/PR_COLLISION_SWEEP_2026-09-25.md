# PR collision sweep — 2026-09-25

Upstream main inspected: `68e0df5e7cc0e9eff9b5f8155ddb99bdcb43b32e`.

This is a routing artifact, not a ranking of other work. Its purpose is to keep the RFC from creating duplicate or conflicting contributions.

| Surface | Current owner / status | Collision rule for this RFC |
|---|---|---|
| [#2250 native DSv4 LMCache MP](https://github.com/ROCm/ATOM/pull/2250) | active feature branch; native PAGE/STATE MP | Do not implement DP/state/native-MP architecture in parallel. Limit our MP work to source characterization/docs or clearly separate defects. |
| [#2353 MP save admission budget](https://github.com/ROCm/ATOM/pull/2353) | stacked on #2250; MP-only admission policy | Do not introduce a shared/global save-admission framework from this RFC. |
| [#2369 plugin/offload accuracy fixes](https://github.com/ROCm/ATOM/pull/2369) | open, mergeable; touches plugin grouping, pin ledger, SeqView, staging | Do not duplicate index-cache group routing, lookup-pin semantics, deferred-save SeqView slots, GLM/Kimi accuracy work, or cudagraph-padding work. |
| [#1594 MoRIIO write/push + region/fabric](https://github.com/ROCm/ATOM/pull/1594) | old draft, currently unmergeable, last updated July; owns generalized MoRIIO write-mode/region design | Do **not** build a competing generalized region-transfer or fabric implementation. Current-main read/pull safety guards may be developed downstream, but refresh against #1594 before any upstream submission. |
| [#2354 MoRIIO region/completion issue](https://github.com/ROCm/ATOM/issues/2354) | concrete real-hardware report; offers completion fix + region reference | Reuse its evidence. The one-line all-status completion candidate is explicitly separable. Region implementation remains owner/design territory. |
| [#2402](https://github.com/ROCm/ATOM/pull/2402), [#2404](https://github.com/ROCm/ATOM/pull/2404), [#2406](https://github.com/ROCm/ATOM/pull/2406), [#2407](https://github.com/ROCm/ATOM/pull/2407) | our current upstream queue | No sibling PR unless it closes a distinct invariant. Comments only on real review/head/evidence changes. |

## Consequences

1. **MoRIIO generalized regions are not our next implementation target.** #1594 already owns that design space and #2354 has a newer real-hardware reference implementation. Our safe lane is current-main read/pull correctness: completion ordering, fail-closed unsupported state, homogeneous local geometry, and peer-geometry compatibility.
2. **Plugin grouping / GLM/Kimi offload work is already occupied by #2369.** Do not turn the full-request RFC into another plugin accuracy branch.
3. **Native MP scheduling/state work belongs to #2250/#2353.** #2407 is intentionally docs-only and stacked on the owner branch.
4. **A no-op is a successful collision result.** In particular, diagnostics parity for M3/DSV4 remains prepared but should not become sibling PRs until #2406 gets maintainer feedback.

## Newly uncovered invariant after the sweep

Current-main MoRIIO read/pull checks only that each local/remote layer has the same **descriptor count** when building sessions. It does not reject:

- different peer `num_blocks`;
- different peer `block_len`;
- equal descriptor counts whose registered byte sizes differ.

MoRI's Python `MemoryDesc` exposes a read-only `size` field, and that field is serialized in the packed descriptor. Therefore this can be checked before any session/read without adding protocol fields.

Downstream candidate: `fix/moriio-peer-layout-compatibility` @ `8076e3a0883f62d2022b0ad50e03d21f0744171b`.

It validates the existing handshake/session data only; it does not implement regions, write mode, fabric, or a new fingerprint protocol. The positive control preserves a matching peer. Three negative controls cover remote block-count, block-length and registered-byte-size mismatch.

Because #1594 touches the same MoRIIO file and changes its protocol substantially, this candidate stays downstream until its CPU gate passes **and** #2354/#1594 are refreshed before submission.

_AI-assisted source review and routing._
