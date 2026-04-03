"""
Skill 插件系统 - 基类定义
每个 Skill 继承此基类，实现标准接口
"""
from __future__ import annotations
from abc import ABC, abstractmethod


class BaseSkill(ABC):
    """
    Skill 基类。
    所有 Skill 插件必须继承此类，并实现 get_tools 和 handle_tool_call 方法。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Skill 的唯一名称，如 'smarthome'"""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Skill 的功能描述，用于日志和状态展示"""
        ...

    @abstractmethod
    def get_tools(self) -> list[dict]:
        """
        返回该 Skill 提供的工具列表（OpenAI function calling 格式）。
        Agent 会将这些工具注入到 LLM 的工具列表中。
        """
        ...

    @abstractmethod
    async def handle_tool_call(self, tool_name: str, args: dict) -> str:
        """
        处理工具调用请求。

        Args:
            tool_name: 工具名称（不含 skill_{name}_ 前缀）
            args: 工具参数字典

        Returns:
            执行结果字符串
        """
        ...

    def is_my_tool(self, full_tool_name: str) -> bool:
        """判断某个工具名是否属于此 Skill"""
        prefix = f"skill_{self.name}_"
        return full_tool_name.startswith(prefix)

    def strip_prefix(self, full_tool_name: str) -> str:
        """去掉工具名前缀，得到原始工具名"""
        prefix = f"skill_{self.name}_"
        return full_tool_name[len(prefix):]
