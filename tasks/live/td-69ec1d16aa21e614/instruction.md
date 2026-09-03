# Fixes after audit

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

- Fixed `--timeout` parsing so explicit values are integers and no longer break transaction-result waiting.
- Added validation that rejects odd-length `--token-transfers` lists instead of silently dropping the final argument.
- Added a regression test for malformed token-transfer pairs.
- Fixed `get network-status --shard` so the selected shard is forwarded to the network provider.
- Made `--name` mandatory for dns register.
- Prevented tx sign from succeeding when no sender, guardian, or relayer wallet is available.
- Added HTTP status validation to contract verification, verification polling, and contract unverification requests.
- Improved guardian cosigner error handling by converting HTTP failures into GuardianServiceError.
- Updated a test address argument to use the supported `addr:` prefix, removing deprecated behavior.
- Expanded `CLI.md.sh` and regenerated `CLI.md` with 16 previously undocumented paths, including DNS, configuration deletion, network status/config, governance proposal, and semi-fungible token commands.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
