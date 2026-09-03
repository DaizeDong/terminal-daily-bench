# fix(mastery): don't freeze choice gates on clarifying composer text

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary
- Skip persisting unreadable composer text as a choice answer on `ask_user` resume, so clarifying questions leave the interaction awaiting instead of answered.
- If an interaction is already stuck with an unreadable `user_answer`, allow a later readable pick to overwrite and grade successfully.
- Keep readable composer picks (`A` / option body) and non-choice answers behaving as before.

[redacted-ref]

## Test plan
- [x] `pytest tests/capabilities/test_mastery_capability.py -k clarifying`
- [x] `pytest [redacted-repo]/learning/tests/test_mastery_tools.py -k recovers_unreadable`
- [ ] Repro from [redacted-ref]: clarifying composer text stays awaiting; later `A` grades cleanly
- [ ] Card taps still commit and grade as before

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
