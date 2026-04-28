# 智能家居 MCP 服务器 (UReal Platform)

基于悠瑞 (UReal) 智能家居平台的 MCP 服务器，允许 LLM 通过自然语言发现家庭网关、查看设备列表、查询设备实时状态并下达控制指令。

## 特性

- **多模式通信**：支持 HTTP API 获取配置和场景，支持 MQTT (paho-mqtt) 进行实时高并发设备控制。
- **设备能力解析**：自动解析 `YRDevicePower.plist`，为 LLM 提供每个设备型号的可调节点和合法值描述。
- **实时状态缓存**：内置 SQLite 数据库，自动缓存 MQTT 推送的设备状态，实现高效查询。
- **生命周期自动化**：启动时自动获取 MQTT 凭证、建立连接并订阅所有关联网关的 Topic。

## 核心工具

| 工具 | 说明 |
| --- | --- |
| `smarthome_get_homes` | 获取网关序列号 (SN) 及名称 |
| `smarthome_get_project` | 获取家中的房间和设备树 |
| `smarthome_get_device_capabilities` | 查看设备具体支持哪些控制选项 |
| `smarthome_control_device` | **控制设备**（如开关、温度、模式等） |
| `smarthome_query_device_status` | 查看设备当前状态 |
| `smarthome_execute_scene` | 触发预设的一键场景 |
| `smarthome_get_weather` | 查看网关当地的天气信息 |

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env` 并填入你的 `UREAL_TOKEN` 和 `UREAL_APP_KEY`。

```bash
cp .env.example .env
```

### 3. 使用 Claude 或 OpenClaw 启动

在 MCP 设置中添加该服务器：

```json
{
  "mcpServers": {
    "smarthome": {
      "command": "python",
      "args": ["/绝对路径/zhinengjiaju/smarthome_mcp/server.py"],
      "env": {
        "SMARTHOME_TOKEN": "你的令牌",
        "SMARTHOME_APP_KEY": "你的AppKey",
        "SMARTHOME_PLIST_PATH": "/绝对路径/zhinengjiaju/YRDevicePower.plist"
      }
    }
  }
}
```

## 注意事项

- 本版本不含登录功能，需用户提前提供 `token`。
- MQTT 发布频道：`$Client/Gw/Manage`
- MQTT 订阅频道：`$Gw/Tx/{sn}`
- 请确保本地 Python 3 环境已激活。
