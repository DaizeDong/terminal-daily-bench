# Support REGEXP BINARY

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

# Thanks for contributing!

Before submitting your pull request please have a look at the
following checklist:

- [x] ran the tests (`pytest`)
- [x] all style issues addressed (`flake8`)
- [x] your changes are covered by tests
- [x] your changes are documented, if needed

We use Django 4.2 and require [redacted-repo] for parsing the SQL Query. (As part of the djongo library, we migrated to latest django version)
Now we got an error, by using case sensitive regex filter like "columnname REGEXP BINARY 'static.+[0-9]+'
I wasn't aware of such operator, but it exists and is used by Django, when regex must be case sensitive.

So I prepare a PR to implement support for this compare operator.
I'm not fully sure about the "\b" at the end, but it was there and probably it prevents to recognize something like "REGEXP binarystring" as operator. (Also when it isn't valid sql)

I'm open to adjust when something feels strange.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
