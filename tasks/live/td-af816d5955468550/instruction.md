# Add round() when loading NIfTI for atlas building

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Hi @[redacted-repo] and collaborators, thank you for sharing this amazing package! So useful and exceptionally well-documented, with a straightforward user interface and high-quality renderings 😊

While noodling around with the `build_subcortical_atlas` function across a variety of subcortical atlases, I found that no meshes were created for one atlas. Upon inspection, at least when loaded with `nibabel`, the voxel index values were floats instead of integers (e.g., 2.99999 when the index should just be 3). I believe this arises from issues with float format and precision.

As a proposed fix for that case (which other volumes may also encounter), I've added a `.round()` function call when loading in the NIfTI volume in `build_subcortical_atlas`. This change is in line 292 of `atlas_builder.py`. I also added a new testing script `tests/test_atlas_builder.py` and confirmed all tests passed with `uv` on my end.

Hope this is helpful, and I'm very happy to tweak if needed.

Cheers,
Annie 😊

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
