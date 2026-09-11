# Poly-Retrace

Codex、Claude Code、Kimi Code、Oh My Pi (OMP)、Grok CLI 会话历史的索引与检索工具,按平台分别维护索引。

## Language

**平台 (Platform)**:
产生会话历史的 agent 运行时,取值为 `codex`、`claude`、`kimi`、`omp`、`grok` 之一。每个平台有独立的会话存储位置和独立的索引数据库,互不混用。
_Avoid_: client, runtime, 工具

**项目桶 (Project Bucket)**:
由会话真实工作目录(workDir/cwd)经 `encode_path` 编码得到的稳定名称,用于按项目过滤搜索结果和定位索引数据库。 kimi 平台只取会话 `state.json` 的 `workDir`;OMP 只取各 JSONL `session` 头的 `cwd`;Grok 只取会话 `summary.json` 的 `info.cwd`,三者的会话目录名都不作为归属依据。
_Avoid_: 项目目录, project folder

**Wire 文件 (Wire File)**:
Kimi Code 记录会话的协议事件日志,位于 `sessions/<工作目录桶>/session_<uuid>/agents/<agent>/wire.jsonl`,是 kimi 平台会话内容的唯一事实来源。
_Avoid_: 会话日志, transcript

**OMP 会话文件 (OMP Session File)**:
OMP 的树形 JSONL 会话,默认位于 `~/.omp/agent/sessions/<目录桶>/*.jsonl`。可变标题槽可能位于 `session` 头之前;assistant 的 `toolCall` 内容块和 `toolResult` 消息拆成独立索引事件。
_Avoid_: OMP Wire, OMP transcript

**Grok 会话文件 (Grok Session File)**:
Grok CLI(xAI 官方 Rust CLI)的会话,位于 `$GROK_HOME/sessions/<url-encoded-cwd>/<session-id-uuidv7>/updates.jsonl`,是 append-only 的 ACP session update 事件流,也是 grok 平台会话内容的唯一事实来源。同目录的 `summary.json` 提供元数据与项目归属,`chat_history.jsonl` 不索引。
_Avoid_: Grok Wire, Grok transcript

**用户消息 (User Message)**:
会话中用户一侧的输入。 kimi 平台以 wire 文件中 `context.append_message`(role=user)事件为唯一来源,`turn.prompt` 为其重复副本,不入索引。
_Avoid_: prompt, 输入

## Decisions

- Kimi 会话的项目归属只取 `state.json.workDir`;缺失或损坏时不猜测归属,也不解析 `wd_` 目录名。详见 `skills/retrace/references/adr-001-kimi-project-attribution.md`。
- OMP 会话的项目归属只取各 JSONL 的 `session.cwd`;缺失或损坏时不解析目录桶。`PI_CODING_AGENT_DIR` 与 `PI_CODING_AGENT_SESSION_DIR` 分别覆盖 agent home 和会话根。
- Grok 会话的项目归属只取 `summary.json` 的 `info.cwd`;缺失或损坏时先 URL-decode percent-encoding 的分组目录名,再读组目录的 `.cwd` 文件,绝不套用 Codex 式 `-` 解码。`GROK_HOME` 是 Grok home 的唯一覆盖项。详见 `skills/retrace/references/adr-002-grok-project-attribution.md`。
