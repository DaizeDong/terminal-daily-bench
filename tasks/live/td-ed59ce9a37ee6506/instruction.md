# fix: report data errors where the mistake was made

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## The problem

Boards are built lazily, so every data check runs at `render()`, far from the line that got it wrong. Two blanket `except Exception` blocks then discarded the one useful thing in the error.

`Deformation` already raises precise messages. [`RenderPlan.get_render_spec`]([redacted-url]) caught them all and substituted `DataError("Please check your data input with Numbers at 'left'")`, dropping the original entirely (`except Exception as _`, no `from e`). `_render_plan` then re-wrapped that into a bare `Exception` whose message was the plotter's repr. Python prints the outermost exception last, so **the final line the user read was the only one that said nothing**:

```
Exception: An error occurred during rendering of Numbers(name='Numbers-left-[redacted-sha]', side='left', zorder=0)
```

39 traceback frames, and the user's own `add_left(...)` line appeared in none of them.

`check_length` in `_normalize.py` already fixed this for the AnnData reference path, and its docstring names the problem: *"Catches the mismatch where it happens instead of at render, where the error `Deformation` raises is swallowed twice before it reaches the caller."* The plain-array path, which is most usage, had no such check.

## After

```
ValueError: `Numbers` on 'left' has 12 values, but there are 10 rows. There are 12 columns, so try `add_top` or `add_bottom` instead.
```

Five frames, and the first is the caller's `add_left`.

## What changed

**Stop discarding the real error.** The blanket `except` in `get_render_spec` is gone. Both `_render_plan` implementations route each plan through `_render_with_context`, which uses `Exception.add_note` (3.11+, and the project already requires 3.11) so the original type, message and traceback all survive and gain two lines of context:

```
ValueError: `Chunk` on 'right' has 3 labels but the rows are in 2 groups. Give one label per group, in the same order as `group_rows`.
  while rendering Chunk on 'right'
  added at Cell In[2]:3
```

This also removes a latent bug: the old `except` read the loop variable `plan`, which is unbound if `get_main_ax()` raises with no side plans, masking the real error with `NameError`.

**Check shapes when the plotter is added.** `check_plot_data` runs from `add_plot` and `add_layer`, before the layout is touched, so a rejected plot leaves no orphan axes behind. To keep it from ever being stricter than the render, the "which axis does this data index" decision moved into `RenderPlan.data_axis`, and `get_deform_func` now dispatches on that same method. A length matching the other axis is called out, since that is nearly always a plot put on the wrong side.

**Record the call site.** Under Jupyter and marimo a cell compiles from a throwaway path such as `/tmp/ipykernel_913/[redacted-sha].py`, which tells the reader nothing, so those are resolved to `Cell In[3]:12` and `marimo cell Hbol:12`. Both lookups are guarded: if either tool changes shape, the note falls back to the raw path and the underlying error is untouched. Nothing imports IPython or marimo; `sys.modules` is probed, the way `_sources.py` already detects its data containers.

**Four other messages**, each reproduced against `main`:

| | before | after |
|---|---|---|
| text into `Heatmap` | `_UFuncNoLoopError: ufunc 'fmin' did not contain a loop with signature matching types (dtype('<U1'), ...)` | `Heatmap needs numbers, but this data is text (dtype <U1). Use ma.CatHeatmap for categories, or pass cluster_data= to cluster on something numeric.` |
| `get_ax('typo')` | `KeyError: 'typo'` | `No axes named 'typo'. Named axes on this board: 'bars'. The main canvas is get_main_ax().` |
| `cut_rows([99])` on 10 rows | **no error at all**, silently wrong | `Cannot cut rows at [99], there are only 10 rows. Cuts go between 1 and 9.` |
| `Chunk` label count | `You have 2 axes but you only provide 3 texts.` | `Chunk on 'right' has 3 labels but the rows are in 2 groups. Give one label per group, in the same order as group_rows.` |

## Verification

The risk here is the add-time check rejecting something the render accepts, so it was dry-run first, recording instead of raising, across the whole suite and the example scripts: **zero false positives**.

- `672 passed, 6 xfailed` before, `672 passed, 6 xfailed` after excluding the new tests. No regressions.
- `704 passed` with the 32 new tests in `tests/test_errors.py`.

Notes render in every environment checked, each tested rather than assumed, since display depends on the traceback formatter rather than on `add_note` itself:

| environment | call site reads |
|---|---|
| script, pytest | `/path/plot.py:14` |
| IPython terminal | `Cell In[1]:3` |
| Jupyter (real ipykernel) | `Cell In[2]:3` |
| marimo, notebook as script | `/path/nb.py:16` |
| marimo interactive kernel | `marimo cell Hbol:3` |

marimo formats through stdlib `traceback`, including its short-message path, which keeps notes via `format_exception_only`; verified against marimo's own renderer, not only a script run.

No new public API and no changes to `exceptions.py`.

🤖 Generated with [Claude Code]([redacted-url])

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
