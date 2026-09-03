# feat(bench): add the [redacted-repo] bench backend benchmark harness (bootstrap)

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

First slice of the backend benchmark suite. Functional parity across the backends does not imply performance parity (a missing index or a bad query plan can make a correct backend orders of magnitude slower), and there was no way to measure or guard that. '[redacted-repo] bench' runs fixed workloads against the configured backend and emits a JSON latency report so regressions are visible and backends are comparable on the same data.

- [redacted-repo]/tools/bench.py: the '[redacted-repo] bench' CLI -- a scenario registry, a warmup+timed runner with nearest-rank p50/p95 (min/max/mean) latency stats, JSON report (version / backend / python / platform / per- scenario results), and --list / --scenario / --backend / --iterations / --warmup / --output flags. Backend label auto-detected from the configured DB URL.
- Two read scenarios to start (bench_top_service, bench_top_port), each a cursor-materialising view topvalues query; adding more is one entry in SCENARIOS.
- Registered in [redacted-repo]/tools/__init__.py (bash completion picks it up via '[redacted-repo] help'); documented in doc/dev/benchmarks.rst.
- BenchToolTests: backend-free coverage of the metric maths, scenario dispatch, arg handling, backend detection and JSON report shape.

Deferred to follow-ups: the larger scenario set (ingest / search / concurrency), shared fixtures, and a CI lane with a regression gate.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
