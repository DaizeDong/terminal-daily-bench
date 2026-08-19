# improve evaluation speed for Min and Max with many arguments

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

#### References to other Issues or PRs

[redacted-ref] 

#### Brief description of what is fixed or changed

Min and Max are currently slow when called with many arguments, mostly because they require pairwise comparisons of all arguments. This PR improves speed by first splitting the arguments into constants, unconstrained symbols, and other values. This allows a fair bit of simplification before the full pairwise comparison, especially when many of the arguments are constants or unconstrained symbols.

I ran the following code on my Macbook before and after the change:
```python
import time

from [redacted-repo] import symbols, Min

start_time = time.time()
Min(*symbols(names='x:100'))
end_time = time.time()
print(f"Time taken: {end_time - start_time} seconds")
```
before: Time taken: 1.[redacted-sha] seconds
after: Time taken: 0.[redacted-sha] seconds

I also added a number of test assertions for Max/Min behavior I was concerned about, and added type annotations to the relevant files to make editing easier in my IDE.

#### Other comments

This is my first PR to [redacted-repo]! I've been a fan for years. I've tried to follow the guidance here and on the site but please tell me if I've done anything wrong and I'll correct it.

#### AI Generation Disclosure

The code and docstrings are human-written (as is this PR description). I used Claude 5 Opus and Grok 4.5 in Cursor to review my changes and suggest test cases.

#### Release Notes

<!-- BEGIN RELEASE NOTES -->
* functions
  * Sped up Max/Min by pruning the number of pairwise comparisons between arguments
<!-- END RELEASE NOTES -->

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
