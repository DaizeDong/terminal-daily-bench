# feat: q to bool

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

<!--- Provide a general summary of your changes in the Title above -->

## Description
<!--- Describe your changes in detail -->
Added `__bool__` support to the `Q` class, allowing `Q` objects to be evaluated in a boolean context.

A `Q` object is considered truthy if it contains any filters or any non-empty children. An empty `Q()` with no filters and no children evaluates to `False`.

## Motivation and Context
<!--- Why is this change required? What problem does it solve? -->
<!--- If it fixes an open issue, please link to the issue here. -->
Previously, all `Q` instances were truthy by default (standard Python object behavior), making it impossible to distinguish between an empty `Q()` and a meaningful one. This change enables natural boolean checks like `if q:` to guard against applying empty query conditions.

## How Has This Been Tested?
<!--- Please describe in detail how you tested your changes. -->
<!--- Include details of your testing environment, and the tests you ran to -->
<!--- see how your change affects other areas of the code, etc. -->
Added `test_q_to_bool` covering four cases:

`Q(row="data")` - truthy (has filters)
`Q()` - falsy (no filters, no children)
`Q(Q(row="data"), Q(row="data"))` - truthy (has non-empty children)
`Q(Q(), Q())` - falsy (all children are empty)

## Checklist:
<!--- Go over all the following points, and put an `x` in all the boxes that apply. -->
<!--- If you're unsure about any of these, don't hesitate to ask. We're here to help! -->
- [x] My code follows the code style of this project.
- [ ] My change requires a change to the documentation.
- [ ] I have updated the documentation accordingly.
- [ ] I have added the changelog accordingly.
- [x] I have read the **CONTRIBUTING** document.
- [x] I have added tests to cover my changes.
- [x] All new and existing tests passed.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
