# [ckpt, fsdp] fix: FSDP model merger concatenates replicated buffers

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

### What does this PR do?

FSDPModelMerger treats every non-DTensor entry in a rank's checkpoint as a row-shard and torch.cat(dim=0)s it across ranks. FSDP2 never shards buffers, so each rank holds an identical copy, and merging a model with persistent buffers goes wrong in two ways:

  - 0-d buffers crash the merge: RuntimeError: zero-dimensional tensor (at position 0) cannot be concatenated
  The error this had yielded is: 
```bash
File "[redacted-repo]/model_merger/fsdp_model_merger.py", line 202, in _load_and_merge_state_dicts
      state_dict[key] = torch.cat(state_dict[key], dim=0)
  RuntimeError: zero-dimensional tensor (at position 0) cannot be concatenated
```
  - ≥1-d buffers are silently corrupted: a (1,) buffer becomes (8,) on 8 ranks, producing an HF checkpoint with wrong-shaped tensors.

This happened during conversion of `google/gemma-4-E4B-it` FSDP2 checkpoints

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
