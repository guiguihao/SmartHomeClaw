# SmartHomeClaw Agent

基于 Node.js 开发的智能家居 AI 管家，由先进的语言模型驱动，具备自主感知、决策、记忆、工作流及多端通信能力。

## 🌟 核心特性

- **🔌 内置 MCP 支持**：内置悠瑞智能家居 MCP、小度 DuerOS MCP，可无缝扩展任意 MCP Server。支持每个 Server 独立启用/禁用，配置文件支持 `${ENV_VAR}` 环境变量引用。
- **🚀 多平台接入**：通过 `MessengerBridge` 实现飞书（Feishu）等平台的无缝集成，支持流式输出与消息去重。
- **🧩 技能系统 (Skills)**：动态加载 `skills/` 目录下的技能，自动映射为 AI 可直接调用的顶级工具。
  - **知识技能（MD Skill）**：标准 `SKILL.md` 格式（带 YAML 前置参数），AI 读取手册后通过 `cmd_exec` 执行脚本。
  - **内置技能**：`baidu-search`（百度 AI 搜索）、`weather`（天气查询）。
- **🔄 工作流引擎 (Workflow)**：基于 YAML 的可视化工作流，支持：
  - `decide`：AI 自主决策步骤
  - `skill`：直接调用技能
  - `mcp`：直接调用 MCP 工具
  - `condition`：条件分支（if/else）
  - `parallel`：并行执行多个步骤
  - `notify`：广播消息到飞书
  - `wait`：等待指定时间
  - 步骤间变量传递（`${varName}` 模板）
- **🧠 长期记忆 (Memory)**：基于本地 Markdown 的结构化记忆。
  - `USER_PROFILE.md`：用户偏好与习惯
  - `FACTS.md`：重要事实记录
  - `ENVIRONMENT.md`：自动同步的环境快照（天气、设备状态）
- **💓 智能巡检 (Heartbeat)**：定时执行系统自检、环境数据同步及异常告警推送。
- **📅 定时任务 (Cron)**：灵活的定时任务管理，支持 AI 自主增删改查。

---

## 📂 目录结构

```text
.
├── config/
│   ├── agent.yaml          # Agent 基础配置与系统提示词
│   ├── heartbeat.yaml      # 心跳巡检任务配置
│   ├── cron.yaml           # 定时任务配置
│   ├── plugin.yaml         # 插件参数（飞书、MCPorter 等）
│   ├── mcporter.json       # MCP Server 连接配置（支持 ${ENV_VAR}）
│   └── workflows/          # 工作流定义目录（支持多个 .yaml 文件）
│       └── morning.yaml    # 示例工作流
├── memory/                 # 长期记忆存储（Markdown）
│   ├── USER_PROFILE.md
│   ├── HABITS.md
│   ├── FACTS.md
│   └── ENVIRONMENT.md
├── skills/                 # 技能库
│   ├── baidu-search/       # 百度 AI 搜索技能（SKILL.md + Python 脚本）
│   └── weather/            # 天气查询技能（SKILL.md）
├── plugin/
│   ├── feishu.js           # 飞书平台适配器
│   └── mcporter.js         # MCP Server 客户端（支持 ${ENV_VAR} 替换）
├── src/
│   ├── agent.js            # 系统主入口
│   └── services/
│       ├── coreagent.js    # 核心 AI 引擎（工具调度、会话管理）
│       ├── workflow.js     # 工作流引擎
│       ├── skill.js        # 技能服务
│       ├── memory.js       # 记忆服务
│       ├── scheduler.js    # 定时任务调度器
│       ├── heartbeat.js    # 心跳巡检服务
│       └── messenger.js    # 消息桥接器
├── sessions/               # 会话历史与去重缓存（已 .gitignore）
└── .env.example            # 环境变量模板
```

---

## 🛠️ 快速开始

### 1. 安装依赖
```bash
npm install
pip install python-dotenv requests  # 技能脚本依赖
```

### 2. 配置环境变量
复制 `.env.example` 到 `.env` 并填写：
```env
NVIDIA_API_KEY=your_key       # 语言模型 API Key
FEISHU_APP_ID=cli_xxxxxxxx    # 飞书应用 ID
FEISHU_APP_SECRET=xxxxxxxx    # 飞书应用密钥
BAIDU_API_KEY=xxxx            # 百度 AI 搜索 Key
XIAODU_ACCESS_TOKEN=xxxx      # 小度 DuerOS Token（可选）
```

### 3. 配置 MCP Server
编辑 `config/mcporter.json`，支持直接引用 `.env` 变量：
```json
{
  "mcpServers": {
    "my-server": {
      "enabled": true,
      "url": "https://example.com/mcp",
      "headers": {
        "Authorization": "${MY_TOKEN}"
      }
    }
  }
}
```

### 4. 启动 Agent
```bash
npm run dev    # 开发模式（热重载）
npm start      # 生产模式
```

---

## 🔄 工作流配置

在 `config/workflows/` 下新建任意 `.yaml` 文件即可定义工作流：

```yaml
workflows:
  - id: "my_workflow"
    name: "我的工作流"
    steps:
      - id: "step1"
        type: "skill"
        skill: "baidu-search"
        params:
          query: "今日新闻"
        output: "news"        # 结果存入变量 ${news}

      - id: "step2"
        type: "condition"
        condition: "{{news}} != ''"
        if_true:
          - id: "notify"
            type: "notify"
            message: "📰 今日新闻：${news}"

      - id: "parallel_check"
        type: "parallel"
        steps:
          - id: "check_a"
            type: "decide"
            prompt: "查询设备 A 状态"
            output: "a_status"
          - id: "check_b"
            type: "decide"
            prompt: "查询设备 B 状态"
            output: "b_status"
```

通过飞书触发：`执行工作流 my_workflow`

---

## 💡 常用指令

### 会话管理
| 指令 | 说明 |
|------|------|
| `/new` 或 `/新会话` | 备份并清空当前会话，开启新对话 |
| `/context` 或 `/上下文` | 查看当前会话统计与摘要 |
| `/compress` 或 `/压缩` | 压缩会话历史，节省 Token |

### AI 能力示例
- `"列出当前所有技能"`
- `"执行百度搜索，搜索今日科技新闻"`
- `"执行工作流 morning_workflow"`
- `"查看所有定时任务"`
- `"创建一个每天早上 8 点发送新闻的定时任务"`
- `"查询所有设备状态"`

---

## 📡 智能巡检

`Heartbeat` 定时触发，自动通过 `wttr.in` 获取天气，查询设备状态，更新 `ENVIRONMENT.md` 记忆，并在异常时推送告警到飞书。

---

## 🤝 扩展开发

- **添加技能**：在 `skills/` 下新建目录，包含 `SKILL.md`（手册格式）和执行脚本。
- **添加工作流**：在 `config/workflows/` 下新建 `.yaml` 文件。
- **接入 MCP**：在 `config/mcporter.json` 中添加 Server 配置。
- **添加新平台**：在 `plugin/` 下实现适配器，注册到 `MessengerBridge`。

## 📄 许可证
MIT
