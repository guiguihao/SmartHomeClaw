# 智能家居 Skill 接入说明

## 概述
本 Skill 是智能家居控制插件的**示例模板**。
智能家居厂商可参考此结构提供自己的 Skill。

## 文件说明
- `SKILL.md`：接入文档（即本文件）
- `skill.py`：Skill 实现代码（继承 `BaseSkill`）

## 提供的工具

| 工具名 | 说明 |
|--------|------|
| `control_device` | 控制设备（开关/调节） |
| `query_status` | 查询设备或房间状态 |
| `list_devices` | 列出所有设备 |

## 工具使用示例

```
用户：把客厅灯调暗一点
Agent 调用：skill_demo_smarthome_control_device(device="客厅灯", action="dim", value=30)
```

## 如何接入真实设备
1. 将 `skill.py` 中的模拟逻辑替换为真实 MQTT / HTTP / 厂商 SDK 调用
2. 在 `__init__` 中建立设备连接
3. 将 Skill 目录放入 `skills/` 下，Agent 启动时自动加载

## 接入 MCP Server（另一种方式）
如果厂商提供了 MCP Server，配置 `config/agent.yaml` 中的 `mcp_servers` 即可，无需编写 Skill。
