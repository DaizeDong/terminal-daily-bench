# feat(knowledge-graph): architecture knowledge graph - persistent, que…

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Architecture Knowledge Graph — persistent, queryable system model

  ### Summary

  Diagrams were always backed by a graph; this PR makes that graph **the source of truth**. It adds a knowledge-graph layer stored as a single version-controlled markdown file (default `.claude/architecture.md`).
  Services and dependencies live in the graph; `.excalidraw` diagrams become rendered **views** of it — full system, a single domain, or everything within N hops of one service.

  This turns the project from a *diagram generator* into a *living architecture layer*: the model is consistent across diagrams, queryable, lintable, and diffs cleanly in PRs.

  > The layout/render/export engine is reused unchanged — the knowledge graph is a superset of the existing `DiagramGraph` and projects down to it.

  ### What's included

  **Core**
  - `KnowledgeGraph` / `Service` / `Dependency` models with validating mutations
  - Markdown DSL parser/serializer (round-trip safe; tolerant of hand edits)
  - File-backed store + CRUD orchestration

  **[redacted-ref] new `kg_*` MCP tools**
  - Build/maintain: `kg_init`, `kg_add_service`, `kg_remove_service`, `kg_link`, `kg_unlink`, `kg_set_domain`, `kg_info`
  - Render: `kg_render`, `kg_render_view`, `kg_render_around`, `kg_render_domain`
  - Knowledge: `kg_import` (bootstrap from existing `.excalidraw`), `whats_connected_to` (impact analysis), `kg_path`
  - Health & ops: `kg_lint` (cycles, single points of failure, orphans, dangling refs), `kg_export` (mermaid/dot/json), `kg_diff` (git-aware), `kg_onboarding_doc`, `kg_drift` (import-based)

  **Parallel edges**
  - Two communication modes between the same services (e.g. `REST /charge` **and** `Kafka payment.requested`) are now kept as two distinct, labelled arrows. Edge identity is `(from_id, to_id, label)`.

  ### Notable fixes
  - **Layout:** fixed an infinite loop in `_uncross_arrivals` when two edges share an endpoint (surfaced by parallel edges; hardens the engine generally).
  - **SVG export:** edge labels now get a canvas-colored backing so the arrow line no longer runs through the text (mirrors Excalidraw's native bound-label rendering). Applies to every exported diagram.

  ### Testing
  - Full assertion suite for the new layer (models, parser round-trip, store, queries, views, migrate, lint, exporters, diff, docgen, drift) plus the MCP tool layer (incl. a git-backed `kg_diff` test).
  - `114 passed, 1 skipped`; `ruff check` and `ruff format` clean.

  ### Backwards compatibility
  - Fully additive. `create_diagram`, `mermaid_to_excalidraw`, `modify_diagram`, `get_diagram_info`, and `export_diagram` are unchanged.

  ### Docs
  - README: new “Architecture Knowledge Graph” section with the showcase image, the `.md` format, example asks, and a `kg_*` tool table.
  - New `.skills/architecture-knowledge-graph/SKILL.md` teaching the AI how to read a codebase and build a clean graph.

  🤖 Generated with [Claude Code]([redacted-url])

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
