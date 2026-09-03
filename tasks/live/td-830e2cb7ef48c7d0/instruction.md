# fix(module): accept functools.partial as forward in spawn workers ([redacted-ref])

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

addresses - [redacted-url]
and also a pre-commit failure unrelated to this PR.

Module bound the user-supplied forward as types.MethodType(fn, self). multiprocessing's bound-method reducer reads __func__.__name__ to round-trip via getattr — callables without __name__ (notably partial) crashed spawn-mode DataLoader workers with AttributeError.

Wrap forward with _NamedForward when __name__ is missing. No effect on regular function forwards.

## Description

<!--- What types of changes does your code introduce? -->

<!--- Please link to an existing issue here if one exists. -->


## Checklist

<!-- - Go over all the following points, and put an `x` in all the boxes that apply. -->

- [ ] I have read the [**Contributing**]([redacted-url]) document.
- [ ] The documentation is up-to-date with the changes I made (check build artifacts).
- [ ] All tests passed, and additional code has been **covered with new tests**.
- [ ] I have added the PR to the [**RELEASES.rst**](../RELEASES.rst) file.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
