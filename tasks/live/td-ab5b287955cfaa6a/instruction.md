# Add optional produce retries; fail-fast remains the default.

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

This pull request introduces robust produce retry logic for Kafka topics in the `slipstream` library, making message production more resilient to transient broker errors. By default, message production is fail-fast, but users can now configure the number of retries and backoff between retries. While retrying, all registered source streams are paused and then resumed to ensure consistency. Comprehensive tests are added to verify this behavior.

**Produce Retry Logic and Error Handling:**

* Added support for configurable produce retries and retry backoff in the `Topic` class via the `produce_retries` and `produce_retry_backoff` options, with fail-fast as the default. Only retriable broker errors are retried, and sources are paused/resumed during retries via the new `signal_iterables` method. (`slipstream/core.py`, `README.md`) [[1]](diffhunk://#diff-f3c1d32418c37dcd213e0281d053ccd480ce7628f54c88555d0cc82d3bd3e64aL326-R366) [[2]](diffhunk://#diff-f3c1d32418c37dcd213e0281d053ccd480ce7628f54c88555d0cc82d3bd3e64aR519-R574) [[3]](diffhunk://#diff-b335630551682c19a781afebcf4d07bf978fb1f8ac04c6bf87428ed5106870f5L77-R77) [[4]](diffhunk://#diff-f3c1d32418c37dcd213e0281d053ccd480ce7628f54c88555d0cc82d3bd3e64aR341-R346) [[5]](diffhunk://#diff-f3c1d32418c37dcd213e0281d053ccd480ce7628f54c88555d0cc82d3bd3e64aR295-R320) [[6]](diffhunk://#diff-f3c1d32418c37dcd213e0281d053ccd480ce7628f54c88555d0cc82d3bd3e64aR193-R197)

**Testing Enhancements:**

* Added tests to verify that retriable errors are retried and sources are paused/resumed, that non-retriable errors fail immediately, and that the default is fail-fast. (`tests/test_core.py`)

These changes make Kafka production more reliable in the face of transient failures, while providing clear configuration and robust test coverage.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
