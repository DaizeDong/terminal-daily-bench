# fix(scan): reject file paths passed as roots

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Problem

<!-- greptile_comment -->

<details><summary><h3>Greptile Summary</h3></summary>

The PR rejects explicitly supplied scan roots that resolve to files, preventing them from being treated as clean scans.
- Adds an early directory validation with a diagnostic and failure exit code.
- Preserves parseable empty output in JSON and SARIF modes.
- Adds a regression test for file roots in JSON mode.
</details>

<h3>Confidence Score: 5/5</h3>

The PR appears safe to merge with no actionable defects identified.

The new guard rejects existing non-directory explicit roots before scanning and follows the established error and machine-output behavior of adjacent validation paths.

<h3>Important Files Changed</h3>

| Filename | Overview |
|----------|----------|
| src/agentsweep/pipeline.py | Adds a correctly ordered file-root rejection after existence validation while preserving established machine-output behavior. |
| tests/test_output.py | Covers the new file-root error path, exit status, stderr diagnostic, and parseable JSON stdout. |

<sub>Reviews (1): Last reviewed commit: ["fix(scan): reject file paths passed as r..."]([redacted-url]) | [Re-trigger Greptile]([redacted-url])</sub>

<!-- /greptile_comment -->

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
