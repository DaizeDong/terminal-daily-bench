# feat(env): read .env in the framework, and drop python-dotenv

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Why

A project should not have to install a dependency, and remember to call it early enough, for `.env` to work. `python-dotenv` was in [redacted-repo]'s dependency list purely so `Config` could call `load_dotenv()`, and even then the file was only read when a class explicitly named it.

Sillo now parses `.env` itself and loads it on the way up. `python-dotenv` leaves `[project.dependencies]`.

## The loader

`sillo/env/_loader.py` was already in the tree (untracked), but it parsed line by line. Two consequences:

- the multi-line triple-quoted values its own docstring advertised never worked — the file was read `for line in fh`, so a certificate or private key was truncated at the first newline
- values were cut at the first `#`, so `PASSWORD=pa#ssword` silently became `pa`

It is now a scanner over the whole text:

| Form | Behaviour |
|------|-----------|
| `KEY=value` | to end of line, trimmed |
| `KEY="value"` | escapes (`\n`, `\t`, `\"`) and `${REFERENCES}` resolved |
| `KEY='value'` | literal — nothing expanded or unescaped |
| `KEY="""…"""` / `'''…'''` | multi-line, for certificates and keys |
| `export KEY=value` | prefix dropped |
| `KEY=value # note` | comment dropped — **whitespace before `#` required** |
| `KEY=pa#ssword` | the hash is part of the value |

References resolve against names defined earlier in the same file first, then the surrounding environment. `${NAME:-fallback}` covers unset-or-empty, `${NAME-fallback}` only unset, `\$` is a literal dollar. CRLF and BOM handled; a malformed line is skipped rather than raised, because a half-typed `.env` should not stop an application from booting.

## Loading it without being asked

`SilloApp(...)`, every `sillo.config.Config` subclass, and the `sillo` command each call `autoload()`, which reads the project's `.env` **once per process**. The console loads it before the project is imported, so a module that reads `os.environ` at import time sees it too.

The file is found by walking up from the working directory and **stopping at the project root** (`pyproject.toml`, `uv.lock`, `setup.py`, `setup.cfg`, `.git`). `sillo serve` from `myproject/app/handlers` finds `myproject/.env`; a stray `~/.env` is never picked up.

Precedence, most specific first:

1. arguments — `Settings(database_url=…)`
2. the real environment — what the shell, container or platform exported
3. `.env`

An exported variable beating the file is what lets one image run in every environment. `load_env(..., override=True)` reverses it for the cases that want the file to win.

`SILLO_ENV_FILE` names a different file, or turns automatic loading off entirely when set empty — useful in tests, where the environment should be the only source.

## Public API

```python
from sillo.env import env, find_env, load_env, parse_env

load_env(".env.local", override=True)   # layering, since there is no implicit .env.local
port = env("PORT", 8000, cast=int)      # one typed read
values = parse_env(text)                # pure: touches nothing
```

`cast=bool` understands what `.env` files actually contain — `true/yes/on/1` and their opposites — rather than Python's rule where the string `"false"` is true.

## Config changes

- **`env_prefix`** — makes the `DATABASE_URL` / `DATABASE_POOL_SIZE` mapping the documentation has always described actually work. It was documented in `advanced/configuration.md` and never implemented; every prefixed example in those docs was wrong.
- **Aliases name the variable** — `Field(alias="db_url")` now reads `DB_URL`, and the value is keyed by alias so it lands whether or not the model populates by name.
- **Options move to an inner `Env` class.** Pydantic claims `Config` for its own deprecated class-based settings and warns on every model that declares one — and removes it in V3. An inner `Config` is still read, so nothing breaks.

```python
class DatabaseConfig(Config):
    url: str
    pool_size: int = 10

    class Env:
        env_prefix = "DATABASE_"   # env_file = None loads no file at all
```

## Fixed: `print(config)` leaked secrets

Found while running `examples/config/01_basic_config.py`. `__repr__` masked fields whose names look like secrets, but `print()` calls `__str__`, which Pydantic writes out in full — the one moment somebody is most likely to be looking at a terminal or a log. Both mask now.

```
before: jwt_secret='dev-secret-key-not-for-production' …
after:  <AppConfig {… 'jwt_secret': '***' …}>
```

## Tests

162 new tests in `tests/test_env/` and `tests/test_config/test_env_loading.py`: the grammar (quoting, escapes, multi-line, comments, malformed lines, unicode), references and defaults, the upward search and its project-root stop, precedence and `override`, `autoload` caching and its opt-outs, the `env()` casts, and that no module in the framework imports dotenv or declares it as a dependency.

- **4828 passed, 60 skipped, 0 failed**
- 99% coverage on `sillo/env` and 100% on `sillo/config` (the two uncovered lines are an `OSError` guard for an unreadable working directory)
- `ruff check`, `ruff format` and `mypy` clean

## Docs

- new **Environment & .env** guide — grammar, precedence, layering, `SILLO_ENV_FILE`, Docker — added to the sidebar
- **Configuration** guide and the internal **Configuration System** reference updated, including two claims they carried that were simply untrue: `DEBUG=yes` does *not* fail validation, and multi-line values *are* supported
- the nine `class Config:` examples in the internal reference now use `class Env:` with the `env_prefix` that makes their own variable tables correct
- examples and `.env.example` updated and run; CHANGELOG entry added
- `npx astro build` completes clean, 252 pages

## Not in this PR

`starter/app/config.py` and `starter-inertia/app/config.py` still pass `_env_file=".env"`. Dropping the argument would be strictly better — it would work from subdirectories — but both install a released `sillo-framework>=0.1.0b1` from PyPI rather than this tree, so the change would silently stop loading `.env` until a release ships with `autoload`. Worth doing as a follow-up once this is released.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
