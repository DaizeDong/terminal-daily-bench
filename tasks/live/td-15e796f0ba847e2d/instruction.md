# fix: resume checkpoints across JobSet whole-set restarts in clustered tasks

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Problem
  
  In `ClusteredTaskEnvironment` tasks, checkpoint saving works but a JobSet whole-set restart never loads
  the checkpoint saved by the previous attempt — `ctx.checkpoint.load()` returns None and training
  silently restarts from step 0, losing all progress.

  ## Root cause
  
  The backend templates `--checkpoint-path` / `--prev-checkpoint` into the container args once, per Flyte 
  attempt (`prevCheckpointPrefix` is only populated from Flyte attempt ≥ 2, pointing at the previous
  Flyte attempt). JobSet whole-set restarts happen entirely at the K8s layer: the JobSet controller
  recreates pods from the same pod template, so the backend never gets a chance to re-template
  `--prev-checkpoint`. Every restart attempt within a Flyte attempt therefore ships with
  `--prev-checkpoint '""'` while sharing one `--checkpoint-path`
  `(.../<action>/<attempt>/_flytecheckpoints)`.

  Verified on a live reproduction `(examples/clustered/failure_cascade.py)`: the restarted pod's args
  carried the empty prev path while the checkpoint blob from the previous attempt sat at the exact
  `--checkpoint-path` URI the pod was given — the SDK just never looked there.

  This can only be fixed in the SDK: the sole signal that a pod is a restarted set is the
  `JOBSET_RESTART_ATTEMPT` env var (downward-API projection of the `jobset.sigs.k8s.io/restart-attempt` annotation), which exists only inside the pod at runtime.

  ## Fix

  In `TaskContext.checkpoint` (`src/flyte/models.py`): when `restart_attempt > 0`, use the task's own
  `checkpoint_path` as the load source — the previous restart attempt saved there. Otherwise keep the
  backend-templated prev path exactly as before.

  - Scoped strictly to jobsets: `JOBSET_RESTART_ATTEMPT` is only ever set on jobset pods, so regular
    tasks hit the identical code path as today. `flyte._checkpoint.Checkpoint` is untouched.
  - `restart == 0` keeps prev, preserving cross-Flyte-attempt resume (backend templates that correctly).
  - A set that restarts before its first save finds nothing at its own path; `Checkpoint.load()` already
    treats a missing object as "no checkpoint" and returns None gracefully.

  ## Testing
  
  - Unit (`tests/flyte/test_checkpoint.py`, +3 tests): restarted set loads from its own path (including
    the literal `'""'` prev the backend templates); restart before first save returns None; env unset / 0
    keeps prev — regular-task behavior pinned unchanged.
  - E2E before: `failure_cascade.py` on a local devbox (JobSet controller v0.8.1) — attempt 1 logged
    `restart_attempt=1`, no resume, reran all 40 steps; checkpoint blob confirmed present in the object
    store.
  - E2E after: same example on local devbox and`demo.hosted.unionai.cloud` (run `uvmmvthbbdnmh4gmklw2`, SUCCEEDED) — attempt 1 logged resumed from checkpoint at step 25 and completed only the remaining steps.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
