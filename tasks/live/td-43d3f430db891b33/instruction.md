# Debug/laplace1d

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

I think the following is a bug: The `Laplace1d` method convolved the input with a 1d laplace kernel and applied an aggregation function (mean or sum), so its outputs could be negative or positive. In `SimpleCoreWrapper` and `SingleCellSeparatedLNP` however it is used as a regularizer so I think it may not make sense to allow negative values. 

I applied the following changes: 
1. `Laplace1d` is now a filtering class (I removed the aggregation function) just like `Laplace` for 2d inputs. 
2. The regularizer class `TimeLaplaceL23dnorm`. then uses the filtering class  `Laplace1d`  just  like `FlatLaplaceL23dnorm` then use the `Laplace` class, by squaring components and applying some aggregation function. 
3. The places where `Laplace1d` was instantiated in models now instantiate `TimeLaplaceL23dnorm`.
4. When `TimeLaplaceL23dnorm` is called, then the weights of the temporal kernels are no longer reshaped, as this is done in the forward method of `TimeLaplaceL23dnorm` itself. 
5. Added a test of the  `SingleCellSeparatedLNP` and removed a default argument value that raised an error. 

Note that one alternative would be to just take the absolute of the convolution result in the forward method (as done [here in neuralpredictors]([redacted-url]) but I thought this is cleaner.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
