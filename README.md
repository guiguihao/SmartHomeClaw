# SmartHome Agent / 智能家居 Agent

[English](#english) | [中文](#中文)

---

<a name="english"></a>
## English Description

An OpenClaw-inspired local AI Agent framework for smart home automation. It supports dynamic model switching, heartbeat checks, cron-based scheduling, MCP server integration, and a modular Skill plugin system.

### Quick Start
1. **Configure API Keys**: `cp .env.example .env` and fill in your keys.
2. **Set Default Model**: Edit `config/agent.yaml` to choose your provider/model.
3. **Run**: `source .venv/bin/activate && python main.py`.

### Features
- **Multi-Model**: Compatible with OpenAI protocol (GPT-4o, DeepSeek-v3, Claude, Ollama).
- **Memory**: Persistent file-based memory (User profile, Habits, Facts).
- **Automation**: Cron scheduling (`/cron`) and background health checks (`HEARTBEAT.md`).
- **Extensibility**: Standard MCP Client and directory-based Python Skills.

---

<a name="中文"></a>
## 中文说明

基于OpenClaw架构打造的智能家居 AI Agent，支持多模型切换、心跳机制、定时任务、MCP Server 集成和 Skill 插件系统。

### 快速开始
1. **配置 API Key**: `cp .env.example .env` 并填入 Key。
2. **设置默认模型**: 在 `config/agent.yaml` 中选择默认模型。
3. **启动**: `source .venv/bin/activate && python main.py`。

### 核心功能
- **多模型支持**: 兼容 OpenAI 协议（GPT-4o, DeepSeek-v3, Claude, Ollama）。
- **记忆系统**: 基于文件的持久化记忆（用户画像、生活习惯、环境事实）。
- **自动化**: Cron 定时任务 (`/cron`) 与后台心跳自检 (`HEARTBEAT.md`)。
- **高扩展性**: 支持标准 MCP 协议与目录式 Python Skill 插件。

---

## CLI Commands / 命令行命令

| Command / 命令 | Description / 说明 |
|------|------|
| `/help` | Show help / 显示帮助 |
| `/quit` | Exit Agent / 退出 |
| `/status` | Check system status / 查看状态 |
| `/model [name]` | Switch LLM / 切换模型 |
| `/cron [list\|add\|del]` | Manage schedules / 管理定时任务 |
| `/memory` | View memory files / 查看记忆 |
| `/heartbeat` | Trigger heartbeat / 手动心跳 |
| `/skills` | List loaded skills / 查看插件 |
| `/mcp` | List MCP connections / 查看 MCP |

## Developer Guide / 开发者指南

### Add Skills / 添加插件
Create a subdirectory in `skills/` with `skill.py` (inheriting `BaseSkill`) and `SKILL.md`.  
在 `skills/` 下创建子目录，包含 `skill.py`（继承 `BaseSkill`）和 `SKILL.md`。

### Memory Files / 记忆文件
- `memory/USER_PROFILE.md`: User preferences / 用户偏好
- `memory/HABITS.md`: Discovered habits / 自动发现的习惯
- `memory/FACTS.md`: Static home facts / 环境固定事实
