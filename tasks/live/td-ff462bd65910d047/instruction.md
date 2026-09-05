# Make linearization a query and add system level to_statespace()

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Makes linearization a query that returns matrices instead of a mode the system
is switched into, and builds the system level assembly on top of it. Design
discussed in [redacted-ref].

## Changes

**`Block.to_statespace(t)`** returns the local `(A, B, C, D)` in the current
operating point. Pure query, the block keeps evaluating its original functions.
Reads the Jacobians from the existing `Operator.jac` / `DynamicOperator.jac_x` /
`.jac_u`, which never needed the mode switch. `Integrator` and `ODE` override it
with their exact models instead of being differenced numerically.

**`Block.linearize(t)`** does what it always did and additionally returns the
matrices it computes anyway. The return value was `None`, so nothing breaks.

**Blocks without a valid linear model raise** `LinearizationError`, declared
through a `linearizable` class attribute: `Comparator`, `Relay`, `Switch`, `RNG`,
`Counter`, the `Logic` blocks, the discrete time blocks, `ADC`/`DAC` and `Delay`.
This means `Simulation.linearize()` now raises on a system containing one of
these where it previously succeeded silently. That is intended -- a "linearized"
system with a relay in it was never linear.

**`Simulation.to_statespace(inputs, outputs, t=None)`** assembles the global
model and returns a `StateSpace` block. The assembly stacks the local models
block diagonally and eliminates the internal signals in one linear solve
(`(I - L·D)·v = L·C·x + M·u`) rather than substituting along a topological order,
so algebraic loops surviving the input break are resolved instead of rejected.
Well posedness is the invertibility of that matrix.

**`StateSpace`** gains `state_labels` / `input_labels` / `output_labels`
constructor arguments. These are the `states` / `inputs` / `outputs` keyword
arguments of `control.StateSpace`, so an assembled model hands over to
python-control without an adapter.

**`Subsystem` implements the block interface recursively.** `state` (getter and
setter), `get_all` and `derivative` were inherited from `Block` and read the
dummy engine, which is only a marker and never written -- a subsystem with two
internal integrators reported a single placeholder state. `to_statespace()` takes
no break or tap points because the interface already designates them, and since a
`Subsystem` is a `Block` it composes: nested hierarchies linearize
hierarchically.

## Test plan

- [x] `pytest -m "slow or not slow"` -- 1048 passed, 12 skipped
- [x] 21 new tests in `tests/[redacted-repo]/optim/test_linearization.py`, checking the
      assembly against analytic models for gain cascades, closed loops, MIMO
      round trips, resolved algebraic loops, subsystems and nested subsystems
- [x] Small signal step response of an assembled model verified against the
      nonlinear system it was linearized from

Pre-existing on `master` and unrelated: the 15 `test_fmuwrapper.py` model
exchange failures, and `steadystate()` failing with `LinAlgError` on a PID plus
nonlinear plant loop.

## Not in this PR

`trim()` -- solving backwards for the input that produces a desired output. Wanted
as an extension of `steadystate()` rather than a separate solver stack, see [redacted-ref]
and [redacted-ref].

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
