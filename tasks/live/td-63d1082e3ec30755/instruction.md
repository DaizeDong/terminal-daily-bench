# fix(build): include pypr-client when installing from source ([redacted-ref])

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

[redacted-ref].

I ran into this installing from a git checkout: `pypr-client` was missing. It turns out any source install is affected.

The native client only gets compiled when `[redacted-repo]_BUILD_NATIVE=1`. That flag is set in `scripts/make_release` for the manylinux wheel, but a plain `uv build`, or a pip/uv install from an sdist or git archive, never sets it. So the build hook skips compilation and you get a pure python wheel with no `pypr-client`. Installing from PyPI hides it, because pip pulls the prebuilt manylinux wheel that already contains the binary, which is probably why it was hard to reproduce.

The gate came in with [redacted-sha] (the 3.3.0 commit). Before that, the hook always tried to compile when a compiler was present.

This restores that behaviour and adds an explicit way to turn it off:

* no env var (default): best effort compile, dynamically linked, wheel tagged for the local platform. This is what source installs get.
* `[redacted-repo]_BUILD_NATIVE=1`: statically linked, manylinux tag, for the PyPI release. Unchanged.
* `[redacted-repo]_BUILD_NATIVE=0`: never compile, stay pure python. `make_release` now uses this for the cross platform wheel, so the set of wheels published to PyPI is exactly the same as before.

How I checked it locally:

* `uv build --wheel` with no flag now produces a wheel containing `[redacted-repo]-3.4.1.data/scripts/pypr-client`, and the binary runs.
* `[redacted-repo]_BUILD_NATIVE=1 uv build --wheel` still produces the manylinux wheel with the static binary.
* `[redacted-repo]_BUILD_NATIVE=0 uv build` produces the pure `py3-none-any` wheel.
* the sdist still ships `client/pypr-client.c` and `hatch_build.py`, so it can compile on the user's machine.
* added `tests/test_native_client_build.py` covering the three modes (it skips when there is no C compiler).

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
