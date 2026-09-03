# fix: 避免 Abaqus MCP 离线时持续等待

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## 问题

Abaqus/CAE 已关闭或插件轮询线程退出后，旧的 `status.json` 仍可能显示 `running`。原 MCP 会继续写入命令并等待 10～30 秒，客户端表现为工具持续转圈。

## 修复

- 新增插件心跳新鲜度、状态和 Abaqus PID 检查
- 新增受管 `mcp_guard.py`，桥接离线时立即返回可读错误
- `doctor` 区分“配置完成”和“当前可调用”
- 新安装默认注册防卡入口
- 已有安装通过 `mcp-setup --repair --yes` 明确切换
- 不覆盖用户自己的同名 guard 文件，替换注册失败时尽力恢复原入口
- 增加中文排障文档

## 验证

- 68 项离线测试全部通过
- 在真实过期状态文件上正确识别 `stale`
- 真实体检显示：MCP 配置完成，但 Abaqus 桥接离线、智能模式不可用
- wheel 构建成功并包含 `mcp_guard.py`
- Markdown 本地链接检查通过

## 使用提醒

合并代码不会自动修改任何用户的 MCP 注册。已有用户需要主动运行：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex mcp-setup --repair --yes
```

然后重新打开 Codex，并启动 Abaqus/CAE 中的 MCP 插件。

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
