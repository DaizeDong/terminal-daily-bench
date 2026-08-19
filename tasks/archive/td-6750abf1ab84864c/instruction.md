# Update OnPolicyAlgorithmJax & PPO to support custom rollout_buffer_class

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

<!--- Provide a general summary of your changes in the Title above -->

## Description
Fixes [redacted-url]

Just a small add to support `rollout_buffer_class` and `rollout_buffer_kwargs` arguments in constructor of `PPO` and `OnPolicyAlgorithmJax`, like in Stable Baselines3.

## Motivation and Context
<!--- Why is this change required? What problem does it solve? -->
<!--- If it fixes an open issue, please link to the issue here. -->
<!--- You can use the syntax `[redacted-ref]` if this solves the [redacted-ref] -->
- [x] I have raised an issue to propose this change ([required]([redacted-url]) for new features and bug fixes)

## Types of changes
<!--- What types of changes does your code introduce? Put an `x` in all the boxes that apply: -->
- [ ] Bug fix (non-breaking change which fixes an issue)
- [x] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to change)
- [ ] Documentation (update in the documentation)

## Checklist:
<!--- Go over all the following points, and put an `x` in all the boxes that apply. -->
<!--- If you're unsure about any of these, don't hesitate to ask. We're here to help! -->
- [x] I've read the [CONTRIBUTION]([redacted-url]) guide (**required**)
- [ ] I have updated the changelog accordingly (**required**).
- [x] My change requires a change to the documentation.
- [x] I have updated the tests accordingly (*required for a bug fix or a new feature*).
- [ ] I have updated the documentation accordingly.
- [ ] I have reformatted the code using `make format` (**required**)
- [ ] I have checked the codestyle using `make check-codestyle` and `make lint` (**required**)
- [ ] I have ensured `make pytest` and `make type` both pass. (**required**)
- [ ] I have checked that the documentation builds using `make doc` (**required**)

Note: You can run most of the checks using `make commit-checks`.

Note: we are using a maximum length of 127 characters per line

<!--- This Template is an edited version of the one from [redacted-url] -->

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
