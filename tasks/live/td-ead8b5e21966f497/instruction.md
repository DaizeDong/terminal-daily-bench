# URL normalization, release docs

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

- Penpa: parse_penpa_input handles full URLs, m=solve, and extra query params; invalid payloads raise PenpaDecodeError instead of leaking low-level binascii / zlib errors.
- puzz.link: parse_puzzlink_input accepts mirror hosts and bare paths; decode adds puzzlink_puzzle_path metadata.
debug: format detection updated for these URL shapes.
- docs: pyproject.toml description/keywords; README section on URL interchange, example, collapsible type table;
- tests: round-trip / alternate-host coverage where applicable.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
