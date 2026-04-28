import plistlib
import os
import sys
from typing import Dict, Any, Optional, List

class DevicePower:
    """智能家居设备能力集解析工具类"""
    def __init__(self, plist_path: str):
        self.plist_path = plist_path
        self.data = self._load_plist()
        
    def _load_plist(self) -> Dict[str, Any]:
        """解析 plist 文件"""
        if not os.path.exists(self.plist_path):
            print(f"Warning: Plist file not found at {self.plist_path}", file=sys.stderr)
            return {}
            
        try:
            with open(self.plist_path, 'rb') as f:
                return plistlib.load(f)
        except Exception as e:
            print(f"Error loading plist: {e}", file=sys.stderr)
            return {}

    def get_all_device_capabilities(self) -> Dict[str, Any]:
        """获取所有设备的能力字典"""
        return self.data.get('alldev', {})

    def get_device_info(self, device_type: str) -> Optional[Dict[str, Any]]:
        """获取指定设备型号的详细能力"""
        alldev = self.get_all_device_capabilities()
        return alldev.get(device_type)

    def get_control_nodes(self, device_type: str) -> List[Dict[str, Any]]:
        """获取设备的可控制节点信息"""
        dev_info = self.get_device_info(device_type)
        if not dev_info:
            return []
        return dev_info.get('control', [])

    def get_feedback_nodes(self, device_type: str) -> List[Dict[str, Any]]:
        """获取设备的状态查询/反馈节点信息"""
        dev_info = self.get_device_info(device_type)
        if not dev_info:
            return []
            
        feedback = dev_info.get('feedback', {})
        if isinstance(feedback, dict):
            return list(feedback.values())
        elif isinstance(feedback, list):
            return feedback
        return []

    def describe_device_capabilities(self, device_type: str) -> str:
        """为 LLM 生成设备能力的易读描述字符串"""
        dev_info = self.get_device_info(device_type)
        if not dev_info:
            return f"未知设备型号: {device_type}"
            
        name = dev_info.get('name', '未命名设备')
        controls = self.get_control_nodes(device_type)
        feedbacks = self.get_feedback_nodes(device_type)
        
        desc_lines = [f"设备类型: {device_type} ({name})"]
        
        if controls:
            desc_lines.append("\n可控节点:")
            for c in controls:
                node_name = c.get('name', '未知')
                node_id = c.get('node', '未知')
                value_info = ""
                if 'valueName' in c and 'value' in c:
                    value_info = f"，值选项: {c['valueName']} -> {c['value']}"
                elif 'value' in c:
                    value_info = f"，取值范围: {c['value']}"
                desc_lines.append(f"  - {node_name} (ID: {node_id}){value_info}")
                
        if feedbacks:
            desc_lines.append("\n状态查询节点:")
            for f in feedbacks:
                node_name = f.get('name', '未知')
                node_id = f.get('node', '未知')
                desc_lines.append(f"  - {node_name} (ID: {node_id})")
                
        return "\n".join(desc_lines)

# 全局单例
def _create_device_power():
    from config import config
    return DevicePower(config.PLIST_PATH)

device_power = _create_device_power()
