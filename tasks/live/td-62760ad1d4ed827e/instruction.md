# fix: render nested StackBoard boards in place

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## The bug

A `StackBoard` of `StackBoard`s drew every heatmap on top of the others at full figure size. The tutorial's "Grid of heatmaps" example rendered as a single purple heatmap with visible ticks instead of a 2×2 grid:

```
figsize [2.2 2.2]  n_axes 8              <- should be 4
0 [0.000, 0.545, 0.455, 0.455] []        <- correctly placed, EMPTY -> the visible ticks
1 [0.545, 0.545, 0.455, 0.455] []
2 [0.000, 0.000, 1.000, 1.000] ['Reds']  <- all four full-figure, stacked
3 [0.000, 0.000, 1.000, 1.000] ['Greens']
4 [0.000, 0.000, 0.455, 0.455] []
5 [0.545, 0.000, 0.455, 0.455] []
6 [0.000, 0.000, 1.000, 1.000] ['Blues']
7 [0.000, 0.000, 1.000, 1.000] ['Purples'] <- last one wins visually
```

Nothing was shared between the colormaps — it was pure axes overlap.

## Root cause

`_copy_board` deep-copies `board.layout` but shallow-copied the nested board list:

```python
new.layout = deepcopy(board.layout)              # fresh child layouts
...
if hasattr(board, "_board_list"):
    new._board_list = list(board._board_list)    # same child boards
```

A copied group board therefore kept the original children, whose `.layout` was the pre-copy object that never entered the frozen tree. The parent positioned the copies (the four empty axes); each child then froze its orphan layout with `figsize=None` and `anchor=(0, 0)`, landing at `(0, 0, 1, 1)`.

Flat `StackBoard` worked because there the child's `.layout` *is* the object handed to `StackCrossLayout`.

## The fix

`_copy_board` now takes the sub-layout a child should be bound to, and a group board copies its children against the layouts that already live in its own freshly copied tree:

```python
new._board_list = [
    _copy_board(child, layout=sub)
    for child, sub in zip(board._board_list, sub_layouts, strict=True)
]
```

Plotters stay shared by reference. That is deliberate and required by [redacted-ref]: deep-copying them drags in the live matplotlib artists a rendered plotter keeps — a `Bar` plotter holds its `BarContainer`, and any categorical axis holds a `category.UnitData` wrapping an `itertools.count`, which is not copyable on Python 3.14+. The `hasattr` ladder is collapsed into one loop over a named tuple of attributes, so the shared-vs-copied contract is stated in one place.

## Also in this PR

- **`_GroupBoard`**, shared by `CompositeBoard` and `StackBoard`, replaces ~90 duplicated lines and fixes the drift between them: `CompositeBoard.render` and `save` now return `self`, as does `StackBoard.set_margin`, and `StackBoard.save()` before `render()` no longer raises `AttributeError` for a missing `figure` attribute.
- **Freeze/draw split.** Drawing moves out of `render` into `_draw`, so a group board freezes the whole layout tree once instead of every child re-freezing its own and `initiate_axes` removing and re-adding each axes. On a six-board stack (heatmap + dendrogram + title each) axes creation drops from **48 calls to 24** and render from **0.131 s to 0.078 s**, with identical output. `ClusterBoard.render` collapses into `_freeze_flex_plots` + `_draw`.
- **Both `figsize was not set by parent` fallbacks are gone.** They were added in the same commit that introduced this bug ([redacted-ref]) and only masked it. Instrumented over the suite, no layout now reaches `freeze` with `figsize` unset; without them a future linkage break raises instead of silently drawing in the wrong place.
- **Three `StackCrossLayout` defects**, all reproduced first:
  - legend axes were placed outside the figure on every side (`side="right"` put them at `[1.0, 0.0, 0.51, 1.0]`; only `save()`'s `bbox_inches="tight"` hid it);
  - `align="center"` overflowed to `x0=-0.308` for a board with a wide one-sided companion plot, because the bbox was sized by `max(bbox)` while each board is anchored by its main canvas;
  - the legend rect used a `main_anchor` computed before the anchors were offset.
- `StackBoard([])` now raises a clear `ValueError` instead of failing later inside numpy.

## Tests

The three existing `StackBoard` tests only asserted that `render()` did not raise — exactly what the bug did, which is how [redacted-ref] shipped this. They now assert geometry, colormaps, legend placement and figure containment.

Seventeen new tests, all failing against the previous code (`test_stack_nested` fails with `assert 8 == 4`). `test_stack_after_render` is the StackBoard side of [redacted-ref]'s `test_composite_after_render`: it stacks and nest-stacks boards that were already rendered and carry a categorical axis.

Verified with CI's own command (`uv sync --dev && pytest tests/`) on **Python 3.14 and 3.12: 616 passed, 6 xfailed** each. `ruff check` and `ruff format` clean.

## Docs

`stack.rst`'s `.. warning:: still considered experimental ... issues with the rendering` was describing these bugs, so it is replaced with the one real remaining limitation: `get_ax` / `get_main_ax` only reach boards stacked directly, not those inside a nested stack (nested layouts are keyed by an internal `uuid4().hex`). That behaviour is unchanged here.

Worth knowing: `stack.rst` has exactly eight `.. plot::` directives, so `stack-8.png` — the broken grid — is the tutorial card thumbnail in `docs/source/tutorial/index.rst`. The docs were rebuilt with no sphinx errors and it is now the correct 2×2 grid.

## Follow-ups in this PR

**Per-board legends (Copilot review).** With `keep_legends=True` the group board froze only its own legend before freezing the tree, so a child never got a legend axes and `_draw` crashed in `_render_legend`. `_freeze_legend` now recurses into the boards. Since a legend is an ordinary side cell, doing it in that order also makes the stack leave room for it — before, one child legend overlapped the next board and the last was placed entirely outside the figure.

**`CompositeBoard` can now be stacked.** `ma.StackBoard([h1 + h2, h3 + h4])` used to raise `AttributeError: 'CompositeCrossLayout' object has no attribute 'remove_legend_ax'`. `StackCrossLayout` drives its children through the `CrossLayout` API and `CompositeCrossLayout` implemented only part of it, so the rest is filled in: `remove_legend_ax`, `set_figsize`, `get_main_width`/`get_main_height`, a `name` for the layout mapper, an anchor that `freeze` actually honours (`set_anchor` used to forward to the main layout and then be ignored), and an `is_composite` guard on `set_size_inches` so a nested composite no longer resizes the figure its parent owns.

Verified across directions, all six align modes, composites carrying side plots, a stack holding a composite *and* a nested stack *and* a plain board, group-level legends, composites keeping their own legend, and numeric pad appends — no axes clipped or overlapping in any of them. The reverse direction is unchanged and still raises `Cannot append object type of StackCrossLayout`, now pinned by a test.

## Out of scope, spotted while confirming the above

- `add_layer` never sets `plot._registered`, unlike `add_plot`, so one plotter object can be silently shared by two boards. (Partly addressed by [redacted-ref]; worth a look.)
- Appending a `StackBoard` to a `CompositeBoard` (`h + stackboard`) is still unsupported. It needs `main_cell` and `set_main_width`/`set_main_height` on `StackCrossLayout`, plus a decision on what "align to the main canvas" means for a stack.

🤖 Generated with [Claude Code]([redacted-url])

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
