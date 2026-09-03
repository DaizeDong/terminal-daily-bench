# Fix monitor lifecycles and GPU sampling

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

- add deterministic `BaseMonitor.close()` / context-manager ownership and run `InputMonitor` transforms before module forward
- consume paired STDP monitor records without stale name indexes or `pop(0)`, reject mismatches, and no-op on empty buffers
- make `GPUMonitor` promptly stoppable, shell-free, failure-aware, and responsible for closing its TensorBoard writer
- consolidate duplicated constructor examples into the bilingual monitor tutorials

[redacted-ref].

## Root cause

A hook registered on a live module owns a closure that strongly references its monitor:

```text
live module -> module._forward_hooks -> hook closure -> monitor
```

Deleting the caller's monitor variable therefore cannot reach `BaseMonitor.__del__()` while the module remains alive. The full diagnosis and its distinction from the autograd retention fixed by [redacted-ref] / [redacted-ref] are recorded in [redacted-ref]. This PR uses explicit `close()` / context-manager ownership instead of adding weak-reference hook machinery.

The learner-side issue was separate: direct `records.pop(0)` calls mutated the flat list without updating `name_records_index` and imposed quadratic FIFO consumption.

## Commits

1. `fix(monitor): make hook and record lifecycles explicit`
2. `fix(monitor): make GPU sampling stoppable`
3. `docs(monitor): consolidate usage examples`

## Validation

Local (macOS, Python 3.11):

- `pytest -q test/activation_based/test_monitor.py test/activation_based/test_learning.py` — 28 passed
- `uv format --check -- ...` — passed
- `uv run python tools/generate_changelog_rst.py --check` — passed
- `uv run sphinx-build -M html docs/source docs/build` — passed, no warnings
- `git diff --check` — passed

Remote g3 (7x RTX 4090, PyTorch 2.7.1+cu118, CUDA toolkit pinned per `ENV.md`):

- verified `[redacted-repo].__file__` resolves to the dedicated remote source directory
- same targeted pytest command — 28 passed
- real `GPUMonitor(gpu_ids=(0,), interval=0.2)` smoke — 2 samples, stopped and joined successfully

## Deliberate limits

No weak-reference hook framework, custom record container, retry policy, extra GPU metrics, NVML dependency, or merger with the model-level profiler.


<!-- This is an auto-generated comment: release notes by coderabbit.ai -->

## Summary by CodeRabbit

* **Improvements**
  * Added safer monitor lifecycle management with context-manager support and explicit `close()` cleanup.
  * Input monitors now capture transformed inputs before module execution.
  * STDP learning validates matching records, handles empty data safely, and clears consumed records consistently.
  * Improved GPU utilization monitoring with responsive stopping, clearer error reporting, configuration validation, and reliable TensorBoard cleanup.
* **Documentation**
  * Updated monitoring tutorials with lifecycle guidance, memory-saving tips, input snapshots, and GPU sampling examples.

<!-- end of auto-generated comment: release notes by coderabbit.ai -->

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
