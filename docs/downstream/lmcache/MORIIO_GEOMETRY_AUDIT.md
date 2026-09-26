# MoRIIO KV geometry audit

Source pin: `68e0df5e7cc0e9eff9b5f8155ddb99bdcb43b32e`. This is a source/CPU-boundary audit; no RDMA device, remote peer, model or GPU transfer was run.

## Current addressing contract

MoRIIO's registration looks per-layer, but the active read path is not:

- `register_kv_caches()` stores **one** `blocks_per_chunk`, taken from the first K tensor.
- It overwrites **one** `num_k_chunks` for every layer, leaving the last layer's K chunk count.
- `_get_or_build_sessions()` uses that one final K chunk count to split K from V metadata for **every** layer.
- `_read_blocks()` derives `is_mla` and `per_block_bytes` from the **first layer**, builds one block-pair grouping from them, and reuses the resulting offsets/sizes for every layer and for V.

Therefore a correct registration needs one homogeneous physical block geometry across every layer handed to this connector: the same MLA-vs-MHA shape convention, logical block count and K bytes per block; an MHA layer's V bytes per block must also equal its K bytes per block. Those facts make the global chunk plan deterministic. Without them, the code can use valid session/block IDs while copying the wrong byte range.

## Concrete counterexample

For two MLA layers at block size 4:

- layer 0 K shape `[8, 2, 4]` uint8 -> 2 logical blocks, 32 B/block;
- layer 1 K shape `[8, 2, 8]` uint8 -> 2 logical blocks, 64 B/block.

Registration currently accepts both. During a read, `_read_blocks()` takes 32 B/block from layer 0 and uses that size for layer 1 too, so only half of layer 1's block is requested. No region-map or scheduler change is needed to reach the wrong byte count.

The same global state is unsafe if layer block counts differ, if MLA and MHA layers are mixed, or if an MHA layer's K and V block widths differ.

This is not purely an invented topology. The repository itself documents that hybrid registrations can contain groups with different page geometries, and `MultiConnector.register_kv_caches()` forwards the same `kv_caches` / `transfer_tensors` arguments to every sub-connector. That does **not** prove a particular production MoRIIO deployment hit this exact geometry bug, so no incidence/performance claim is made.

## Minimal downstream candidate

Branch `fix/moriio-homogeneous-kv-geometry`, candidate `e0a4b178e933c31f23ef9761e3d9f8dfc46c4c7d`.

The candidate preflights geometry **before registering any memory**:

- K leading dimension must describe a whole number of logical blocks;
- MHA K and V block count/bytes must agree;
- every layer must share `(is_mla, logical_blocks, k_bytes_per_block)`.

It does not implement region transfer, change RDMA chunking, touch the scheduler, or claim heterogeneous layouts should be supported by MoRIIO. It narrows the current implicit assumption into a loud startup contract.

Six CPU cases are prepared:

1. cross-layer bytes-per-block mismatch -> reject;
2. cross-layer logical block-count mismatch -> reject;
3. MLA + MHA mixture -> reject;
4. MHA K/V bytes-per-block mismatch -> reject;
5. homogeneous MLA -> still register;
6. homogeneous MHA -> still register.

The negative cases must fail on original source because it accepts the geometry, pass on the candidate, and fail again when original source is restored. The wrapper and thread are test doubles; the actual production `register_kv_caches()` method is exercised. No RDMA operation is faked into a success claim.

## Registry contract (G4)

`moriio` currently inherits `reads_block_regions=True` while its worker accepts but does not consume `transfer_tensors`. That name is semantically inaccurate, but flipping it to `False` is not a safe fix: the FP4 sparse-indexer gate uses this capability to refuse layouts whose state the connector cannot represent. Marking it false would make the gate more permissive without teaching MoRIIO to move the missing bytes.

Disposition: keep the registry behavior unchanged for now; use concrete registration fail-closed guards for state/geometry MoRIIO does not move. Revisit the capability vocabulary only with an owner-approved region implementation or a replacement predicate that distinguishes “reads the map” from “safe for this layout.”

_AI-assisted source analysis and downstream experiment preparation._
