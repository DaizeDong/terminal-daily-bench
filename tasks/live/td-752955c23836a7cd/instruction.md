# Fix TCN tuple schema unwrap

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

**Issue**

TCN.forward passed the raw kwargs dict straight to the embedding model (tcn.py:309). Tuple-schema features such as StageNetProcessor arrive as a tuple (time, value), so the embedding model received a tuple and crashed with "'tuple' object has no attribute 'to'". Every sibling sequence model (RNN, CNN, MLP, Transformer, Deepr, MICRON) unwraps the tuple and extracts the value tensor first, so TCN alone was broken for these inputs.

**Fix**

Before calling the embedding model, TCN now builds an inputs dict by extracting the "value" tensor (and optional "mask") from each feature using the processor's schema(), mirroring RNN. Plain tensor features are wrapped as a one-element tuple so the same schema lookup applies. This leaves the existing sequence/tensor behavior unchanged (their schema is ("value",)) while fixing tuple-schema features.

**Notes**

Added regression test test_model_with_stagenet_tuple_feature in tests/core/test_tcn.py.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
