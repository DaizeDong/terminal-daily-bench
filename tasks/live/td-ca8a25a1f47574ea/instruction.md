# [rollout] fix: continuous token fuse generation prompt with the final append group

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

### What does this PR do?

[redacted-ref].

`ContinuousTokenBuilder.tokenize_non_assistant_incremental_messages()` previously encoded the complete updated message history twice after every appended non-assistant group solely to derive the tokens added by `add_generation_prompt=True`. For long agent trajectories, this repeatedly processes the growing history and results in approximately O(N^2) tokenization work.

This PR changes the default behavior to fuse generation-prompt rendering into the final append group. The final group is rendered with `add_generation_prompt=True`, so its delta contains both the appended non-assistant messages and the following generation prompt. This removes the separate full-history generation-prompt render from the default path.

Some chat templates may derive their generation prompt from context that is not fully determined by the final append group. Model-specific builders can therefore opt out by returning `False` from `_should_fuse_generation_prompt_with_last_group()` and can preserve or implement their own behavior through `_tokenize_generation_prompt_delta()`.

### Test

- `test_default_builder_fuses_generation_prompt_into_last_append_group`: verifies that a final multi-message tool group performs only two bounded renders and that the second render uses `add_generation_prompt=True`.
- `test_default_builder_only_fuses_generation_prompt_into_final_append_group`: verifies that only the final group receives the generation prompt when multiple groups are appended.
- `test_special_builder_can_keep_separate_full_history_generation_prompt`: verifies that an opted-out builder still invokes `_tokenize_generation_prompt_delta()` and can retain the full-history false/true suffix-diff behavior.

And e2e trial that validates the perf gain is being produced. 

### Design & Code Changes
There is no change to the AgentLoop-facing runtime API. But only Developer extension APIs.
Changes are made as below
- Materialize append groups before tokenization so the final group can be identified.
- Pass `add_generation_prompt=True` only to the final append group on the default fused path.
- Extend `_tokenize_tool_group()` and `_tokenize_single_non_tool()` with an `add_generation_prompt` keyword argument and forward it to `render_delta_token_id()`.
- Add `_should_fuse_generation_prompt_with_last_group()` as a builder-level capability hook; the base implementation returns `True`.
- Preserve `_tokenize_generation_prompt_delta()` as the separate generation-prompt extension point for opted-out builders.
- Keep GPT-OSS and Gemma 4 on their existing model-specific separate paths.
- Add CPU unit tests for fusion, final-group selection, argument propagation, and the full-history fallback.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
