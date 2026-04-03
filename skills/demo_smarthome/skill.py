"""
智能家居 Skill 示例实现
智能家居厂商参考此模板提供自己的 Skill 接入包
"""
from __future__ import annotations

import json
import logging
from typing import Any

# 将 src 添加到路径（Skill 是独立目录，需要显式引入）
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.skills.base import BaseSkill

logger = logging.getLogger(__name__)


class DemoSmartHomeSkill(BaseSkill):
    """
    智能家居 Skill 示例。
    当前使用模拟数据，替换 _call_real_api 方法即可接入真实设备。
    """

    # 模拟设备数据库（真实场景替换为从网关查询）
    _mock_devices = {
        "客厅灯": {"type": "light", "status": "on", "brightness": 80, "room": "客厅"},
        "主卧灯": {"type": "light", "status": "off", "brightness": 0, "room": "主卧"},
        "空调":   {"type": "ac", "status": "off", "temperature": 26, "mode": "cool"},
        "窗帘":   {"type": "curtain", "status": "open", "level": 100, "room": "客厅"},
    }

    def __init__(self):
        logger.info("[Skill] demo_smarthome 初始化（模拟模式）")
        # 真实接入时：在这里建立 MQTT / HTTP 连接
        # self.mqtt = MQTTClient(host=..., port=...)
        # self.mqtt.connect()

    @property
    def name(self) -> str:
        return "demo_smarthome"

    @property
    def description(self) -> str:
        return "智能家居设备控制（示例，含模拟数据）"

    def get_tools(self) -> list[dict]:
        """返回此 Skill 提供的工具列表"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "control_device",
                    "description": (
                        "控制智能家居设备，支持开关、调光、调温、开关窗帘等操作。"
                        "设备名称使用用户的自然语言称呼，如'客厅灯'、'空调'。"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "device": {
                                "type": "string",
                                "description": "设备名称，如：客厅灯、空调、窗帘、主卧灯",
                            },
                            "action": {
                                "type": "string",
                                "enum": ["on", "off", "set_brightness", "set_temperature", "open", "close"],
                                "description": "操作指令",
                            },
                            "value": {
                                "type": "number",
                                "description": "操作参数（调光时为0-100的亮度值，调温时为温度数值）",
                            },
                        },
                        "required": ["device", "action"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "query_status",
                    "description": "查询指定设备或整个房间的状态信息。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target": {
                                "type": "string",
                                "description": "查询对象，设备名（如：空调）或房间名（如：客厅、全部）",
                            }
                        },
                        "required": ["target"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_devices",
                    "description": "列出家中所有智能设备及其当前状态。",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                    },
                },
            },
        ]

    async def handle_tool_call(self, tool_name: str, args: dict) -> str:
        """路由工具调用到对应处理方法"""
        if tool_name == "control_device":
            return self._control_device(
                args.get("device", ""),
                args.get("action", ""),
                args.get("value"),
            )
        elif tool_name == "query_status":
            return self._query_status(args.get("target", "全部"))
        elif tool_name == "list_devices":
            return self._list_devices()
        else:
            return f"❌ 未知工具：{tool_name}"

    def _control_device(self, device: str, action: str, value=None) -> str:
        """
        模拟设备控制。
        真实接入时：替换为 MQTT publish 或 HTTP POST 调用。
        """
        if device not in self._mock_devices:
            return f"❌ 未找到设备：{device}（可用设备：{', '.join(self._mock_devices.keys())}）"

        dev = self._mock_devices[device]

        if action == "on":
            dev["status"] = "on"
            if dev["type"] == "light":
                dev["brightness"] = value or 80
            return f"✅ {device} 已开启"

        elif action == "off":
            dev["status"] = "off"
            if dev["type"] == "light":
                dev["brightness"] = 0
            return f"✅ {device} 已关闭"

        elif action == "set_brightness":
            if dev["type"] != "light":
                return f"❌ {device} 不支持调光"
            brightness = int(value or 50)
            dev["brightness"] = max(0, min(100, brightness))
            dev["status"] = "on" if brightness > 0 else "off"
            return f"✅ {device} 亮度已调整为 {brightness}%"

        elif action == "set_temperature":
            if dev["type"] != "ac":
                return f"❌ {device} 不支持调温"
            temp = float(value or 26)
            dev["temperature"] = temp
            dev["status"] = "on"
            return f"✅ {device} 温度已设为 {temp}°C"

        elif action == "open":
            if dev["type"] != "curtain":
                return f"❌ {device} 不支持开合操作"
            dev["status"] = "open"
            dev["level"] = 100
            return f"✅ {device} 已打开"

        elif action == "close":
            if dev["type"] != "curtain":
                return f"❌ {device} 不支持开合操作"
            dev["status"] = "closed"
            dev["level"] = 0
            return f"✅ {device} 已关闭"

        else:
            return f"❌ 不支持的操作：{action}"

    def _query_status(self, target: str) -> str:
        """查询设备状态"""
        results = []

        if target == "全部":
            devices_to_show = self._mock_devices.items()
        else:
            # 支持按设备名或房间名查询
            devices_to_show = [
                (name, dev) for name, dev in self._mock_devices.items()
                if target in name or target == dev.get("room", "")
            ]

        if not devices_to_show:
            return f"❌ 未找到设备或房间：{target}"

        for name, dev in devices_to_show:
            if dev["type"] == "light":
                status = f"{'开' if dev['status'] == 'on' else '关'}"
                if dev["status"] == "on":
                    status += f"，亮度 {dev['brightness']}%"
            elif dev["type"] == "ac":
                status = f"{'开' if dev['status'] == 'on' else '关'}"
                if dev["status"] == "on":
                    status += f"，{dev['temperature']}°C {dev.get('mode', '')}"
            elif dev["type"] == "curtain":
                status = "已打开" if dev["status"] == "open" else "已关闭"
            else:
                status = dev["status"]
            results.append(f"• {name}：{status}")

        return "\n".join(results)

    def _list_devices(self) -> str:
        """列出所有设备"""
        lines = ["家中智能设备清单："]
        for name, dev in self._mock_devices.items():
            dev_type = {"light": "💡灯光", "ac": "❄️空调", "curtain": "🪟窗帘"}.get(dev["type"], dev["type"])
            status = "开" if dev["status"] in ("on", "open") else "关"
            lines.append(f"  {dev_type} {name}（{status}）")
        return "\n".join(lines)
