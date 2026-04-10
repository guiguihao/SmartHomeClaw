# AGENTS.md - SmartHome AI 管家 项目指引

> **本文件是写给 AI 编程助手的操作手册。每次开始新的对话或任务前，AI 必须优先完整阅读此文件。**

---

## 🧠 AI 会话提示词（必读）

你正在协助开发一套名为 **SmartHome AI 管家** 的智能家居 AI Agent 系统。请在所有代码和对话中遵循以下原则：

1.  **单一职责微服务架构**：此项目是解耦的多进程微服务系统，核心组件是"Agent API 服务器"和"网关（Gateway）"，绝对不要将它们的代码混在一起。
2.  **理解数据流方向**：用户消息 → 飞书网关 → Agent API (`/v1/chat`) → Agent 核心引擎 → Tool调用/模型 → 返回回复 → 飞书网关 → 用户。每一个修改都要遵循这个链路的上下文。
3.  **涉及 AI 行为时谨慎修改**：`src/core/agent.py` 是核心引擎，`config/agent.yaml` 是主配置，`config/HEARTBEAT.md` 是心跳任务指令，修改这些文件会直接改变 AI 的行为。
4.  **技能（Skill）开发标准**：所有技能必须在 `skills/<name>/` 目录下，需包含 `skill.py`（BaseSkill 子类）和 `SKILL.md`（技能文档）。新增技能后需在 `config/agent.yaml` 中注册才能生效。
5.  **保持中文注释**：所有代码注释、文档字符串必须使用中文，保持项目规范一致性。

---

## 📁 项目目录结构

```
ureal_agent/
├── main.py                  # CLI 入口（交互式对话模式）
├── launcher.py              # 微服务统一启动器（生产环境使用）
├── requirements.txt
│
├── config/
│   ├── agent.yaml           # ⭐ 核心配置（模型、技能、MCP服务器、心跳）
│   ├── services.yaml        # 微服务启动配置（由 launcher.py 读取）
│   ├── crons.yaml           # 定时任务
│   └── HEARTBEAT.md         # 心跳任务指令内容
│
├── src/
│   ├── core/
│   │   ├── agent.py         # ⭐ Agent 核心引擎（对话循环、工具调度）
│   │   ├── model.py         # 模型客户端（多 Provider 统一接口）
│   │   ├── heartbeat.py     # 心跳调度器
│   │   └── cron.py          # 定时任务调度器
│   ├── server/
│   │   └── main.py          # FastAPI HTTP 服务器（/v1/chat 接口）
│   ├── memory/
│   │   └── manager.py       # 记忆管理器
│   ├── mcp/
│   │   └── client.py        # MCP 协议客户端（连接外部工具服务）
│   ├── skills/
│   │   └── loader.py        # 技能加载器
│   └── cli/
│       └── main.py          # CLI 工具集（含 build_agent 工厂函数）
│
├── services/
│   └── feishu/
│       └── main.py          # ⭐ 飞书 WebSocket 网关（独立进程运行）
│
├── skills/                  # 所有技能模块目录
│   └── <skill_name>/
│       ├── skill.py         # 技能实现（必须是 BaseSkill 的子类）
│       └── SKILL.md         # 技能文档（描述用途和工具定义）
│
├── memory/                  # 运行时记忆文件（不提交 Git）
│   ├── USER_PROFILE.md
│   ├── HABITS.md
│   └── FACTS.md
│
├── sessions/                # 会话历史（JSON 持久化，不提交 Git）
└── logs/                    # 日志文件（按日切分）
```

---

## ⚙️ 环境配置

- **根目录**：所有命令必须在仓库根目录执行（`$HOME/ureal_agent`）。
- **虚拟环境**：使用 `source .venv/bin/activate`，也可以使用系统 Python。
- **安装依赖**：`pip install -r requirements.txt`
- **环境变量**：`cp .env.example .env`，然后填写以下必要的 Key：
  - `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, `ANTHROPIC_API_KEY`, `VOLCENGINE_API_KEY`
  - `FEISHU_APP_ID`, `FEISHU_APP_SECRET`
- **禁止缓存**：`.env` 中已设置 `PYTHONDONTWRITEBYTECODE=1`，不会生成 `__pycache__`。

---

## 🚀 核心命令

| 命令 | 用途 |
|---|---|
| `python main.py chat` | 交互式 CLI 模式（含心跳/定时任务） |
| `python launcher.py start` | 启动全部微服务（生产环境使用） |
| `python launcher.py stop` | 停止全部微服务 |
| `python launcher.py restart` | 重启所有微服务 |
| `nohup python launcher.py > logs/serve.out 2>&1 &` | 后台持久化运行 |
| `pytest tests/test_feishu_direct.py -v` | 运行飞书集成测试 |

---

## 🏗️ 微服务架构

系统采用完全解耦的多进程微服务架构：

```
[飞书用户]
    │ WebSocket
    ▼
[services/feishu/main.py]  ← 独立进程，飞书 WebSocket 网关
    │ HTTP POST /v1/chat
    ▼
[src/server/main.py]       ← FastAPI 服务器 (127.0.0.1:8000)
    │ await agent.chat()
    ▼
[src/core/agent.py]        ← Agent 核心引擎
    │
    ├── MemoryManager      (src/memory/)
    ├── MCPRegistry        (src/mcp/)      ← 连接外部 MCP 工具服务器
    └── SkillLoader        (src/skills/)   ← 加载 skills/ 目录下的技能
```

---

## 🔧 关键配置说明

- **`config/agent.yaml`**：主配置文件，定义模型默认值、MCP 服务器列表、技能启用开关、心跳设置。
- **`config/services.yaml`**：控制微服务的启停，由 `launcher.py` 读取。
- **切换模型**：CLI 中输入 `/model <name>`，可切换的模型列在 `config/agent.yaml` 的 `providers` 节。
- **定时任务**：通过 `/cron` 命令管理，配置持久化到 `config/crons.yaml`。
- **心跳**：默认每 5 分钟执行一次，执行内容由 `config/HEARTBEAT.md` 文件定义。

---

## 🧩 技能（Skill）系统

新增一个技能的完整步骤：
1.  在 `skills/<skill_name>/` 下创建目录。
2.  创建 `skill.py`，继承 `BaseSkill`，实现工具定义和处理逻辑。
3.  创建 `SKILL.md`，描述技能的用途和使用方法。
4.  在 `config/agent.yaml` 的 `skills` 节中注册，设置 `enabled: true`。

**飞书多机器人**：在 `agent.yaml` 的 `skills.feishu.apps` 下配置多个 bot，每个 bot 在独立进程中运行，通过 `app_name` 区分会话隔离。

---

## 🔌 MCP 服务器

- 配置位于 `agent.yaml` 的 `mcp_servers` 节，使用 `stdio` 传输方式。
- `command` 字段必须使用**绝对路径**（因为工作目录会被切换到项目根目录）。

---

## ⚠️ 开发注意事项（Critical Quirks）

- **工作目录**：`launcher.py` 和 `main.py` 启动时会显式调用 `os.chdir(ROOT)`，所有配置文件中的相对路径都是相对于**项目根目录**的。
- **日志**：日志按天滚动切分，保存在 `logs/` 目录下（`agent.log`, `feishu_gateway.log` 等）。控制台默认只显示 `WARNING`+，调试时可设置 `LOG_LEVEL=DEBUG`。
- **会话隔离**：飞书多用户的会话通过 `{app_name}:{open_id}` 作为 `session_id` 进行隔离，每个会话对应 `sessions/` 目录下的独立 JSON 文件。
- **Python 版本**：代码需兼容 Python 3.10+。注意不要在 f-string 大括号 `{}` 内直接使用反斜杠（Python 3.12 以下报错），建议先将表达式赋值给变量再引用。
- **`tool_call` 循环**：`agent.py` 中的 `chat` 方法在模型发起工具调用时会进行多次循环。修改此逻辑时务必注意不要引入 assistant 消息被重复加入历史的 Bug（已知问题，已修复）。

---

## 🐛 常见问题排查

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| `FileNotFoundError: 'python'` | Linux 系统只有 `python3` | `launcher.py` 已自动用 `sys.executable` 替换 |
| `ModuleNotFoundError` | 使用了系统 Python | 激活虚拟环境后重新安装依赖 |
| `SyntaxError: f-string backslash` | Python < 3.12 | 将表达式移出 f-string 大括号，先赋值给变量 |
| 飞书回复内容重复 | assistant 消息被写入历史两次 | 已修复（循环内的 `history.append` 是唯一写入点） |
| 端口 8000 已占用 | 服务未完全停止 | 运行 `python launcher.py restart` |
