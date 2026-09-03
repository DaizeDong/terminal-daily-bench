# fix(llm): suppress spurious "trying again" warning on the final retry attempt

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

generate_script and generate_terms guarded the "trying again…" log with if i < _max_retries:. Since the loop is for i in range(_max_retries), i maxes out at _max_retries - 1, making the condition always True — the misleading warning fired even on the last attempt when no retry would follow.

Changed the guard to if i < _max_retries - 1:, matching the identical pattern already present in generate_social_metadata (line 958). Added unit tests verifying the warning fires exactly _max_retries - 1 times when every attempt fails.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
