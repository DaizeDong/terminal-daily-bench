# Enhance Benchmark Functions for Performance Evaluation

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

This pull request enhances the benchmark suite in [redacted-repo] by adding new mathematical functions commonly used for evaluating optimization algorithms. These functions improve the diversity of test cases, allowing better analysis of convergence, local minima avoidance, and overall performance.

**Changes Made:**
 Added new benchmark functions in benchmark.py:

> Ackley Function – Tests convergence behavior
> Rosenbrock Function – Evaluates valley-following performance
> Rastrigin Function – Measures global and local search capabilities
> Griewank Function – Analyzes algorithm robustness

 Created unit tests in test_benchmark.py to verify function accuracy.
 Updated README.md with descriptions and usage instructions.

**Testing:**
All new functions were tested with random input vectors.
Verified correct outputs against standard function definitions.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
