# [Bug] Custom function imports: namespace to a copy, never in place

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

`CustomFunctionFactory.with_namespace` rewrote the factory it was called on. A parsed import environment is shared — process-wide by the import store, and object-for-object with its importer on a bare `import x;` — so the factory an aliased import namespaces is the same object the next edge namespaces. Each edge re-prefixed the previous edge's work: an argument declared `col` became `direct.two.two.one.one.right.left.col`, growing with the size of the import graph.

The accumulation alone was survivable, because body references and argument bindings accumulated together and still matched at substitution time. It turned fatal under the directory runner's thread pool: `with_namespace` wrote `self.function` and `self.function_arguments` in two separate statements, so a thread invoking `@fn(...)` in between deep-copied a body one level deeper than the names it matched against. Substitution silently no-opped and the accumulated reference survived into concept lineage, failing as `Undefined concept: launch.launch....manufacturer.col` — intermittently, depending on interleaving.

Returns a new factory instead. Argument addresses now equal the real import nesting and are byte-identical across repeated and threaded parses.

### Coverage
`tests/parsing/test_custom_function_namespace_isolation.py`, over a diamond import graph (`helper` reached under four aliases through two levels of nesting):
- `with_namespace` returns a copy and leaves the source untouched across two edges
- argument addresses are no deeper than the function's own key — pre-fix this was `direct.two.two.two.one.one.one.right.left.col` for `one.double`
- four-thread concurrent parses match a sequential parse
- a custom-function-derived concept still resolves through nested aliases

The first two fail on the pre-fix code; all four pass after.

### Release
Version bumped 0.3.337 → 0.3.338 so prod can move off the 0.3.335 pin.

🤖 Generated with [Claude Code]([redacted-url])

[redacted-url]

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
