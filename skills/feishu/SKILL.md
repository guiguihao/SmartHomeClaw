# Feishu (Lark) Skill / 飞书插件

[English](#english) | [中文](#中文)

---

<a name="english"></a>
## English Description

This plugin allows the SmartHome Agent to interact with the Feishu (Lark) Open Platform. It supports sending text messages and **real-time message listening** via WebSocket (Long Connection).

### Features
- **Send Messages**: Proactively send alerts or status updates.
- **Real-time Listening**: Receive events from Lark without a public IP (WebSocket).
- **AI Auto-Reply**: Automatically process and reply to incoming messages using independent AI reasoning.

### Setup Instructions

1.  **Create App**: Log in to the [Lark Open Platform](https://open.feishu.cn/), create an "Internal App".
2.  **Enable Features**: Enable "Bot" in "App Capabilities".
3.  **Permissions**: Grant:
    - `im:message:send_as_bot` (Send messages)
    - `im:message` (Read messages)
4.  **Event Subscription (Crucial)**:
    - Go to **Events & Callbacks** -> **Event Configuration**.
    - Select **"Receive events through persistent connection"**.
    - Add event: `p2.im.message.receive_v1` (Receive messages).
5.  **Config**: Update `config/agent.yaml`.

### Configuration (`agent.yaml`)
```yaml
skills:
  feishu:
    app_id_env: "FEISHU_APP_ID"
    app_secret_env: "FEISHU_APP_SECRET"
    enable_listener: true   # Enable background listening
    auto_reply: true        # Enable AI response
```

---

<a name="中文"></a>
## 中文说明

该插件使 SmartHome Agent 支持通过飞书进行消息交互，现已升级支持 **长连接实时监听**。

### 功能特性
- **主动发送**：向指定用户或群聊推送消息。
- **实时接收**：无需公网 IP，通过 WebSocket 接收飞书机器人消息。
- **AI 自动回复**：收到消息后，Agent 会在后台独立思考并自动回复。

### 接入指南

1.  **创建应用**：登录 [飞书开放平台](https://open.feishu.cn/)，创建“企业自建应用”。
2.  **启用机器人**：在“应用能力”中开启“机器人”功能。
3.  **权限配置**：在“权限管理”中勾选：
    - `im:message:send_as_bot` (发送消息)
    - `im:message` (接收消息内容)
4.  **事件订阅（核心步骤）**：
    - 进入“事件订阅”页面。
    - **订阅方式** 切换为 **“通过长连接接收事件”** (WebSocket)。
    - **添加事件**：搜索并添加 `接收消息` (v1.0)。
5.  **本地配置**：修改 `config/agent.yaml` 并确保 `.env` 中填入了凭证。

### 配置文件示例 (`config/agent.yaml`)
```yaml
skills:
  feishu:
    app_id_env: "FEISHU_APP_ID"        # 环境变量引用模式
    app_secret_env: "FEISHU_APP_SECRET"
    enable_listener: true              # 开启后台实时监听
    auto_reply: true                   # 开启 AI 自动回信
```

### 提供的工具
- `send_text_message`: 主动发送消息。
