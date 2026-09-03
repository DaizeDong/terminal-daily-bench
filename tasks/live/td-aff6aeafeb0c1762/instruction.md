# fix: point the Chunk error at group_cols, which exists

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Follow-up to [redacted-ref], which I merged before its review landed. Both points came from Copilot; I evaluated each rather than taking them as given.

## 1. The error named a method that does not exist (worth fixing)

The label-count message derived the method name from the word it had just printed:

```python
axis = "rows" if self.is_flank else "columns"
... f"in the same order as `group_{axis[:-1]}s`."
```

On rows that yields `group_rows`. On columns it yields `group_columns`, and the API is [`group_cols`]([redacted-url]). So a `Chunk` on top or bottom sent the reader to a method that is not there:

```
before:  `Chunk` on 'top' has 3 labels but the columns are in 2 groups.
         Give one label per group, in the same order as `group_columns`.   <- does not exist

after:   `Chunk` on 'top' has 3 labels but the columns are in 2 groups.
         Give one label per group, in the same order as `group_cols`.
```

That is precisely the failure [redacted-ref] set out to remove, so it earns the fix. Both names are now written out rather than computed.

I audited every other identifier the new messages mention (`add_top`/`add_bottom`/`add_left`/`add_right`, `ma.CatHeatmap`, `mp.Colors`, `cluster_data=`, `get_main_ax`, `get_plot_names`, `render`, `group_rows`): `group_columns` was the only broken one.

The new test follows whichever method the message names and asserts the board actually has it, so a future rename fails loudly instead of silently misdirecting:

```python
named = re.search(r"`(group_\w+)`", str(err.value)).group(1)
assert hasattr(ma.Heatmap, named), f"error points at {named}, which does not exist"
```

## 2. `list(cuts).count(c)` in a comprehension (taken, but not for the stated reason)

```python
-        repeated = sorted({int(c) for c in cuts if list(cuts).count(c) > 1})
+        values, counts = np.unique(cuts, return_counts=True)
+        repeated = [int(v) for v in values[counts > 1]]
```

The O(n²) claim is accurate, but `cuts` holds the cut positions of a heatmap, so n is single digits and the quadratic term buys nothing. Rebuilding a list inside the comprehension was just poor code, and `np.unique` on an array that is already a numpy array is shorter and clearer. Taking it as a readability change, not a performance one.

Output is unchanged, order included, since `np.unique` returns sorted values:

```
[4, 4]       -> Cannot cut rows at [4] twice, that would leave an empty group.
[3, 3, 7, 7] -> Cannot cut rows at [3, 7] twice, that would leave an empty group.
[2, 5]       -> ok
[99]         -> Cannot cut rows at [99], there are only 10 rows. Cuts go between 1 and 9.
```

## Verification

`706 passed, 6 xfailed` (704 from [redacted-ref] plus the two new parametrised cases).

🤖 Generated with [Claude Code]([redacted-url])

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
