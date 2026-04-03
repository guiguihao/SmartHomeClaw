"""
Agent 核心引擎 - 管理对话循环、工具调用分发、上下文维护
整合 Model / Memory / MCP / Skills 四个子系统
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

from src.core.model import ModelClient
from src.memory.manager import MemoryManager
from src.mcp.client import MCPRegistry
from src.skills.loader import SkillLoader

logger = logging.getLogger(__name__)

# Agent 系统提示词基础模板
BASE_SYSTEM_PROMPT = """你是一个智能家居 AI Agent，名叫"{agent_name}"。

你的能力：
- 通过工具控制和查询智能家居设备
- 记录用户的偏好和习惯，提供个性化体验
- 执行定时场景和自动化规则
- 主动学习用户的使用习惯

工作原则：
1. 操作设备前，优先确认用户意图（涉及安全的操作必须确认）
2. 发现用户规律性行为后，主动调用记忆工具记录
3. 回复简洁清晰，必要时主动询问细节
4. 如果工具调用失败，给出明确说明和建议
5. 当前时间：{current_time}

{memory_context}
"""


class Agent:
    """
    智能家居 Agent 主引擎。

    负责：
    - 管理多轮对话上下文
    - 整合所有工具（Memory + MCP + Skills）
    - 执行 tool_use 循环直到 Agent 完成任务
    - 提供 run_background_task 接口供心跳/定时器调用
    """

    def __init__(
        self,
        name: str,
        model_client: ModelClient,
        memory: MemoryManager,
        mcp_registry: MCPRegistry,
        skill_loader: SkillLoader,
        max_context_turns: int = 20,
        max_tool_iterations: int = 10,
    ):
        self.name = name
        self.model = model_client
        self.memory = memory
        self.mcp = mcp_registry
        self.skills = skill_loader
        self.max_context_turns = max_context_turns
        self.max_tool_iterations = max_tool_iterations

        # 对话历史（滑动窗口）
        self._history: list[dict] = []

    def _build_system_prompt(self) -> str:
        """构建带有记忆上下文的系统提示词"""
        memory_ctx = self.memory.load_all()
        return BASE_SYSTEM_PROMPT.format(
            agent_name=self.name,
            current_time=datetime.now().strftime("%Y-%m-%d %H:%M (%A)"),
            memory_context=memory_ctx if memory_ctx else "",
        )

    def _get_all_tools(self) -> list[dict]:
        """
        聚合所有可用工具：Memory 工具 + MCP 工具 + Skill 工具
        """
        tools = []
        tools.extend(self.memory.get_memory_tools())       # 记忆工具（内置）
        tools.extend(self.mcp.get_all_tools_openai_format())  # MCP 工具
        tools.extend(self.skills.get_all_tools_openai_format())  # Skill 工具
        return tools

    async def _handle_tool_call(self, tool_name: str, arguments: dict) -> str:
        """
        分发工具调用到对应的子系统处理。

        路由规则：
        - memory_*    → MemoryManager
        - mcp_*       → MCPRegistry
        - skill_*     → SkillLoader
        """
        logger.debug(f"[Agent] 工具调用: {tool_name}({arguments})")

        if tool_name.startswith("memory_"):
            return self.memory.handle_tool_call(tool_name, arguments)

        elif self.mcp.is_mcp_tool(tool_name):
            return await self.mcp.call_tool(tool_name, arguments)

        elif self.skills.is_skill_tool(tool_name):
            return await self.skills.handle_tool_call(tool_name, arguments)

        else:
            return f"❌ 未知工具类型：{tool_name}"

    async def chat(self, user_message: str) -> str:
        """
        处理一条用户消息，返回 Agent 的回复。
        内部会执行完整的 tool_use 循环直到得到最终文本回复。

        Args:
            user_message: 用户输入的消息

        Returns:
            Agent 的最终文字回复
        """
        # 添加用户消息到历史
        self._history.append({"role": "user", "content": user_message})

        # 滑动窗口：保留最近 N 轮
        if len(self._history) > self.max_context_turns * 2:
            self._history = self._history[-(self.max_context_turns * 2):]

        # 构建完整消息列表（system + history）
        messages = [
            {"role": "system", "content": self._build_system_prompt()},
            *self._history,
        ]

        tools = self._get_all_tools()
        final_response = ""

        # Tool use 循环
        for iteration in range(self.max_tool_iterations):
            response_msg = await self.model.chat(
                messages=messages,
                tools=tools if tools else None,
            )

            # 检查是否有工具调用
            if hasattr(response_msg, "tool_calls") and response_msg.tool_calls:
                # 将 assistant 消息（含 tool_calls）加入历史
                messages.append(response_msg)

                # 依次处理所有工具调用
                for tool_call in response_msg.tool_calls:
                    tool_name = tool_call.function.name
                    try:
                        arguments = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        arguments = {}

                    tool_result = await self._handle_tool_call(tool_name, arguments)
                    logger.info(f"[Agent] 工具 {tool_name} → {tool_result[:100]}")

                    # 将工具结果加入消息历史
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_result,
                    })

                # 继续循环，让 Agent 根据工具结果生成下一步
                continue

            else:
                # 没有工具调用，得到最终文字回复
                final_response = response_msg.content or ""
                break
        else:
            final_response = "（已达到最大工具调用次数，任务可能未完成）"

        # 将 assistant 的最终回复加入历史
        if final_response:
            self._history.append({"role": "assistant", "content": final_response})

        return final_response

    async def run_background_task(
        self,
        task_description: str,
        system_override: Optional[str] = None,
    ) -> str:
        """
        在独立上下文中执行后台任务（心跳/定时任务专用）。
        不影响主对话历史。

        Args:
            task_description: 任务描述（Agent 将根据此执行）
            system_override: 可选的自定义 System Prompt 覆盖

        Returns:
            任务执行结果字符串
        """
        system = system_override or self._build_system_prompt()
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": task_description},
        ]

        tools = self._get_all_tools()
        final_response = ""

        for _ in range(self.max_tool_iterations):
            response_msg = await self.model.chat(
                messages=messages,
                tools=tools if tools else None,
            )

            if hasattr(response_msg, "tool_calls") and response_msg.tool_calls:
                messages.append(response_msg)
                for tool_call in response_msg.tool_calls:
                    tool_name = tool_call.function.name
                    try:
                        arguments = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        arguments = {}
                    tool_result = await self._handle_tool_call(tool_name, arguments)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_result,
                    })
                continue
            else:
                final_response = response_msg.content or ""
                break

        return final_response

    def clear_history(self):
        """清除对话历史"""
        self._history.clear()

    @property
    def history_length(self) -> int:
        return len(self._history)
