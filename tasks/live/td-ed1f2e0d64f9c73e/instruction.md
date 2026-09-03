# Fix DatasetDict.push_to_hub leaving removed splits in the dataset card

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Pushing a `DatasetDict` that drops a split leaves the repo unloadable:

```python
DatasetDict({"train": ds_train, "test": ds_test}).push_to_hub("user/repo")
DatasetDict({"train": ds_train}).push_to_hub("user/repo")   # "test" is gone

load_dataset("user/repo")
# ValueError: Couldn't infer the same data file format for all splits.
# Got {'train': ('parquet', {}), 'test': (None, {})}
```

## Context

Two things matter here:

- `configs.data_files` paths are **globs**, and every split listed there must expand to real files at load time.
- `DatasetDict.push_to_hub` **replaces** the split set: any split not in the dict has its parquet files deleted from the repo, and the card is rewritten with `remove_other_splits=True`. (`Dataset.push_to_hub` only appends, and passes `remove_other_splits=False`.)

After the second push above, the card's YAML header looks like this:

```yaml
configs:
- config_name: default
  data_files:
  - split: train
    path: data/train-*
  - split: test           # <-- stale: this push just deleted these files
    path: data/test-*
dataset_info:
  splits:
  - name: train           # <-- dataset_info correctly dropped "test"
```

`data/test-*` now matches no files, so `load_dataset` can't infer a format for `test` and fails.

## Root cause

`remove_other_splits=True` was only honored for the `dataset_info` block. The `configs.data_files` block was rebuilt like this:

```python
data_files_to_dump = sanitize_patterns(metadata_config["data_files"])  # start from the old card
for split_info in splits_info:                                         # then add this push's splits
    data_files_to_dump[split_info.name] = [f"{data_dir}/{split_info.name}-*"]
```

Splits are only ever **added** to that dict — nothing removes one, so `test` survives from the old card even though this push deleted its files.

## Fix

When `remove_other_splits=True`, don't seed from the old card — start empty so the patterns describe exactly the splits this push wrote.

```python
if "data_files" in metadata_config and not remove_other_splits:
```

`Dataset.push_to_hub` is unaffected — it stays on the additive path and keeps whatever the card already lists.

## Tests

Two hermetic tests in `tests/test_buckets.py` (in-memory filesystems, no Hub), alongside the existing `_get_updated_dataset_card` test:

- `test_get_updated_dataset_card_drops_removed_splits_when_replacing_split_set` — verified to fail before the fix. Asserts both blocks agree, since it's the disagreement that breaks loading.
- `test_get_updated_dataset_card_keeps_existing_splits_when_appending` — pins the additive `remove_other_splits=False` path so `Dataset.push_to_hub` doesn't regress.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
