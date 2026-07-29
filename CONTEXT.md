# Poly-Retrace

Codex、Claude Code、Kimi Code 会话历史的索引与检索工具,按平台分别维护索引。

## Language

**平台 (Platform)**:
产生会话历史的 agent 运行时,取值为 `codex`、`claude`、`kimi` 之一。每个平台有独立的会话存储位置和独立的索引数据库,互不混用。
_Avoid_: client, runtime, 工具

**项目桶 (Project Bucket)**:
由会话真实工作目录(workDir/cwd)经 `encode_path` 编码得到的稳定名称,用于按项目过滤搜索结果和定位索引数据库。 kimi 平台一律以会话 `state.json` 的 `workDir` 为来源,不解析会话目录名。
_Avoid_: 项目目录, project folder

**Wire 文件 (Wire File)**:
Kimi Code 记录会话的协议事件日志,位于 `sessions/<工作目录桶>/session_<uuid>/agents/<agent>/wire.jsonl`,是 kimi 平台会话内容的唯一事实来源。
_Avoid_: 会话日志, transcript

**用户消息 (User Message)**:
会话中用户一侧的输入。 kimi 平台以 wire 文件中 `context.append_message`(role=user)事件为唯一来源,`turn.prompt` 为其重复副本,不入索引。
_Avoid_: prompt, 输入

## Decisions

- Kimi 会话的项目归属只取 `state.json.workDir`;缺失或损坏时不猜测归属,也不解析 `wd_` 目录名。详见 `skills/retrace/references/adr-001-kimi-project-attribution.md`。
