# Add ResMLP architecture and multi-output (Q-) models

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

PR3 of the [redacted-repo] integration series (base = `feat/score-children-contract` from [redacted-ref]; Draft until that one is merged).

`ModelConfig.n_outputs`, added in [redacted-ref] together with the `score_children` contract, was accepted by the config but no model could be built with it. This PR adds such models.

## What is added

- **`MlpModel` with `n_outputs > 1`.** For `n_outputs=1` keys and shapes of its state dict are exactly as before, so weights of pretrained models from `PREDICTOR_MODELS` still load — pinned by `test_mlp_state_dict_is_backward_compatible` and by `models_lib_test.test_loads_predictor_models` (green, downloads real Kaggle weights).
- **`ResMlpModel`** (model type `"RESMLP"`, registered in `ModelConfig.build_model`): residual blocks of Linear+LayerNorm+ReLU followed by a linear output layer. `layers_sizes` describes the blocks: there are `len(layers_sizes)` of them, and i-th one has `layers_sizes[i]` neurons. A block adds its input to its output, except blocks that change the number of features (e.g. the first one, which consumes the one-hot encoded state) — so `layers_sizes=[512, 512, 512]` is one projection plus two residual blocks. Deep MLPs with skip connections are easier to train, which matters for the trainer coming later in the series.
- **Fast path in `Predictor.score_children`.** When the model declares `n_outputs == n_generators` (a Q-model), children of a state are scored by one forward pass on the parent, instead of one pass per child — `n_generators` times fewer model evaluations. Dispatch uses the `n_outputs` attribute of the model, which models built by `ModelConfig.build_model` set automatically; this is the semantics documented for `ModelConfig.n_outputs` in [redacted-ref].

## Notes

- Weights are here: [redacted-ref] registers a `ResMlpModel` Q-model for "lrx-14", trained with the trainer ([redacted-ref], [redacted-ref]), in `PREDICTOR_MODELS` — it solves 50 out of 50 random states at beam width 1000, where the Hamming heuristic solves none. So this is not dead code.
- Scope deviation from the plan: `predictor.py` had to be touched too, because `score_children` (where the fast path belongs) lives there.
- One existing test changed meaning: `test_score_children_rejects_2d_output` asserted that a multi-output model cannot score children — exactly the limitation this PR lifts. It is replaced by `test_score_children_rejects_wrong_number_of_outputs` (`n_outputs` mismatching the graph) plus tests of the new path.

## Tests

12 new tests: output shapes for both architectures with 1 and 3 outputs, state dict compatibility, skip connections (a block with zeroed weights is the identity function), invariance to batch size, checkpoint round-trip for both types, per-column equality of the fast path and the default path (Hamming Q-model vs the `"hamming"` heuristic, plus an assertion that the model was called once), Q-model built from a config, and errors for non-positive `n_outputs`, empty `layers_sizes`, `n_outputs` mismatching the graph, and output shape contradicting the declared `n_outputs`.

`./lint.sh` green (black, pylint 10.00/10, mypy), `black --check .` green, `docs/build_docs.sh` (`-W`) green, `RUN_SLOW_TESTS=1 pytest` = 335 passed / 12 skipped / 3 xfailed on Python 3.12 (torch 2.13) and on Python 3.9 (torch 2.8).



---

Based on [redacted-ref], which is the base branch of this PR, so this diff is only its own change. [redacted-ref] should be merged first.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
