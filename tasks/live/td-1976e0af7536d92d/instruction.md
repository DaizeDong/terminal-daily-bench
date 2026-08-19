# fix: resolve fewshot gen_prefix against the fewshot doc, not the eval doc

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

In `ConfigurableTask.fewshot_context`, the few-shot loop resolves every per-document field against `fs_doc`, the few-shot document being rendered, except `gen_prefix`, which is resolved against `doc`, the evaluation document:

```python
q, c, a = (
    self.doc_to_text(fs_doc, self.fewshot_cfg.doc_to_text),
    self.doc_to_choice(fs_doc, self.fewshot_cfg.doc_to_choice) if ... else None,
    self.doc_to_target(fs_doc, self.fewshot_cfg.doc_to_target),
)
_gen_prefix = self.resolve_field(doc, self.fewshot_cfg.gen_prefix)   # <-- doc, not fs_doc
```

`resolve_field` either looks the name up as a column on the doc it is handed or renders it as a Jinja template against that doc, so whenever `gen_prefix` is document-specific rather than a fixed literal, every few-shot demonstration is built with the evaluation item's prefix. The question under test is spliced into the demonstrations that are supposed to be independent of it.

The one-character-per-word fix is to pass `fs_doc`.

## Affected tasks in this repo

`FewshotConfig.from_dict` inherits `gen_prefix` from the parent `TaskConfig`, so this reaches any task that sets a document-dependent `gen_prefix` at the top level and is then run with `num_fewshot > 0`:

- `lm_eval/tasks/ruler/niah_single_1.yaml` sets `gen_prefix: "{{gen_prefix}}"`, a per-document column. `lm_eval/tasks/ruler/prepare_niah.py` builds that column as

  ```python
  "gen_prefix": f"The special magic {type_needle_v[:-1]} for {query} mentioned in the provided text is"
  ```

  so the prefix embeds the document's own `query`, the needle key being retrieved. Resolving it against the eval doc means every few-shot demonstration asks for the key under test. For a needle-in-a-haystack task that is the worst possible field to share between the shots and the item, since the shot's answer is then presented next to the eval item's query.
- `lm_eval/tasks/humaneval/humaneval_instruct.yaml` and `humaneval_64_instruct.yaml` set `gen_prefix: "Here is the completed function:\n```python\n{{ prompt }}\n"`. The evaluated function signature and docstring are pasted into every shot.

`lm_eval/tasks/ruler/vt_utils.py` builds a per-document `gen_prefix` the same way, so the other RULER generators are one YAML change away from the same behaviour.

For a task whose few-shot split has a different schema from its test split, `apply_template` silently renders the missing field as empty instead, which is a quieter version of the same problem.

## Why the existing test did not catch it

`test_gen_prefix_in_fewshot` sets `fewshot_cfg.gen_prefix = "Answer:"`, a fixed literal, and stubs `resolve_field` with `lambda doc, val: val`. Both choices make the doc argument irrelevant, so the assertion holds either way.

## Tests

Two regression tests are added, covering the two shapes `resolve_field` supports, and both use the real `resolve_field` so the document that is passed in actually matters:

- `test_fewshot_gen_prefix_resolved_against_fewshot_doc`: `gen_prefix` is a column name. Asserts the shot carries its own prefix, that the eval prefix does not appear attached to the shot's answer, and that the final turn still ends with the eval prefix.
- `test_fewshot_gen_prefix_template_resolved_against_fewshot_doc`: `gen_prefix` is a Jinja template shaped like HumanEval's. Asserts the shot renders its own `prompt` and that the evaluated `prompt` does not leak in.

## Verification

Verified against the base ref rather than by stashing:

```
# fix present
$ pytest tests/test_fewshot_context.py -q
51 passed

# source reverted to upstream/main, new tests kept
$ git checkout upstream/main -- lm_eval/api/task.py
$ pytest tests/test_fewshot_context.py -q
2 failed, 49 passed
FAILED ...::test_fewshot_gen_prefix_resolved_against_fewshot_doc
FAILED ...::test_fewshot_gen_prefix_template_resolved_against_fewshot_doc
AssertionError: assert 'Code:\ndef shot():\n' in 'Q1 Code:\ndef evaluated():\nA1\n\nQ2'
```

The failure message shows the leak directly: the shot rendered `def evaluated():`, the item under test, instead of its own `def shot():`.

Also confirmed end to end with a RULER-shaped config, where the rendered prompt goes from

```
FS_Q The magic number for EVAL is FS_A

EVAL_Q The magic number for EVAL is
```

to

```
FS_Q The magic number for FEWSHOT is FS_A

EVAL_Q The magic number for EVAL is
```

Broader suite on CPU, 393 passed in two batches:

- 207 passed across `test_fewshot_context`, `test_samplers`, `test_prompt`, `test_filters`, `test_metrics`, `test_misc`, `test_registry`, `test_aggregation_pipeline`, `test_evaluator_utils`.
- 186 passed across `test_task_manager`, `test_group`, `test_cli_subcommands`.

`test_utils` was skipped locally only because it imports torch, which is not installed on this machine.

Formatted with the pinned `ruff` 0.15.12 from `.pre-commit-config.yaml`. Note that `lm_eval/api/task.py` already fails `ruff format --check` on `main` at an unrelated block near `_compute_task_aggregations`, so that pre-existing reformatting is deliberately left out of this diff to keep it minimal.

## Note on this line's history

The line was introduced by [redacted-ref], the hotfix for [redacted-ref], whose stated purpose was that `fewshot_config` was not being applied to fewshot docs. That change switched this loop over to `fs_doc`, so passing `doc` for `gen_prefix` alone looks like a slip rather than an intent.

I did not find an existing issue reporting this, so there is nothing to link. Happy to open one first if you would prefer the report and the fix tracked separately.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
