# fix: NaN padding, warning stacklevels, and Zero* data sources

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Three things that looked fine and said nothing. Each one is small; the first is the one that can put a wrong figure in a paper.

## 1. `annotate_stats` drew unlabelled brackets over NaN padding

Wide input has to be rectangular. Group sizes in single-cell data are never equal, so the short columns get padded with `NaN`. Seaborn already treats a padded slot as absent, but `observations()` handed the padding straight to the test:

```python
return frame.loc[keep, "value"].to_numpy()
```

scipy returns `pval=nan`, `PValueFormat.format_data` renders `""`, and [`draw_brackets`]([redacted-url]) draws the bracket regardless. The result is a figure that looks finished and says nothing, with no warning at any step.

Measured in a fresh env before the fix:

```
nan-padded -> pval nan | label ''
clean n=2  -> pval 0.1588 | label 'ns'
```

The padding never belonged in the test, so it is dropped there:

```python
return frame.loc[keep, "value"].dropna().to_numpy()
```

`.dropna()` rather than `values[~np.isnan(values)]`: no new import, and it does not raise `TypeError` if `pdata["value"]` ever lands on object dtype.

A group can still end up with nothing to test, and an empty label is the one failure a reader cannot see, so `annotation_texts` now says so:

```
UserWarning: 1 pair(s) produced no p-value and are drawn without a label: [(('a', 'WT'), ('a', 'KO'))]
```

The bracket keeps being drawn. `pvalue_thresholds` can be configured with a deliberately empty label, and dropping the bracket would remove one the caller asked for.

### Why padding, and not a ragged input path

Padding is not a workaround here, it is the correct representation, and I checked both halves of that claim.

Seaborn already agrees. Across all seven supported plotters, a padded column and an unpadded one produce identical artist extents:

```
barplot identical   boxplot identical   violinplot identical   stripplot identical
pointplot identical boxenplot identical swarmplot identical
```

And there is no unambiguous way to spell ragged input in the current API. `np.asarray([[1, 2, 3], [4, 5, 6]])` reads the outer list as **rows**, so auto-padding a ragged outer list as **columns** would silently flip orientation between the equal-length and unequal-length cases. A `dict` already means hue levels. The wide-format contract constrains columns only, because that is what has to match the main data for split and reorder; rows are free. Pandas already emits exactly the right thing and keeps the column labels the pairs are named with:

```python
pd.DataFrame({"A": pd.Series(a), "B": pd.Series(b)})
```

So this is documented in the plotter docstrings and the tutorial, and no input code changed.

## 2. Every warning blamed [redacted-repo] instead of the caller

Nine warnings carried a hand-counted `stacklevel`; two carried none. All eleven pointed at [redacted-repo]'s own internals. Measured: the four in the annotation path all resolved to `base.py:1610`, whatever constant they used, because the constants were counted for a chain that has since grown layers.

Counting frames by hand cannot survive a refactor, so `find_stack_level()` walks out of the package instead. It sits next to [`caller_location()`]([redacted-url]), which already walks the same stack against the same `_PKG_DIR`, and it uses `sys._getframe` for the same reason that one does:

```python
def find_stack_level():
    frame = sys._getframe(1)  # the warnings.warn() call site
    level = 1
    while frame is not None and frame.f_code.co_filename.startswith(_PKG_DIR):
        frame = frame.f_back
        level += 1
    return level
```

All eleven call sites use it now, the two bare ones included. Verified end to end, at depths from two frames to seven:

```
OK  blank label          -> where.py:24   1 pair(s) produced no p-value ...
OK  undodged             -> where.py:30   2 pair(s) compare hue levels ...
OK  unknown pair         -> where.py:36   1 pair(s) name a category ...
OK  obs_axis no source   -> where.py:47   obs_axis has no effect without ...
OK  pairs='all' dense    -> where3.py:23  pairs='all' on 9 categories ...
OK  crowded brackets     -> where3.py:23  20 rows of brackets do not fit ...
OK  deform deprecation   -> where3.py:26  Deformation.reorder_row is ...
OK  dense sparse         -> where3.py:29  Converting a sparse (30000, 30000) ...
```

`src/oncoprinter/core.py` is left alone: it is a separate top-level package, so a walk keyed on [redacted-repo]'s directory would stop at its own `warn` line and gain nothing.

## 3. The Zero* boards could not take a data source

`ZeroWidth`, `ZeroHeight`, `ZeroWidthCluster` and `ZeroHeightCluster` each override `__init__` and none of them carried `@accepts_source`, so all three ways in were broken and the first was silent:

```
before                                     after
ZeroHeight(adata, 2)          -> adata bound to `width`, no source   -> source bound
ZeroHeight(2, source=adata)   -> TypeError: unexpected keyword       -> source bound
ZeroWidthCluster(adata, A.X[:, :], 2)
                              -> ValueError from inside numpy        -> reference resolved
```

The decorator is all that was missing. References on their side plots resolve through the board now, the same as any other board:

```python
board = ma.ZeroWidth(adata, 3)
board.add_left(mp.Numbers(A.obs["score"]))
board.add_right(mp.Labels(A.obs.index))
board.render()
```

This is also why [redacted-ref] had to land with it rather than after. The `obs_axis` warning inside `accepts_source` was `stacklevel=2`, which only held while no decorated `__init__` nested inside another. Decorating the Zero* boards makes them nest, and the walk is what keeps that warning pointing at the caller.

## Tests

Nine new, `718 passed, 6 xfailed`, ruff clean.

- **Padding is not an observation.** A column padded to twice its length annotates the same as the unpadded one. Failed before the fix with `''` against `'****'`.
- **A group with nothing in it is reported**, and its bracket is still drawn.
- **Ordinary data reports nothing**, so the new warning cannot start firing on clean input. Uses the `simplefilter("error", UserWarning)` pattern already in this file.
- **A warning blames the line that asked for it**, parametrized over a two-frame chain and a three-frame one. I checked this is not vacuous: putting `stacklevel=2` back into `_deform.py` (right for the shallow case) fails the deep one.
- **`find_stack_level` stops as soon as it leaves [redacted-repo]**, called straight from the test file.
- **Each Zero\* board binds a source**, a `ZeroWidthCluster` takes a reference as its `cluster_data`, and a `ZeroWidth` resolves references on its side plots through to rendered artists.

🤖 Generated with [Claude Code]([redacted-url])

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
