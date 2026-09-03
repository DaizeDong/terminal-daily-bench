# [data] add minicpm5 template with XML tool calling

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

# What does this PR do?

Adds a `minicpm5` chat template and the matching XML tool-calling format, and points the MiniCPM5 model group at it.

MiniCPM5 is currently registered with `template="empty"`. That is not a delegation to the tokenizer's own `chat_template.jinja` — `empty` is a real, empty template: bare `{{content}}` slots, no role markers, no EOS replacement, and tools falling back to ReAct `Action:` / `Action Input:`. Training under it silently produces a token layout the model has never seen.

## Changes

- `data/tool_utils.py` — `MINICPM5_TOOL_PROMPT` + `MiniCPM5ToolUtils`, registered as `"minicpm5"` in `TOOLS`
- `data/template.py` — register the `minicpm5` template (`ReasoningTemplate`, `replace_eos=True`, `stop_words=["<|im_end|>"]`), plus a two-line fix in `Template._encode` (see below)
- `extras/constants.py` — `template="empty"` → `"minicpm5"`
- `README.md` / `README_zh.md` — template column for MiniCPM 4/5
- `tests/data/test_formatter.py` — 11 new tests, no network required

## Correctness

Verified against `openbmb/MiniCPM5-1B`'s own `chat_template.jinja` on 300 real tool-calling samples: the rendered prompt is byte-identical to `apply_chat_template(history, add_generation_prompt=True, enable_thinking=False)` in all 300, with and without a system message.

Tests are formatter-level rather than `_check_template`-style. MiniCPM5's jinja does not emit the empty `<think></think>` block for a non-CoT assistant turn — unlike Qwen3's, which is why `test_qwen3_template` can use `_check_template` — so a plain `apply_chat_template(messages)` round trip does not apply here.

## Why `template: empty` is not a working alternative

Controlled A/B on `openbmb/MiniCPM5-1B`: identical data (3000 tool-calling samples), hyper-parameters and seed, `template` the only variable, `empty` run against an unmodified upstream checkout. Full fine-tuning, 200-sample held-out set:

| template               | parseable | function name | arguments exact |
| ---------------------- | --------- | ------------- | --------------- |
| *(untrained baseline)* | 99.0%     | 98.5%         | 79.5%           |
| `empty`                | **33.0%** | **33.0%**     | **17.5%**       |
| `minicpm5`             | **100%**  | **100%**      | **83.0%**       |

McNemar (paired, n=200): baseline → `empty` is 2 better / 126 worse (z=10.87, p<0.01); `empty` → `minicpm5` is 132 / 1 (z=11.27, p<0.01); baseline → `minicpm5` is not significant.

Trained under `empty`, the model learns the ReAct serialization and at inference emits only the `Action Input:` half, dropping the function name entirely — hence 98.5% → 33.0%.

Two reasons this has gone unnoticed: **LoRA masks it** (r=16 gives 98.5% function name, statistically indistinguishable from the untrained baseline; 81% of outputs are byte-identical to it), and **eval loss gives no warning** (0.0519 vs 0.0469 — an 11% gap alongside a 4.7x capability gap).

## Note on `_encode`

`MINICPM5_TOOL_PROMPT` starts with `\n\n` to separate itself from a user-supplied system message, matching the model's jinja. `Template._encode` therefore needs to strip it when there is no system message:

```python
if tools and not system:
    tool_text = tool_text.lstrip("\n")
```

`MossVLTemplate._encode` already carries these exact two lines — the same issue was previously worked around by duplicating the whole method into a subclass.

Hoisting it to the base class touches the 14 templates whose tool prompt starts with a newline *and* which have no `default_system` (`qwen3*`, `glm4_moe`, `glm4_7`, `glm4_5v`, `keye_vl`, `moss_vl`), and for them it is a fix rather than a behaviour change: `qwen3` with tools and no system message rendered `<|im_start|>system\n\n\n# Tools` where its own jinja emits `<|im_start|>system\n# Tools`. Both now agree, and the full `tests/data/` suite passes unchanged (128 passed, 6 skipped, 3 xpassed).

## Before submitting

- [x] Did you read the [[contributor guideline]([redacted-url])]([redacted-url])?
- [x] Did you write any new necessary tests?

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
