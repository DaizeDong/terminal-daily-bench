# Add fft()/invfft() functions for DFT calculation

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Addresses [redacted-ref] 

Implements the `Radix-2 Cooley-Tukey` Fast Fourier Transform (FFT) algorithm to compute the discrete fourier transform (DFT) and inverse discrete fourier transform (IDFT) of a signal.

### Key Changes:
- Added iterative Radix-2 Cooley-Tukey FFT for power-of-two input lengths signals.
- Implemented `fft(x)` and `invfft(X)` for calculating forward and inverse DFT.
- Added unit tests along with docstrings and usage examples.

### Design Decisions & Next Steps
- No zero-padding: After a long discussion, we decided not to use optional zero-padding and Inputs are currently restricted to lengths of powers of 2 ($N = 2^k$).
- Future Work: Support for arbitrary input sizes via Bluestein's algorithm or similar approaches.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
