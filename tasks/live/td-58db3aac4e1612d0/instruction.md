# Add automatic durable run checkpoints

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

[redacted-ref].

## Outcome

Adds opt-in automatic checkpointing and automatic resume to the local and distributed scientific run APIs. A run with no `checkpoint_dir` follows the ordinary path without filesystem work. When a directory is supplied, [redacted-repo] restores the latest committed complete `State` or `DistributedState`, including its random stream and retry-stable pending distributed work.

## Architecture and intent

- Uses the existing `Pytree.save`/`Pytree.load` serialization surface for the entire immutable state; the checkpoint layer does not duplicate or selectively reconstruct scientific state.
- Checks cadence only at coherent Python depth boundaries. Local capacity growth is an interruption of the same logical depth and is not checkpointed as a goal boundary. Distributed cadence checkpoints occur only after all work from the depth has been committed.
- Saves a changed final state regardless of cadence. Retryable distributed failures save the complete pending state before surfacing the error.
- Writes each generation to a same-directory temporary file, fsyncs it, computes SHA-256, atomically publishes the state, then atomically publishes a strict `CHECKPOINT` manifest as the commit record.
- Verifies manifest schema and checksum before pickle deserialization. Missing, malformed, incomplete, unsupported, and corrupt commits fail closed; there is no silent scientific rollback.
- Retains two generations for explicit operator recovery and holds one process lock for the full run to prevent competing continuations.
- Deliberately does not fingerprint or infer model, arguments, sampler, or runner compatibility. As agreed in [redacted-ref], the caller owns that contract.

Alternatives rejected:

- Selective/derived checkpoint payloads: duplicate the state schema and risk omitting continuation data. The complete immutable Pytree is the authoritative recovery unit.
- A sidecar checksum without atomic manifest publication: cannot distinguish an interrupted update from a committed generation.
- Silent fallback to an older generation: can conceal corruption and resume scientifically stale work.
- Checkpointing local capacity-growth returns: would expose a physical allocation boundary as a logical depth boundary.

## Performance evidence

The committed benchmark compares this branch with `develop` at `[redacted-sha]`, using Python 3.12.9, JAX/JAXLIB 0.10.0, x64, and one CPU device.

| Measurement | `develop` | This branch | Branch / develop |
|---|---:|---:|---:|
| Compile + first run | 1.74044 s | 1.74059 s | 1.00009 |
| Steady median, 200 runs | 3.335 ms | 3.275 ms | 0.9820 |
| Steady mean, 200 runs | 3.335 ms | 3.309 ms | 0.9923 |
| Scientific signatures | exact | exact | — |

The disabled path has no measured regression and does not alter the compiled JAX depth program.

For the enabled path, a complete 8D `State` with physical capacity 1,000,000 occupied 104,001,927 bytes. Five full durable saves took 0.5717–0.6172 s, median 0.6014 s. At the default one-hour cadence, that is 0.0167% amortized wall time on the measured local filesystem. This is not presented as an NFS or parallel-filesystem throughput claim; cadence remains configurable.

Reproduction and raw summary: `benchmarks/issue_270/`.

## Correctness evidence

- Exact local interrupted/resumed state equals uninterrupted continuation, including random stream.
- A real supervisor/worker distributed run checkpoints after one goal epoch and resumes the same directory to the next goal with a deliberately unrelated supplied key.
- Complete distributed pending task identities, requests, reservations, and keys survive serialization.
- Corrupt bytes are rejected before deserialization.
- Injected interruptions during state write and manifest publication preserve the prior commit.
- Malformed manifests, missing state, unsupported schemas, and incomplete directories fail clearly.
- A spawned competing process cannot acquire the directory while a run owns it.
- Cadence uses a monotonic clock and retains exactly two generations.

## Validation

- Full repository unit suite: 278 passed
- GitHub required matrix, Python 3.10 through 3.14: passed
- `cicd/tests/test_checkpoint.py` + reviewer autochecks: 19 passed
- Real distributed supervisor/worker checkpoint-resume test: passed
- Local run round-trip system test: passed
- Focused core/distributed/reviewer suite: 50 passed
- `ruff`: passed
- `flake8` on new checkpoint/test/benchmark modules: passed
- `git diff --check`: passed

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
