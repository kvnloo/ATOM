# LMCache pin-drift checkpoint

Reviewed ATOM main `68e0df5e7cc0e9eff9b5f8155ddb99bdcb43b32e` and #2250 head `62893d7530352395e8987f8e8123295ee6ef3f61`.

Both Dockerfiles still pin the same LMCache wheel image:

```
rocm/atom-dev:lmcache-v0.5.6.dev98-g05fc77a0-rocm-torch210@sha256:d3cfe74f42d78a188992cae98efbe23053610216e7b247632d6be772e9d465d6
```

So the owner branch has **no LMCache pin drift** relative to the inspected main. The MP parser/source experiments tied to `05fc77a0a7ababd9a7f2e343a771bc4bbc5b65cb` remain source-matched for that dimension.

LMCache's public repository currently uses `dev` as its default branch and continues moving independently. That moving branch is not evidence about the ATOM runtime until ATOM changes its digest-pinned wheel. Do not silently retarget qualification to current LMCache `dev`.

## Validator boundary

ATOM's wheel validator proves the installed wheel/version, native/CUDA extensions, ATOM MP adapter classes, `DeviceMessagingFuture`, `EngineGroupInfo`, and the MP-specific `--null-block-id -1 --separate-object-groups` parser path.

It intentionally calls `add_mp_server_args()`, not the complete `ServerCommand`/storage-manager CLI composition. Therefore it does not establish that the README's full `lmcache server ...` command contains every storage-manager-required argument. This is why the missing `--eviction-policy` recipe defect could coexist with a valid wheel. #2407 fixes that documentation using the separately executed real-parser comparison; it is not a wheel-validator failure.

**Disposition:** J2 is currently a no-op for runtime code. Re-run this audit only when the ATOM wheel image/digest or #2250's LMCache dependency changes. A future validator expansion should be considered only if maintainers want full launch-recipe validation in CI; do not add it merely to duplicate #2407.

_AI-assisted source audit; no new LMCache binary was executed in this checkpoint._
