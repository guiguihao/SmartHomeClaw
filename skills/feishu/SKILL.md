# Feishu (Lark) Skill / 飞书插件

[English](#english) | [中文](#中文)

---

<a name="english"></a>
## English Description

This plugin provides the SmartHome Agent with the ability to **proactively send messages** to Feishu (Lark). It is used by the Agent to notify users about device status, alerts, or scheduled task completions.

**Note:** Real-time message listening is now handled by the standalone `Feishu Gateway` service (`services/feishu/`).

### Features
- **Send Messages**: Proactively send text messages to users or groups.
- **Multi-Bot Support**: Can target different bots configured in `agent.yaml`.

### Provided Tools
- `send_text_message`: Send a text message to a receiver ID.

---

<a name="中文"></a>
## 中文说明

该插件为 SmartHome Agent 提供了**主动发送飞书消息**的能力。Agent 可以利用此工具向用户推送设备状态、警报信息或定时任务执行结果。

**注意：** 实时消息监听功能已移至独立的 `飞书网关 (Feishu Gateway)` 服务 (`services/feishu/`)。

### 功能特性
- **主动发送**：向指定用户或群聊推送文本消息。
- **多机器人支持**：支持根据配置选择不同的机器人发送消息。

### 提供的工具
- `send_text_message`: 向指定的接收者 ID 发送文本消息。
