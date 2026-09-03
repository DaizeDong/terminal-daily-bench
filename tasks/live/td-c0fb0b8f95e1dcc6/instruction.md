# Fix DropPath sampling on Gaudi lazy mode

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

- sample DropPath masks with the out-of-place tensor-probability `torch.bernoulli` path
- preserve per-sample broadcasting, dtype, scaling, seeded determinism, and invalid-probability validation
- fix the `drop_prob` docstring and document the accelerator portability change

## Why

Gaudi 1.21 lazy recipe reuse can reject the in-place scalar `Tensor.bernoulli_` path with a tensor storage-offset mismatch. The bridge has a distinct, tested out-of-place tensor-probability Bernoulli path.

## Validation

- 14 focused DropPath tests
- 71 model/integration tests across DropPath, LUNA, EEGDINO, and TCFormer (9 skipped)
- Voyager Gaudi 1.21.4: 100 synchronized Bernoulli iterations and 5 BF16 LUNA forward/backward/AdamW steps in lazy mode; finite losses and gradients; exit 0

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
