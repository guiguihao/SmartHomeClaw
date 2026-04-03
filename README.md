# SmartHomeclaw / 智能家居龙虾

[English](#english) | [中文](#中文)

---

<a name="english"></a>
## English Description

An OpenClaw-inspired local AI Agent framework for smart home automation. It supports dynamic model switching, heartbeat checks, cron-based scheduling, MCP server integration, and a modular Skill plugin system.

### Quick Start

#### 1. Configure API Key
```bash
cp .env.example .env
# Edit .env and fill in your API Key
```

#### 2. Set Default Model in `config/agent.yaml`
```yaml
model:
  default: "deepseek-v3"   # Change to the model you want to use
```

#### 3. Start Agent
```bash
# Activate virtual environment
source .venv/bin/activate

# Start conversation
python main.py
```

### CLI Commands

| Command | Description |
|------|------|
| `/help` | Show help |
| `/quit` | Exit |
| `/clear` | Clear chat history |
| `/status` | Check Agent status |
| `/model [name]` | View/Switch model |
| `/memory` | View memory content |
| `/cron list` | List scheduled tasks |
| `/cron add` | Add scheduled task |
| `/cron del <id>` | Delete scheduled task |
| `/heartbeat` | trigger heartbeat |
| `/skills` | List loaded Skills |
| `/mcp` | List MCP connections |

### Supported Models (OpenAI Protocol Compatible)

Configured in `config/agent.yaml`, selected on startup:

- **OpenAI** GPT-4o / GPT-4o-mini
- **DeepSeek** deepseek-v3 (Recommended, highly cost-effective)
- **Anthropic** Claude Sonnet
- **Ollama** Local models (qwen2.5, llama3 etc.)

Switch command: `/model deepseek-chat`

### Adding Skills (Smart Home Device Integration)

Create a subdirectory under `skills/`:

```text
skills/
└── your_brand_name/
    ├── SKILL.md      # Setup documentation
    └── skill.py      # Implements BaseSkill
```

Reference: `skills/demo_smarthome/skill.py`

### MCP Server Integration

Configure in `config/agent.yaml`:

```yaml
mcp_servers:
  - name: "smarthome"
    transport: "stdio"
    command: ["python3", "/path/to/smarthome_mcp/server.py"]
```

### Memory System

Agent automatically discovers user habits and writes to the `memory/` directory:

- `memory/USER_PROFILE.md` - User preferences (editable manually)
- `memory/HABITS.md` - Auto-discovered habits
- `memory/FACTS.md` - Static home information (manual entry recommended)

### Heartbeat Mechanism

Agent automatically executes health checks from `config/HEARTBEAT.md` silently in the background every 5 minutes (configurable).

### Scheduled Scenes

```text
/cron add
> Task ID: morning_routine
> Task Name: Morning Mode
> Cron: 0 7 * * *
> Description: Turn on living room lights, set brightness to 80%, report today's weather
```

---

<a name="中文"></a>
## 中文说明

基于 OpenClaw 思想打造的智能家居 AI Agent，支持多模型切换、心跳机制、定时任务、MCP Server 集成和 Skill 插件系统。

### 快速开始

#### 1. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env，填入你的 API Key
```

#### 2. 在 config/agent.yaml 中选择默认模型

```yaml
model:
  default: "deepseek-v3"   # 改成你要用的模型
```

#### 3. 启动 Agent

```bash
# 激活虚拟环境
source .venv/bin/activate

# 启动对话
python main.py
```

### CLI 命令

| 命令 | 说明 |
|------|------|
| `/help` | 显示帮助 |
| `/quit` | 退出 |
| `/clear` | 清除对话历史 |
| `/status` | 查看 Agent 状态 |
| `/model [名称]` | 查看/切换模型 |
| `/memory` | 查看记忆内容 |
| `/cron list` | 列出定时任务 |
| `/cron add` | 添加定时任务 |
| `/cron del <id>` | 删除定时任务 |
| `/heartbeat` | 触发心跳 |
| `/skills` | 查看已加载 Skill |
| `/mcp` | 查看 MCP 连接 |

### 支持的模型（OpenAI 协议兼容）

在 `config/agent.yaml` 中配置，启动时选择：

- **OpenAI** GPT-4o / GPT-4o-mini
- **DeepSeek** deepseek-v3（推荐，性价比高）
- **Anthropic** Claude Sonnet
- **Ollama** 本地模型（qwen2.5、llama3等）

切换命令：`/model deepseek-chat`

### 添加 Skill（智能家居厂商接入）

在 `skills/` 目录下创建子目录：

```text
skills/
└── 你的品牌名/
    ├── SKILL.md      # 接入说明
    └── skill.py      # 继承 BaseSkill 的实现
```

参考：`skills/demo_smarthome/skill.py`

### 接入 MCP Server

在 `config/agent.yaml` 中配置：

```yaml
mcp_servers:
  - name: "smarthome"
    transport: "stdio"
    command: ["python3", "/path/to/smarthome_mcp/server.py"]
```

### 记忆系统

Agent 会自动发现用户习惯并写入 `memory/` 目录：

- `memory/USER_PROFILE.md` - 用户偏好（可手动编辑）
- `memory/HABITS.md` - 自动发现的习惯
- `memory/FACTS.md` - 家居固定信息（建议手动填写）

### 心跳机制

Agent 每 5 分钟（可配置）自动执行 `config/HEARTBEAT.md` 中的检查任务，后台静默运行。

### 定时场景

```text
/cron add
> 任务 ID: morning_routine
> 任务名称: 早晨起床模式
> Cron: 0 7 * * *
> 描述: 打开客厅灯，亮度设为80%，播报今日天气
```
