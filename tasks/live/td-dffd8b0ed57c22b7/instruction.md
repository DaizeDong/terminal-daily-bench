# feat(email): 新增 Inbucket 自建邮箱提供方

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## 概述

新增第 7 个邮箱服务商 `inbucket`,支持自建 [Inbucket]([redacted-url]) 实例收 xAI 验证码。

## 配置

| 字段 | 说明 |
|------|------|
| `inbucket_api_base` | 实例根 URL,如 `[redacted-url] `INBUCKET_API_BASE` 环境变量、`INBUCKET_WEB_BASEPATH` 子路径) |
| `inbucket_domain` | 收信域名(MX 需指向该实例),如 `mail.example.com` |

无需 API Key:Inbucket 邮箱即建即用,注册时本地生成地址,轮询 v1 REST API 收信。API 的 `{name}` 参数直接传完整邮箱地址,服务端按自身 MailboxNaming(local/full)解析,无需额外配置。

## 改动

- `email_providers/inbucket.py`(新):地址生成、列表/详情两级验证码提取(复用 common 打分逻辑)、用后清理邮箱;API 请求强制直连
- `grok_register_ttk.py`:默认配置、getter、取号/收码分发、直连规则
- `connectivity.py`:面板连通性测试分支(404/401 分别提示)
- `webui/email_provider_store.py`:注册 Inbucket 字段与已配置判定
- 面板 FAQ、`config.example.json`、README、CHANGELOG 同步
- 新增 `tests/test_inbucket.py`(8 用例)并更新 store 测试断言,已注册进 `scripts/run_tests.sh`

## 验证

- 新增/更新测试全部通过;`compileall`、`bash -n`、`git diff --check` 通过
- 全量套件中 4 个测试文件在 Windows 上失败,已用 `git stash` 验证为干净树上同样失败的平台既有问题(符号链接权限、POSIX `0o600`、路径分隔符),与本次改动无关
- diff 仅含保留地址/示例值,无真实凭据

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
