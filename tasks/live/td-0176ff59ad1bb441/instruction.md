# perf: Avoid getting columns to read dtypes, route bare selectors through `simple_select`

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

# Description

Drive by [redacted-url]

---

*`_iter_schema` reads `df.schema` rather than every column just to look at its dtype.
* `DataFrame.select` now routes a bare selector (`ncs.numeric()`) to `simple_select` instead of evaluating it to N Series and concatenating them, and eager
* Also fixes `DuckDBLazyFrame.simple_select`

Each one has its own commit - happy to keep any of those ([redacted-url] is really low effort :)) 

## What type of PR is this? (check all applicable)

- [ ] 💾 Refactor
- [ ] ✨ Feature
- [ ] 🐛 Bug Fix
- [x] 🔧 Optimization
- [ ] 📝 Documentation
- [ ] ✅ Test
- [ ] 🐳 Other

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
