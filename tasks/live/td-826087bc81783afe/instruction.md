# Add semidefinite_tag for operators of unknown-sign definiteness

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

This is useful when an operator gets multiplied by a traced scalar or potentially in diffrax if we go down the `AssumeTagged` route. This affects the Cholesky/CG/HEVD handling.

**Cholesky**

Cholesky requires sign probing, fortunately this is cheap because Cholesky materialises the operator so we can be confident the sign is equal to the sign of the max absolute value along the diagona (theoretically it should be ANY diagonal value for a definite operator, which is what Cholesky requires, but this is safer and still O(N)).

**CG**

I realised CG is NOT sign sensitive and we can actually entirely remove the sign handling in CG (essentially multiplying by -1 on the way in and the way out is effectively a no-op), I validated this empirically and guard against it in tests now.

**HEVD**

When `MaxRankTag` is provided we do rank checking and discard the eigenvalues we expect to be zero by using the fact that the eigenvalues come in ascending order. We evaluate the sign by comparing the absolute value of the first and last eigenvalue and then use a dynamic slice to drop the below threshold ones.

Also made a drive-by change to use `jnp.split` for this on other branches.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
