"""
Skill Plugin System - Base Class Definition / 
Skill 插件系统 - 基类定义
Each Skill inherits from this base class and implements standard interfaces / 
每个 Skill 继承此基类，实现标准接口
"""
from __future__ import annotations
from abc import ABC, abstractmethod


class BaseSkill(ABC):
    """
    Skill Base Class. / Skill 基类。
    All Skill plugins must inherit from this and implement get_tools and handle_tool_call. / 
    所有 Skill 插件必须继承此类，并实现 get_tools 和 handle_tool_call 方法。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name of the Skill, e.g., 'smarthome' / Skill 的唯一名称"""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Functional description for logs and status display / Skill 的功能描述"""
        ...

    @abstractmethod
    def get_tools(self) -> list[dict]:
        """
        Returns list of tools provided by this Skill (OpenAI function format). / 
        返回该 Skill 提供的工具列表（OpenAI function calling 格式）。
        Agent injects these into LLM tool profile. / Agent 会将这些工具注入到 LLM 的工具列表中。
        """
        ...

    @abstractmethod
    async def handle_tool_call(self, tool_name: str, args: dict) -> str:
        """
        Handle tool call requests. / 处理工具调用请求。

        Args:
            tool_name: Raw name (without skill_{name}_ prefix) / 工具名称（不含前缀）
            args: Dictionary of tool arguments / 工具参数字典

        Returns:
            Execution result string / 执行结果字符串
        """
        ...

    def is_my_tool(self, full_tool_name: str) -> bool:
        """Check if a tool name belongs to this Skill / 判断某个工具名是否属于此 Skill"""
        prefix = f"skill_{self.name}_"
        return full_tool_name.startswith(prefix)

    def strip_prefix(self, full_tool_name: str) -> str:
        """Strip skill prefix to get raw tool name / 去掉工具名前缀，得到原始工具名"""
        prefix = f"skill_{self.name}_"
        return full_tool_name[len(prefix):]
