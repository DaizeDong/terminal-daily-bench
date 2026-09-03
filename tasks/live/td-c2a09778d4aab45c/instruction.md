# feat(image): add Krea 2 models

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

Add built-in image model support for Krea 2 Raw and Krea 2 Turbo.

## Changes

- Register `Krea-2-Raw` and `Krea-2-Turbo` as built-in text-to-image models.
- Add Hugging Face and ModelScope sources:
  - Hugging Face revision: `main`
  - ModelScope revision: `master`
- Add Diffusers support using the released `diffusers>=0.39.0` package.
- Add SGLang [redacted-repo] support.
- Translate Krea CFG values to SGLang guidance scale semantics.
- Enable build isolation for Krea SGLang virtual environments so build dependencies are resolved automatically.
- Add minimal built-in model documentation and catalog entries.
- Add metadata, registration, and guidance-scale regression tests.

## Default Generation Settings

| Model | [redacted-repo] Steps | Guidance Scale |
|---|---:|---:|
| `Krea-2-Raw` | 52 | 3.5 |
| `Krea-2-Turbo` | 8 | 0.0 |

## SGLang Guidance Scale

Krea uses:

```text
cond + cfg * (cond - uncond)
```

SGLang uses:

```text
uncond + scale * (cond - uncond)
```

Therefore, X[redacted-repo] adds `1.0` to the configured Krea guidance scale before sending the request to SGLang.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
