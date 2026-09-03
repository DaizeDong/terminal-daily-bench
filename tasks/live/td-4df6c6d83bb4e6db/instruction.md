# [redacted-repo] Python Client Release - 1.13.0

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Automated Sync from Internal Repository

### Changes in this sync:
<!-- Please describe the main changes included in this sync -->
- `DatacubeService.enrich_raster_metadata()` for client-side enrichment of STAC items with projection (`proj:code`, `proj:transform`, `proj:shape`, `gsd`) and raster band (`raster:bands`) metadata by reading asset files via rasterio

### Breaking Changes:
<!-- List any breaking changes, or write "None" -->
- None

---
*Automated sync from internal repository. Please review and update the changelog above before merging.*

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
