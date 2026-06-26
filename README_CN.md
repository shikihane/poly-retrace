# poly-retrace

搜索和分析 Codex、Claude Code 与 pi 的会话历史，基于 SQLite FTS 全文索引、BM25 排序，以及可选的 AI 摘要能力。

English version: [README.md](./README.md).

## 功能

- 为每个项目的 Codex / Claude Code / Pi 会话 JSONL 建立独立的 SQLite 索引。
- 全文检索 + BM25 排序，额外提供 trigram 混合模式，用于中文、路径、连字符标识符和粘贴的日志片段。
- 分层检索输出（`stats` -> `list` -> `detail` -> `full`），帮助控制 token 预算。
- 单会话历史抽取（chronicle），输出 TOON / JSON，便于交接或存入记忆。
- 无 git 提交时，从会话日志中恢复文件版本（recover）。
- 可选通过 `codex exec` 进行 AI 分析，做错误分类、摘要等。

## 支持的平台

- Codex 会话：`%CODEX_HOME%\sessions\**\*.jsonl` / `$CODEX_HOME/sessions/**/*.jsonl`，以及 `archived_sessions`；默认 home 是 `~/.codex`。
- Claude Code 会话：`%CLAUDE_HOME%\projects\<encoded-cwd>\*.jsonl` / `$CLAUDE_HOME/projects/<encoded-cwd>/*.jsonl`；默认 home 是 `~/.claude`。
- Pi 会话：`%PI_AGENT_HOME%\sessions\**\*.jsonl` / `$PI_AGENT_HOME/sessions/**/*.jsonl`；默认 home 是 `~/.pi/agent`。
- 索引数据库位于对应平台 home 下的 `projects/<encoded-cwd>/retrace-index.db`。

必须显式传 `--platform codex`、`--platform claude` 或 `--platform pi`。

### 路径编码

Windows 路径中，盘符分隔符会被替换成 `--`，路径分隔符替换成 `-`：

`X:\Work\example-project` -> `X--Work-example-project`。

Unix 路径会去掉开头的 `/`，再把路径分隔符替换成 `-`：

`/home/user/example-project` -> `home-user-example-project`。

由于真实路径也可能包含连字符，反向解码是尽力而为的，除非 Codex 的 `session_meta.payload.cwd` 提供了原始路径。

## 目录结构

```
poly-retrace/
|-- skills/retrace/SKILL.md       # 技能入口
|-- skills/retrace/scripts/
|   |-- retrace_paths.py          # 对外兼容层，封装 platforms/
|   |-- retrace_common.py         # 共享工具（搜索、分块、AI 调用）
|   |-- platforms/
|   |   |-- common.py             # 共享数据模型
|   |   |-- codex.py              # Codex 路径与解析
|   |   |-- claude.py             # Claude Code 路径与解析
|   |   |-- pi.py                 # Pi 路径与解析
|   |-- retrace-index.py          # 建立 / 刷新 FTS 索引
|   |-- retrace-search.py         # 搜索（FTS 或混合）
|   |-- retrace-locate.py         # 定位会话文件
|   |-- retrace-analyze.py        # 基于搜索结果的 AI 分析
|   |-- retrace-chronicle.py      # 单会话历史抽取
|   |-- retrace-recover.py        # 从历史恢复文件版本
|   |-- list-session.py
|   |-- clean-index.py
|-- tests/
|-- AGENTS.md
```

## 环境准备

项目以 Windows 为主，但 Python 运行脚本和 shell 示例可以在常见 Unix 环境中运行。

```powershell
$env:RETRACE_SCRIPTS = Join-Path (Get-Location) "skills\retrace\scripts"
$PYTHON_CMD = "python"
```

```sh
RETRACE_SCRIPTS="$(pwd)/skills/retrace/scripts"
PYTHON_CMD="python3"
```

索引和搜索不需要额外 Python 依赖：现代 Python 自带 SQLite FTS5；若缺失会自动回退到 FTS4。

AI 摘要和分析会调用 `codex exec`，默认不绕过沙箱与审批检查。只有在受信任的本地环境下，且确实需要旧版跳过行为时，才设置 `RETRACE_ALLOW_UNSANDBOXED_AI=1`。

## 建立索引

搜索之前始终先确保索引是最新的。

```powershell
# Codex
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-index.py" --auto --platform codex --project poly-retrace --no-summary

# Claude Code
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-index.py" --auto --platform claude --project poly-retrace --no-summary

# Pi
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-index.py" --auto --platform pi --project poly-retrace --no-summary

# 查看统计
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-index.py" --stats --platform codex
```

```sh
"$PYTHON_CMD" "$RETRACE_SCRIPTS/retrace-index.py" --auto --platform codex --project poly-retrace --no-summary
"$PYTHON_CMD" "$RETRACE_SCRIPTS/retrace-index.py" --auto --platform claude --project poly-retrace --no-summary
"$PYTHON_CMD" "$RETRACE_SCRIPTS/retrace-index.py" --auto --platform pi --project poly-retrace --no-summary
"$PYTHON_CMD" "$RETRACE_SCRIPTS/retrace-index.py" --stats --platform codex
```

日常使用建议始终带上 `--no-summary`。只有需要 Codex 生成会话摘要时再去掉它——那条路径会调用模型、比较慢。

## 搜索

```powershell
# 列出会话
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform codex --list-sessions --project poly-retrace

# 基本查询
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform claude "query" --project poly-retrace

# 混合查询（中英混合、代码、日志优先使用）
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform codex --hybrid "Wi-Fi whd_bus_sdio_init_oob_intr EEXIST host-wake" --project poly-retrace
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform pi --hybrid "多 pi 编排 worker_done" --project poly-retrace

# 过滤
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform codex "pwsh" --type tool_use --tool shell_command --project poly-retrace

# 按结果 id 查看上下文
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --context <id> --before 5 --after 5

# 查看单条记录的完整内容
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --full <id>
```

什么时候优先使用 `--hybrid`：

- 中文短语 + 代码符号，例如 `录音确认超时 req_id`。
- 连字符 / 点号标识符、文件路径，例如 `whd_bus_sdio_init_oob_intr`、`path/to/file.c:123`。
- 粘贴进来的日志片段或错误字符串。

简单英文 / 代码 token（例如 `pwsh`、`shell_command` 或单个函数名），默认 FTS 查询依然是最合适的选择。

### 分层输出

| 级别    | 输出内容                     | 近似 token |
|---------|------------------------------|------------|
| stats   | 计数与分布                   | ~50        |
| list    | id、时间戳、预览             | ~500       |
| detail  | 完整预览、文件位置           | ~2000      |
| full    | 完整消息                     | 不定       |

### 过滤参数

| 参数         | 示例值                                                           |
|--------------|------------------------------------------------------------------|
| `--type`     | `session_meta`, `turn_context`, `user`, `assistant`, `tool_use`, `tool_result` |
| `--role`     | `user`, `assistant`, `tool`                                      |
| `--tool`     | `shell_command`, `apply_patch`, `read_mcp_resource`, `Read`, `Edit` |
| `--project`  | 项目名或编码后路径片段                                           |
| `--session`  | 会话 UUID                                                        |
| `--since`    | ISO 起始日期                                                     |
| `--until`    | ISO 结束日期                                                     |

## 定位会话

```powershell
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-locate.py" --platform codex --session-id <uuid> --json
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-locate.py" --platform codex --list
```

## AI 分析

```powershell
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-analyze.py" "error" --platform codex --prompt "classify error types" --project poly-retrace
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-analyze.py" "bug" --platform claude --prompt "summarize" --json
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-analyze.py" "worker_done" --platform pi --prompt "summarize pi orchestration work" --project poly-retrace
```

结果集较小时走一次 `codex exec`；较大时会被自动分块并行处理。小结果约 5-7 秒/次，大结果每块约 15-22 秒，最多 20 个并发。

## Chronicle（单会话史）

对单个会话做强约束的历史抽取，默认输出 TOON，可切换 JSON：

```powershell
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-chronicle.py" --platform codex --session <uuid> --project poly-retrace --output .\chronicle.toon
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-chronicle.py" --platform codex --file "$HOME\.codex\sessions\2026\05\09\<session>.jsonl" --output .\chronicle.json --json
```

Chronicle 会保留：代码片段、shell / git / npm 命令、涉及的文件路径、错误与堆栈、技术决策，以及返工原因。

## Recover（版本恢复）

当文件修改没进 git 时，从会话日志中重建版本。只信任完整 `Write`、完整 `Read`，以及 `cat` 类完整输出。

```powershell
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-recover.py" --platform codex --session <uuid> --project poly-retrace --file "skills\retrace\scripts\retrace-index.py" --output .\recovery
```

## 技能入口

`skills/retrace/SKILL.md` 是支持的 agent 客户端的 skill 入口，触发语包括“查找以前的对话”、“回忆做过什么”、“搜索历史”、“恢复文件”等。skill 最终调用的就是上述脚本。

## 故障排查

| 问题                                | 解决方法                                                                                     |
|-------------------------------------|----------------------------------------------------------------------------------------------|
| 提示“索引数据库不存在”              | 运行 `retrace-index.py --auto --platform <codex|claude|pi> --project <name> --no-summary`。 |
| 搜不到结果                          | 检查 `--project` 过滤，放宽关键词，然后用 `--hybrid` 重试。                                  |
| 查询含 `-` 时 FTS 报错              | 升级到当前脚本；遇到非单词字符时会自动加引号。                                               |
| 控制台输出乱码                      | 使用 PowerShell 7 运行；脚本也会强制 UTF-8 stdio。                                           |
| analyze / chronicle 输出为空        | 检查文件路径，先确认 search 能命中记录。                                                     |

## 版本

本项目仅作为独立 skill 分发。版本信息见 `skills/retrace/SKILL.md` 和各脚本文件头。
