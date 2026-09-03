# give a better error if collation functions fails

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Change Description
currently, if there's an issue with the default collation function, `[redacted-repo]` will send an error message saying there was a problem with the "custom" collation function, even if the user doesn't provide one. I changed the error message to specify the collation function name so that it's more readable/less confusing for the user.

## Code Quality
- [x] I have read the Contribution Guide and agree to the Code of Conduct
- [x] My code follows the code style of this project
- [x] My code builds (or compiles) cleanly without any errors or warnings
- [x] My code contains relevant comments and necessary documentation

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
