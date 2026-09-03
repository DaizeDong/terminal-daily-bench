# feat: implement custom provider management with CRUD support, registration schema updates, and a dedicated UI form.

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

Implemented admin dashboard support for custom providers.

- Added create, edit, and delete flows for custom providers from the Providers dashboard.
- Added structured provider forms with dropdowns for finite choices like provider type, auth type, flow, OAuth auth method, device token request mode, and API-key header prefix.
- Added client-side validation with field-level highlighting for missing/invalid fields, while preserving the save-level error message.
- Added server-side validation for URL-like provider fields and API targets.
- Added `PUT /api/providers/{provider}` for updating custom providers.
- Fixed browser-session dashboard calls so custom provider mutations do not require a PoP header.
- Kept bundled providers read-only in the UI.
- Added focused regression tests for provider update, URL validation, and browser-session provider creation.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
