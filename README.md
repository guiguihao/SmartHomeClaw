# SmartHomeClaw Agent

基于 Node.js 开发的智能家居 AI 管家，由先进的语言模型驱动，具备自主感知、决策、记忆及多端通信能力。

## 🌟 核心特性
- **内置mcp**: 内置米家mcp, 悠瑞mcp
- **🚀 多平台接入**：通过 `MessengerBridge` 实现飞书（Feishu）等平台的无缝集成，支持交互式卡片回复及流式输出。
- **🧩 技能系统 (Skills)**：支持动态加载 `skills/` 目录下的脚本。
  - **知识技能**：支持标准 `SKILL.md` 格式（带 YAML 前置参数），让 AI 瞬间学会使用第三方 API。
- **🧠 长期记忆 (Memory)**：基于本地 Markdown 文件的记忆系统。
  - **UserProfile**: 记录用户偏好与习惯。
  - **Facts**: 记录家居设备状态与重要事实。
  - **Environment**: **自动同步**室外天气、未来预报及传感器上报数据。
- **💓 智能巡检 (Heartbeat)**：定时执行系统自检、环境数据同步及异常告警推送。
- **📅 自动化任务 (Cron)**：灵活的定时任务管理，支持 AI 自主添加、删除及开关任务。
- **🔌 MCP 支持**：完美兼容 Model Context Protocol，可无缝接入各种 MCP Server 扩展能力。

## 📂 目录结构

```text
.
├── config/             # 配置文件 (yaml)
│   ├── agent.yaml      # Agent 基础与模型配置
│   ├── heartbeat.yaml  # 心跳检查项配置
│   ├── cron.yaml       # 定时任务持久化
│   └── plugin.yaml     # 插件/平台参数
├── mcp/                # MCP Server 目录
├── memory/             # 长期记忆存储 (Markdown)
│   ├── USER_PROFILE.md
│   ├── HABITS.md
│   ├── FACTS.md
│   └── ENVIRONMENT.md  # 环境快照记忆
├── skills/             # 技能库
│   └── weather/        # 标准 MD 技能示例 (SKILL.md)
├── src/
│   ├── agent.js        # 系统入口
│   ├── services/       # 核心服务 (CoreAgent, Skill, Memory, etc.)
│   └── plugin/         # 平台适配器 (Feishu, MessengerBridge)
└── sessions/           # 历史会话备份与去重缓存
```

## 🛠️ 快速开始

### 1. 安装依赖
```bash
npm install
```

### 2. 配置环境
复制 `.env.example` 到 `.env` 并填写相关 API Key 和插件密钥：
- `FEISHU_APP_ID` / `FEISHU_APP_SECRET`
- `NVIDIA_API_KEY` (或其它 Provider 的 Key)

### 3. 配置提示词与模型
在 `config/agent.yaml` 中修改 `system_prompt` 来定义您的 AI 管家性格。

### 4. 启动 Agent
```bash
npm start
```

## 💡 常用指令

### 会话控制指令
您可以在聊天窗口直接发送以下指令来管理对话：
- **`/new`** 或 **`/新会话`**：备份并清空当前会话历史，开启全新对话。
- **`/context`** 或 **`/上下文`**：查看当前会话的统计信息（消息条数）及 AI 自动生成的上下文摘要。
- **`/compress`** 或 **`/压缩`**：强制对当前冗长的会话进行压缩总结，以节省 Token 并提升响应速度。

### AI 技能指令示例
- “列出你现在的技能”
- “执行 weather 技能，参数是 city=上海”
- “创建一个每天早上 8 点提醒我带伞的定时任务”

## 📡 智能巡检与环境同步
系统每隔一段时间会触发 `Heartbeat`。其中“环境同步”任务会自动通过 `wttr.in` 获取天气，并调用 `memory_update_environment` 工具将其存入 `ENVIRONMENT.md`。

## 🤝 开发与贡献
1. **添加新服务**: 在 `src/services/` 下实现逻辑，并在 `agent.js` 中注册。
2. **添加新平台**: 在 `src/plugin/` 下实现适配器，并注册到 `MessengerBridge`。

## 📄 许可证
MIT
