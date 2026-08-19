# fix: support 3D activations in gradient CAM weights

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

- Reduce over all spatial activation axes in GradCAM++ and XGradCAM weight calculations.
- Preserve existing 2D behavior while supporting 5D Conv3d activations.
- Add regression coverage for direct weight computation and full CAM calls on a tiny Conv3d model.

[redacted-ref].

## Why

Conv3d target layers produce activations shaped like `(N, C, D, H, W)`. The previous GradCAM++ and XGradCAM implementations only reduced axes `(2, 3)`, leaving the depth axis in the weight tensor and breaking 3D CAM generation.

## Tests

- `D:\Dev\Miniconda3\python.exe -m pytest tests/test_3d_cam_weights.py -q -p no:cacheprovider`
- `D:\Dev\Miniconda3\python.exe -m pytest tests/test_one_channel.py tests/test_svd_no_side_effect.py tests/test_3d_cam_weights.py -q -p no:cacheprovider`

I also tried `tests/test_context_release.py`, but the local run was blocked by filesystem permissions while torchvision attempted to create `D:\AI\Cache\Torch\hub` for pretrained weights.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
