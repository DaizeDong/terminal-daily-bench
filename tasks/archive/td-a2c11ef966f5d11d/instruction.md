# 统一前后端上传视频格式契约

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## 问题

本地视频文件选择器包含 `video/*`。该 MIME 通配符会让浏览器开放 `.3gp`、`.ogv` 等后端明确拒绝的格式，用户直到上传后才收到 422。

## 根因

前端把宽泛 MIME 类型与显式扩展名做并集；后端则只按文件名末尾扩展名接受固定 8 种格式，两侧契约没有自动防漂移检查。

## 修复方案

- 新增机器可读的前端上传格式契约，固定为 `.mp4/.mov/.m4v/.mkv/.webm/.avi/.flv/.wmv`。
- 文件输入只使用这些扩展名 token，移除 `video/*`，不再向用户开放后端必然拒绝的格式。
- 后端安全校验保持不变，继续在建任务和写盘前按扩展名白名单拒绝非法文件。
- 新增跨栈契约测试：直接比对 JSON 与后端 `ALLOWED_VIDEO_SUFFIXES`，检查重复、大小写和点前缀，并验证所有大写扩展名可规范化。
- 增加 `.3gp` 伪报 `video/mp4` 仍返回 422 的回归测试，证明 MIME 不能绕过后端校验。

## 验证结果

- `.venv/bin/pytest backend/tests -q`：322 个测试通过（1 个既有弃用警告）
- `npm --prefix apps/web test -- --reporter=verbose`：9 个测试通过
- `npm --prefix apps/web run lint`：通过
- `cd apps/web && ./node_modules/.bin/tsc --noEmit`：通过
- `npm --prefix apps/web run build`：通过
- `git diff --check`：通过

## 审查

前后端独立复审均未发现代码层 P0–P2。复审提示的新 JSON 漏提交风险已通过显式暂存清单核对闭环，提交 `[redacted-sha]` 已包含该文件。

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
