# Fix model loading issues and forecast_naive slicing bug in [redacted-repo] 2.5

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

- Allow model wrapper constructors (__init__) to accept and ignore extra keyword arguments (e.g. proxies) passed by huggingface_hub during from_pretrained.
- Implement load_checkpoint for [redacted-repo]_2p5_200M_torch and [redacted-repo]_2p5_200M_flax to restore weights from local paths.
- Fix slicing bug in PyTorch's forecast_naive to correctly slice the time/horizon dimension ([:, :horizon, :]) instead of quantiles.
- Add unit tests in tests/test_model_loading.py covering local checkpoint loading, hub compatibility, and prediction shape correctness.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
