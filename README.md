# SmartHomeClaw / 智能家居龙虾

[English](#english) | [中文](#中文)

---

<a name="english"></a>
## English Description

An OpenClaw-inspired local AI Agent framework for smart home automation. It supports dynamic model switching, heartbeat checks, cron-based scheduling, MCP server integration, a modular Skill plugin system, and **real-time Feishu (Lark) messaging**.

### Features

- 🤖 **Multi-Model Support** — OpenAI, DeepSeek, Claude, Ollama (local)
- 🧠 **Persistent Memory** — Automatically records user habits & preferences
- ⏰ **Cron Scheduling** — Time-based scene automation
- 💓 **Heartbeat** — Silent background health checks every 5 min
- 🔌 **MCP Server** — Connect any MCP-compatible smart home server
- 🧩 **Skill Plugin System** — Extensible third-party integrations
- 📱 **Feishu Integration** — Real-time WebSocket listener + AI auto-reply

---

### Quick Start

#### 1. Configure Environment
```bash
cp .env.example .env
# Fill in your API Keys
```

#### 2. Set Default Model in `config/agent.yaml`
```yaml
model:
  default: "deepseek-v3"   # Change to your preferred model
```

#### 3. Run Agent

```bash
# Activate virtual environment
source .venv/bin/activate

# Show all available commands
python main.py

# Enter interactive chat mode
python main.py chat

# Start backend services only (Feishu listener + Heartbeat + Cron, no CLI)
python main.py serve
```

---

### Launch Modes

| Command | Description |
|---------|-------------|
| `python main.py` | Show help menu |
| `python main.py chat` | Interactive CLI chat mode |
| `python main.py serve` | Backend-only mode (ideal for production / always-on) |

> **Tip**: Use `serve` mode with `nohup` to run persistently in the background:
> ```bash
> nohup .venv/bin/python main.py serve &
> ```

---

### In-Chat Commands (`/` slash commands)

| Command | Description |
|---------|-------------|
| `/help` | Show help |
| `/quit` | Exit |
| `/clear` | Clear chat history |
| `/status` | View Agent status |
| `/model [name]` | View or switch model |
| `/memory` | View memory content |
| `/cron list` | List scheduled tasks |
| `/cron add` | Add scheduled task (guided) |
| `/cron del <id>` | Delete scheduled task |
| `/heartbeat` | Trigger heartbeat now |
| `/skills` | List loaded Skills |
| `/mcp` | List MCP connections |

---

### Feishu (Lark) Integration

The Feishu Skill supports **sending messages** and **real-time listening** via WebSocket — no public IP required.

#### Setup Steps

1. Log in to the [Lark Open Platform](https://open.feishu.cn/) and create an "Internal App".
2. In **App Capabilities**, enable **Bot**.
3. In **Permissions**, grant:
   - `im:message:send_as_bot`
   - `im:message`
4. In **Events & Callbacks → Event Configuration**, switch subscription to **"Receive events through persistent connection"** and add the `p2.im.message.receive_v1` event.
5. Configure in `config/agent.yaml`:

```yaml
skills:
  feishu:
    app_id_env: "FEISHU_APP_ID"
    app_secret_env: "FEISHU_APP_SECRET"
    enable_listener: true    # Enable real-time listener
    auto_reply: true         # AI auto-reply to incoming messages
```

6. Add credentials to `.env`:

```env
FEISHU_APP_ID=cli_xxxxxxxx
FEISHU_APP_SECRET=xxxxxxxx
```

---

### Supported Models (OpenAI Protocol Compatible)

| Provider | Model |
|----------|-------|
| **OpenAI** | gpt-4o, gpt-4o-mini |
| **DeepSeek** | deepseek-v3 (Recommended) |
| **Anthropic** | claude-sonnet |
| **NVIDIA** | openai/gpt-oss-120b |
| **Ollama** | qwen2.5, llama3, etc. |

Switch with: `/model deepseek-chat`

---

### Adding a Skill Plugin

Create a subdirectory under `skills/`:

```text
skills/
└── your_brand/
    ├── SKILL.md      # Documentation
    └── skill.py      # Implements BaseSkill
```

Reference: `skills/demo_smarthome/skill.py`

---

### MCP Server Integration

Configure in `config/agent.yaml`:

```yaml
mcp_servers:
  - name: "smarthome"
    transport: "stdio"
    command: ["python3", "/path/to/smarthome_mcp/server.py"]
```

---

### Memory System

Agent automatically writes discovered habits to the `memory/` directory:

| File | Description |
|------|-------------|
| `memory/USER_PROFILE.md` | User preferences (manually editable) |
| `memory/HABITS.md` | Auto-discovered habits |
| `memory/FACTS.md` | Static home info (manual entry recommended) |

---

### Scheduled Scenes

```
/cron add
> Task ID: morning_routine
> Task Name: Morning Mode
> Cron: 0 7 * * *
> Description: Turn on living room lights, brightness 80%, report today's weather
```

---

<a name="中文"></a>
## 中文说明

基于 OpenClaw 思想打造的本地智能家居 AI Agent，支持多模型切换、心跳机制、定时任务、MCP Server 集成、Skill 插件系统，以及**飞书实时消息收发**。

### 功能特性

- 🤖 **多模型支持** — OpenAI、DeepSeek、Claude、Ollama 本地模型
- 🧠 **持久化记忆** — 自动记录用户习惯与偏好
- ⏰ **Cron 定时任务** — 基于时间的场景自动化
- 💓 **心跳机制** — 每 5 分钟在后台静默自检
- 🔌 **MCP Server** — 接入任意 MCP 兼容的智能家居服务端
- 🧩 **Skill 插件系统** — 可扩展的第三方服务集成
- 📱 **飞书集成** — WebSocket 实时监听消息 + AI 自动回复

---

### 快速开始

#### 1. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入你的 API Key
```

#### 2. 在 `config/agent.yaml` 中选择默认模型

```yaml
model:
  default: "deepseek-v3"   # 改成你要用的模型
```

#### 3. 启动 Agent

```bash
# 激活虚拟环境
source .venv/bin/activate

# 查看所有可用命令（默认行为）
python main.py

# 进入对话模式
python main.py chat

# 仅启动后台服务（飞书监听 + 心跳 + Cron，无 CLI 对话）
python main.py serve
```

---

### 启动模式说明

| 命令 | 描述 |
|------|------|
| `python main.py` | 显示帮助菜单 |
| `python main.py chat` | 进入交互式 CLI 对话模式 |
| `python main.py serve` | 仅运行后台服务（适合生产环境/常驻后台） |

> **提示**：使用 `serve` 模式配合 `nohup` 可实现持久后台运行：
> ```bash
> nohup .venv/bin/python main.py serve &
> ```

---

### 对话模式内置命令（`/` 斜杠命令）

| 命令 | 说明 |
|------|------|
| `/help` | 显示帮助 |
| `/quit` | 退出 |
| `/clear` | 清除对话历史 |
| `/status` | 查看 Agent 状态 |
| `/model [名称]` | 查看/切换模型 |
| `/memory` | 查看记忆内容 |
| `/cron list` | 列出定时任务 |
| `/cron add` | 添加定时任务（引导式） |
| `/cron del <id>` | 删除定时任务 |
| `/heartbeat` | 立即触发心跳 |
| `/skills` | 查看已加载 Skill |
| `/mcp` | 查看 MCP 连接 |

---

### 飞书（Lark）插件接入

飞书 Skill 支持**主动发送消息**和通过 WebSocket **实时接收消息**——无需公网 IP，本地就能运行。

#### 接入步骤

1. 登录 [飞书开放平台](https://open.feishu.cn/)，创建"企业自建应用"。
2. 在"应用能力"中开启**机器人**功能。
3. 在"权限管理"中勾选：
   - `im:message:send_as_bot`（发送消息）
   - `im:message`（读取消息内容）
4. 在"事件订阅"页面，将订阅方式切换为**"通过长连接接收事件"**，并添加 `接收消息 v1` 事件。
5. 在 `config/agent.yaml` 中配置：

```yaml
skills:
  feishu:
    app_id_env: "FEISHU_APP_ID"         # 环境变量名
    app_secret_env: "FEISHU_APP_SECRET"
    enable_listener: true               # 开启实时监听
    auto_reply: true                    # 开启 AI 自动回复
```

6. 在 `.env` 中填入凭证：

```env
FEISHU_APP_ID=cli_xxxxxxxx
FEISHU_APP_SECRET=xxxxxxxx
```

---

### 支持的模型（OpenAI 协议兼容）

| 供应商 | 模型 |
|--------|------|
| **OpenAI** | gpt-4o, gpt-4o-mini |
| **DeepSeek** | deepseek-v3（推荐，性价比高） |
| **Anthropic** | claude-sonnet |
| **NVIDIA** | openai/gpt-oss-120b |
| **Ollama** | qwen2.5、llama3 等本地模型 |

切换命令：`/model deepseek-chat`

---

### 添加 Skill 插件

在 `skills/` 目录下创建子目录：

```text
skills/
└── 你的品牌名/
    ├── SKILL.md      # 接入说明文档
    └── skill.py      # 继承 BaseSkill 的实现类
```

参考实现：`skills/demo_smarthome/skill.py`

---

### 接入 MCP Server

在 `config/agent.yaml` 中配置：

```yaml
mcp_servers:
  - name: "smarthome"
    transport: "stdio"
    command: ["python3", "/path/to/smarthome_mcp/server.py"]
```

---

### 记忆系统

Agent 会自动发现用户习惯并写入 `memory/` 目录：

| 文件 | 说明 |
|------|------|
| `memory/USER_PROFILE.md` | 用户偏好（可手动编辑） |
| `memory/HABITS.md` | 自动发现的习惯记录 |
| `memory/FACTS.md` | 家居固定信息（建议手动填写） |

---

### 定时场景

```
/cron add
> 任务 ID: morning_routine
> 任务名称: 早晨起床模式
> Cron: 0 7 * * *
> 描述: 打开客厅灯，亮度设为80%，播报今日天气
```
