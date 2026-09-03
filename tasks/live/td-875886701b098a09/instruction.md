# fix(security): harden remote media fetching

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

- block SSRF through loopback, private, link-local, multicast, credential-bearing, and unsafe redirect targets
- verify the connected peer to defend against DNS rebinding and fail closed when it cannot be inspected
- stream and cap remote image, audio, and PDF downloads; stop caching media payloads in process memory
- refresh vulnerable runtime dependency floors and generated locks while preserving Python 3.9 compatibility
- pin GitHub Actions to reviewed commit SHAs and add Dependabot coverage/cooldowns

## Security impact

Remote multimodal URLs previously used unrestricted requests calls. An attacker able to influence those URLs could reach internal services or force unbounded response bodies into memory. This change centralizes remote fetching with public-address validation at every redirect, bounded decoded reads, ambient credential/proxy isolation, and explicit peer verification.

## Verification

- 165 focused multimodal, provider, and security tests passed; 1 skipped
- 26 remote-fetch security tests passed on Python 3.9
- Ruff check and format checks passed
- ty checks passed for source and tests
- pip-audit reports no known vulnerabilities in the generated current-Python requirements
- uv lock validation and package build passed

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
