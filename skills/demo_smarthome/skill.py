"""
智能家居 Skill 示例实现
"""
from __future__ import annotations

import json
import logging
from typing import Any
from pathlib import Path
import sys

# 确保项目路径正确
ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.skills.base import BaseSkill

logger = logging.getLogger(__name__)


class DemoSmartHomeSkill(BaseSkill):
    """
    智能家居 Skill 示例。
    使用模拟数据，供测试 Agent 功能。
    """

    # 模拟设备数据库
    _mock_devices = {
        "客厅灯": {"type": "light", "status": "on", "brightness": 80, "room": "客厅"},
        "空调":   {"type": "ac", "status": "off", "temperature": 26},
        "窗帘":   {"type": "curtain", "status": "open"},
    }

    @property
    def name(self) -> str:
        return "demo_smarthome"

    @property
    def description(self) -> str:
        return "智能家居控制示例插件"

    def get_tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "control_device",
                    "description": "控制智能家居设备（模拟）",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "device": {"type": "string", "description": "设备名称"},
                            "action": {"type": "string", "enum": ["on", "off", "set_temp"]},
                            "value": {"type": "number", "description": "数值（如温度）"},
                        },
                        "required": ["device", "action"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_devices",
                    "description": "获取所有设备状态",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

    async def handle_tool_call(self, tool_name: str, args: dict) -> str:
        if tool_name == "control_device":
            device = args["device"]
            action = args["action"]
            if device not in self._mock_devices:
                return f"❌ 未找到设备：{device}"
            self._mock_devices[device]["status"] = action
            return f"✅ {device} 已执行 {action}"
        elif tool_name == "get_devices":
            return json.dumps(self._mock_devices, ensure_ascii=False, indent=2)
        return f"❌ 未知工具：{tool_name}"
