# fix(terraform): CKV_AZURE_190 override singular get_expected_value

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

**By submitting this pull request, I confirm that my contribution is made under the terms of the Apache 2.0 license.**

## Description

`StorageBlobRestrictPublicAccess` (CKV_AZURE_190) overrides `get_expected_values()` (plural) returning `[False]`, but inherits `get_expected_value()` (singular) from `BaseResourceValueCheck`, which returns `True` by default.
Per the base class docstring, `get_expected_values()` (plural) should be overridden only when a check accepts multiple values; single-value checks should override `get_expected_value()` (singular). Because of the mismatch, consumers that call the singular form (e.g. fix-suggestion generators) receive `True` — the value the rule flags as non-compliant — instead of `False`.
This PR overrides `get_expected_value()` to return `False` and lets `get_expected_values()` inherit `[False]` from the base class, so both methods stay consistent. Adds a regression test asserting both return values.
Detection behavior is unchanged.

Fixes [XSUP-71484]([redacted-url])

## Checklist:

- [x] I have performed a self-review of my own code
- [x] I have commented my code, particularly in hard-to-understand areas
- [x] I have made corresponding changes to the documentation
- [x] I have added tests that prove my feature, policy, or fix is effective and works
- [x] New and existing tests pass locally with my changes

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
