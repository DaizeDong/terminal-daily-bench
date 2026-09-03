# UID type validation

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

### Description

Users should be able to rely on `ss.uids()` instances being able to index states. However, this requires that they must contain integers. Previously the constructor partially accounted for this by casting inputs to integers. However, this validation does not apply when performing operations like

```
> ss.uids([1,2,3]) | []
uids([1., 2., 3.])
```

which returns UIDs instance that contains `float` values. Similarly, `ss.uids([np.inf])` fails (correctly) but `ss.uids([1,2,3]) | [np.inf]` does not. This PR implements a single entry point for type conversion and validation and then uses it for construction and as part of method calls to more consistently ensure that `ss.uids()` always maintain an integer type. 

One change in this PR is that conversion of fractions like `1.5` now fails e.g., previously `ss.uids([1.5])` returned `uids([1])` but now it will raise a `TypeError`. The thinking is that most of the time if fractional values have been passed into `ss.uids` this probably reflects an error and passing an inappropriate variable into `ss.uids`. If it's intentional, the user simply needs to round or convert the values before constructing `ss.uids()`. For convenience, if the input is `float` but all of the values are integers, the input will be allowed e.g., `ss.uids([1.0])` is allowed)

### Checklist
- [x] All new functions have a docstring and are appropriately commented
- [x] New tests were needed and have been added, or no tests required
- [x] Changelog has been updated, or there are no user-facing changes

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
