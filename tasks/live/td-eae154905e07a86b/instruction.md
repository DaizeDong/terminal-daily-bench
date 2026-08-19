# feat(config): XDG-style config location, with legacy fallback ([redacted-ref])

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

[redacted-ref].

## 1. XDG-style config location

The global config lived at `~/.[redacted-repo]`, which isn't XDG-compliant. It now resolves to `$XDG_CONFIG_HOME/[redacted-repo]`, defaulting to `~/.config/[redacted-repo]`.

**Existing installs are unaffected.** If `~/.[redacted-repo]` is present and the XDG path is not, the legacy directory is used as-is — no migration, nothing moves on upgrade. Once the XDG path exists it takes precedence, so migrating is just:

```bash
mv ~/.[redacted-repo] ~/.config/[redacted-repo]
```

The rule is implemented identically in all four places that resolve config independently — `obsidian_wiki/cli.py`, `setup.sh`, `scripts/daily-update.sh`, `scripts/wiki-notify.sh` — plus the Config Resolution Protocol in `.skills/llm-wiki/SKILL.md` that the other ~30 skills defer to. This matters because a Python/bash mismatch would put vault-scoped `state/` in one directory and the config in another, silently breaking the daily-update → terminal-notification handoff.

Named `config.<name>` vault profiles (`wiki-switch`, `@name` routing) follow the same directory.

## 2. Drive-by fix: `setup` was wiping user config keys

While testing the above I found a **pre-existing data-loss bug**, present on `main` and unrelated to the XDG change: `write_config` rewrote the config with only the three setup-managed keys, so every `[redacted-repo] setup` — including the one a pip upgrade prompts for — silently destroyed everything else in the file.

Before, on `main`:

```console
$ cat ~/.[redacted-repo]/config          # before setup
# my notes config
OBSIDIAN_VAULT_PATH="/path/to/vault"
OBSIDIAN_LINK_FORMAT="markdown"
QMD_WIKI_COLLECTION="mybrain"

$ [redacted-repo] setup --vault /path/to/vault
$ cat ~/.[redacted-repo]/config          # after setup — comment + 2 keys GONE
OBSIDIAN_VAULT_PATH="/path/to/vault"
OBSIDIAN_WIKI_REPO="..."
OBSIDIAN_WIKI_VERSION="2026.6.8"
```

After, on this branch:

```console
$ cat ~/.[redacted-repo]/config          # after setup — everything preserved
# my notes config
OBSIDIAN_VAULT_PATH="/path/to/vault"
OBSIDIAN_LINK_FORMAT="markdown"
QMD_WIKI_COLLECTION="mybrain"
OBSIDIAN_WIKI_REPO="..."
OBSIDIAN_WIKI_VERSION="2026.6.8"
```

Setup now owns only `OBSIDIAN_VAULT_PATH`, `OBSIDIAN_WIKI_REPO` and `OBSIDIAN_WIKI_VERSION`, updating those in place and carrying every other line — including comments and ordering — over untouched. Duplicate definitions of a managed key collapse to one.

It's fixed here rather than separately because this branch already touches config writing, and making `setup` re-runs more likely is exactly what the XDG work does.

## Verification

Ran end-to-end in throwaway `HOME`s (since deleted). Every scenario passing:

| Scenario | Result |
|---|---|
| Fresh install (`cli setup`) | → `~/.config/[redacted-repo]/`, no legacy dir created |
| Fresh install (`setup.sh`) | same — bash matches Python |
| Existing legacy install | stays at `~/.[redacted-repo]`, settings read intact |
| Re-run setup on legacy (pip upgrade) | stays put — no split-brain, no XDG dir created |
| `XDG_CONFIG_HOME` set to a custom dir | honored |
| Migration (`mv` to XDG) | XDG takes over, settings survive |
| Both dirs exist / neither exists | deterministic; bash == Python |
| `@work` named vault, XDG + legacy | routes to the right vault |
| `wiki-switch` symlinked config | resolves through the symlink |
| Missing `@name` | clean error, no silent fallback |
| `daily-update.sh` → `wiki-notify.sh` state handoff | writer/reader agree in both layouts |
| Stale-vault notification | fires from the XDG state dir |

Bash and Python resolvers were cross-checked against each other on all six layout permutations:

```console
MATCH  fresh       -> A-fresh/.config/[redacted-repo]
MATCH  legacy      -> B-legacy/.[redacted-repo]
MATCH  migrated    -> D-migrate/.config/[redacted-repo]
MATCH  custom-xdg  -> C-xdghome/[redacted-repo]
MATCH  both-exist  -> H-both/.config/[redacted-repo]
MATCH  neither     -> I-none/.config/[redacted-repo]
```

Named-vault routing, proven by giving each vault a distinct page count:

```console
=== @work (work vault)          === pages = 7
=== default/active (personal)   === pages = 4
```

### Tests

10 new tests across two files:

- `tests/test_xdg_config_location.py` — fresh install, `XDG_CONFIG_HOME` override, legacy-still-works, XDG-wins-after-migration, empty-`XDG_CONFIG_HOME`, end-to-end read of a legacy config.
- `tests/test_write_config_preserves_user_keys.py` — user keys survive a re-run (XDG and legacy), managed keys still written on a fresh config, duplicate managed keys collapse.

Both pin `PYTHONPATH` so they exercise this checkout rather than whatever `obsidian_wiki` happens to be pip-installed.

**Suite status:** 550 passed. The 12 remaining failures (`test_code_understand_cli.py`, `test_context_pack_cli.py`) are pre-existing — I ran the same subset on `origin/main` and on this branch in clean clones and the failure set is byte-identical, so this PR introduces no regressions. The `code_understand` ones arrived with the upstream CodeGraph commits and appear environment-dependent (missing `codegraph` binary).

### Docs

`docs/configuration.md` gains a "Where the global config lives" section covering the XDG path, the legacy fallback, and the one-line migration; `docs/installation.md` gets an upgrade note linking to it. `README.md`/`README_TW.md` contain no config-path references, so translation parity is unaffected.

> Note: this is a CLI/config change with no UI surface, so the evidence above is captured terminal output rather than screenshots.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
