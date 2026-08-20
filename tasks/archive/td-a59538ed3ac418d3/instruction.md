# fix(skills): remove broken default skills hub

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

**Issue:** [redacted-ref] — official skills hub URL returns 404
**Type:** Bug Fix
**Severity:** Medium

This PR removes the unavailable `openclaw-ai/skills-hub` repository from the default skill import path. The default `import-official-hub` command now only imports a verified reachable default skill (`mmx_cli`), while users who maintain their own Skills Hub can still opt in with `OPENCLAW_SKILLS_HUB_BASE` or `~/.openclaw/skills-hub-url`.

[redacted-ref].

---

## Root Cause

The default import path in `scripts/skill_manager.py` generated six URLs from `[redacted-url] That repository currently returns 404, so both `add-remote` examples and `import-official-hub` attempted to download unavailable files.

Source -> Sink:
- `scripts/skill_manager.py` default hub base -> `OFFICIAL_SKILLS_HUB` entries -> `import_official_hub()` -> `add_remote()` -> `_download_file()`
- README/docs examples -> users copy a raw URL from the unavailable hub -> `_download_file()`

```python
# Before
OFFICIAL_SKILLS_HUB_BASE = '[redacted-url]
OFFICIAL_SKILLS_HUB = {
    'code_review': _get_hub_url('code_review'),
    ...
}

# After
OFFICIAL_SKILLS_HUB = {
    'mmx_cli': '[redacted-url]
}
```

---

## Fix Description

**Changed files:**
- `scripts/skill_manager.py:221` — removed the broken built-in hub base and mirror fallbacks.
- `scripts/skill_manager.py:225` — added custom hub discovery via `OPENCLAW_SKILLS_HUB_BASE` or `~/.openclaw/skills-hub-url`.
- `scripts/skill_manager.py:240` — kept only verified `mmx_cli` as a default built-in skill.
- `scripts/skill_manager.py:271` — kept `import-official-hub` compatible, but defaulted each skill to its own recommended agents when `--agents` is omitted.
- `README.md:553` — replaced broken `code_review` examples with the reachable `mmx_cli` URL.
- `docs/remote-skills-guide.md:160` — documented default skills and custom hub configuration.
- `docs/remote-skills-quickstart.md` — updated quickstart examples away from the 404 source.
- `tests/test_skill_manager.py` — added regression coverage for default URLs, custom hub opt-in, and recommended-agent import behavior.

Rationale:
- This avoids replacing one unavailable official source with an unverified third-party source.
- The existing CLI command name stays stable for compatibility.
- Users who have a private or community Skills Hub can still use the previous `<base>/<skill>/SKILL.md` layout explicitly.

---

## Test Results

| Test | Description | Status |
|------|-------------|--------|
| `python3 tests/test_skill_manager.py` | Unit tests for default skill URLs, custom hub URLs, and recommended-agent import behavior | PASS |
| `python3 -m py_compile scripts/skill_manager.py tests/test_skill_manager.py` | Syntax check for changed Python files | PASS |
| `OPENCLAW_HOME=/tmp/[redacted-repo]-[redacted-ref]-openclaw python3 scripts/skill_manager.py import-official-hub --agents menxia` | Real CLI smoke test downloading the default `mmx_cli` skill | PASS |
| `git diff --check` | Whitespace check | PASS |
| `rg ... openclaw-ai/skills-hub ...` | Verified no default docs/code path still references the broken hub URL | PASS |

Manual verification before the fix:
- `curl -I [redacted-url] returned `HTTP/2 404`.
- `curl -I [redacted-url] returned `HTTP/2 404`.
- `curl -I [redacted-url] returned `HTTP/2 200`.

---

## Disprove Analysis

### 是否已有其他地方修复

Checked current open PRs before implementing. [redacted-ref] and [redacted-ref] do not touch remote skills. The earlier merged [redacted-ref] added `mmx_cli`, but did not remove the broken `openclaw-ai/skills-hub` defaults or documentation references.

### 影响范围

Affected path is limited to remote skill import defaults and docs. Direct `add-remote --source <url>` continues to work for any valid HTTPS URL. Existing local remote skills already installed under `~/.openclaw` are not migrated or deleted.

### 边界情况

When `--agents` is omitted, the command now imports each default/custom skill to its own recommended agents instead of building one combined agent list for every skill. If a user sets `OPENCLAW_SKILLS_HUB_BASE` or `~/.openclaw/skills-hub-url`, the legacy skill names are restored using `<base>/<skill_name>/SKILL.md`.

### 已知局限

This PR does not introduce a replacement official Skills Hub. It intentionally keeps only verified reachable defaults and leaves custom hub selection explicit.

---

## Checklist

- [x] 代码遵循项目现有风格（错误信息用中文，符合现有 CLI 惯例）
- [x] 相关 issue 编号在 PR 描述中已引用（[redacted-ref]）
- [x] 有测试覆盖（并包含真实 CLI 下载烟测）
- [x] 无硬编码路径、密钥、调试输出

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
