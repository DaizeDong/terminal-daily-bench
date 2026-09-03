# Gate new path globs on a package anchor

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Extends `check_artifact_paths.py`: a pattern whose non-final segments carry no package id can match the same-named file inside another app's container, so a new unanchored pattern now fails the lint job unless `path_anchor_allowlist.json` records why it needs no anchor.

The seeded allowlist carries all 164 current unanchored patterns with measured reasons (three corpora, 2026-08-28): distinctive markers, cross-app sweeps whose rows attribute the owning app (walStrings, the chromium family, c2paProvenance), shared or system locations, and two recorded as over-broad pending scoping (tikTok's `*_im.db*` also matches Lemon8; intrusion_logging's date-glob staged 2,688 TikTok files). Wildcarded package segments count as anchored; stale entries warn without failing; helper-built `__artifacts_v2__` blocks are imported so fitbit's patterns are audited too. Covered by unit tests.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
