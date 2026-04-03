# 智能家居 Agent

基于 OpenClaw 架构打造的智能家居 AI Agent，支持多模型切换、心跳机制、定时任务、MCP Server 集成和 Skill 插件系统。

## 快速开始

### 1. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env，填入你的 API Key
```

### 2. 在 config/agent.yaml 中选择默认模型

```yaml
model:
  default: "deepseek-chat"   # 改成你要用的模型
```

### 3. 启动 Agent

```bash
# 激活虚拟环境
source .venv/bin/activate

# 启动对话
python main.py
```

## CLI 命令

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
| `/heartbeat` | 手动触发心跳 |
| `/skills` | 查看已加载 Skill |
| `/mcp` | 查看 MCP 连接 |

## 支持的模型（OpenAI 协议兼容）

在 `config/agent.yaml` 中配置，启动时选择：

- **OpenAI** GPT-4o / GPT-4o-mini
- **DeepSeek** deepseek-v3（推荐，性价比高）
- **Anthropic** Claude Sonnet
- **Ollama** 本地模型（qwen2.5、llama3等）

切换命令：`/model deepseek-chat`

## 添加 Skill（智能家居厂商接入）

在 `skills/` 目录下创建子目录：

```
skills/
└── 你的品牌名/
    ├── SKILL.md      # 接入说明
    └── skill.py      # 继承 BaseSkill 的实现
```

参考：`skills/demo_smarthome/skill.py`

## 接入 MCP Server

在 `config/agent.yaml` 中配置：

```yaml
mcp_servers:
  - name: "smarthome"
    transport: "stdio"
    command: ["python3", "/path/to/smarthome_mcp/server.py"]
```

## 记忆系统

Agent 会自动发现用户习惯并写入 `memory/` 目录：

- `memory/USER_PROFILE.md` - 用户偏好（可手动编辑）
- `memory/HABITS.md` - 自动发现的习惯
- `memory/FACTS.md` - 家居固定信息（建议手动填写）

## 心跳机制

Agent 每 5 分钟（可配置）自动执行 `config/HEARTBEAT.md` 中的检查任务，后台静默运行。

## 定时场景

```
/cron add
> 任务 ID: morning_routine
> 任务名称: 早晨起床模式
> Cron: 0 7 * * *
> 描述: 打开客厅灯，亮度设为80%，播报今日天气
```
