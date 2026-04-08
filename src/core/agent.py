"""
Agent Core Engine - Manages conversation loops, tool dispatching, and context maintenance / 
Agent 核心引擎 - 管理对话循环、工具调用分发、上下文维护
Integrates Model / Memory / MCP / Skills subsystems / 整合 Model / Memory / MCP / Skills 四个子系统
"""
from __future__ import annotations

import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.core.model import ModelClient
from src.memory.manager import MemoryManager
from src.mcp.client import MCPRegistry
from src.skills.loader import SkillLoader

logger = logging.getLogger(__name__)

# Agent System Prompt Base Template / Agent 系统提示词基础模板
BASE_SYSTEM_PROMPT = """你是一个极其聪明、动作果断的物理智能家居 AI 管家，名叫 "{agent_name}"。
你驻留在用户的家庭服务器中，通过各种工具（Memory / MCP / Skills）感知并控制物理世界。

### 行动准则 (Action Principles) - 极其重要
1. **探测优先 (Probing-First)**：如果用户的意图涉及查询（如“几个家”、“有什么设备”、“状态如何”），**严禁**反向询问用户以获取信息。你拥有工具，你应该**立即调用工具**自助查询，然后再给出结论。
2. **拒绝平庸**：不要做一个只会复读和确认的复读机。你的价值在于通过后台操作减少用户的认知负担。
3. **静默多步执行**：如果一个任务需要多步（如：查家 -> 选家 -> 查设备），请在一次回复前连续调用所有必要工具，直接汇报最终发现。
4. **歧义处理**：只有当工具返回依然存在无法确定的多项选择时，才礼貌地请用户选择。

### 思路示例 (Few-shot Learning)
- **场景 A（查询数量）**
  用户：我有几个家？
  你的思考：用户在询问家庭数量，我应该调用工具列出家庭。
  你的行动：[调用 mcp_..._list_homes]
  你的回复：您名下一共有 2 个家，分别是“我的家 79”和“办公室”。需要我进一步为您展示设备吗？

- **场景 B（模糊意图）**
  用户：帮我看看家里有没有异常。
  你的思考：用户需要体检。我需要先查家庭列表，然后对每个家进行巡检。
  你的行动：[连续调用 list_homes, query_dev_stat 等]
  你的回复：报告管家，经过巡检：您的客厅温控器当前离线，其余 15 台设备运行正常。建议您检查一下客厅网关的电源。

### 实时环境 (Real-time Context)
- **当前时间**：{current_time}
- **记忆与历史**：
{memory_context}

---
请开始你的服务。**少说话，多干活**，做一个让用户感到“省心”的管家。
"""


class Agent:
    """
    Main engine for the SmartHome Agent. / 智能家居 Agent 主引擎。

    Responsible for / 负责：
    - Managing multi-turn conversation context / 管理多轮对话上下文
    - Integrating all tools (Memory + MCP + Skills) / 整合所有工具（Memory + MCP + Skills）
    - Executing tool_use loops until task completion / 执行 tool_use 循环直到 Agent 完成任务
    - Providing run_background_task for heartbeats/timers / 提供 run_background_task 接口供心跳/定时器调用
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
        session_dir: str = "sessions",
    ):
        self.name = name
        self.model = model_client
        self.memory = memory
        self.mcp = mcp_registry
        self.skills = skill_loader
        self.max_context_turns = max_context_turns
        self.max_tool_iterations = max_tool_iterations
        self.session_dir = Path(session_dir)
        
        # Ensure session directory exists / 确保会话目录存在
        self.session_dir.mkdir(parents=True, exist_ok=True)

        # Managed sessions (history by ID) / 分会话管理的历史记录
        self._sessions: dict[str, list[dict]] = {}
        # Default history (for CLI/legacy) / 默认历史记录（用于 CLI/旧版）
        self._history: list[dict] = []

    def _build_system_prompt(self) -> str:
        """Build system prompt with memory context / 构建带有记忆上下文的系统提示词"""
        memory_ctx = self.memory.load_all()
        return BASE_SYSTEM_PROMPT.format(
            agent_name=self.name,
            current_time=datetime.now().strftime("%Y-%m-%d %H:%M (%A)"),
            memory_context=memory_ctx if memory_ctx else "",
        )

    def _get_all_tools(self) -> list[dict]:
        """
        Aggregate all available tools: Memory + MCP + Skills / 聚合所有可用工具：Memory 工具 + MCP 工具 + Skill 工具
        """
        tools = []
        tools.extend(self.memory.get_memory_tools())       # Internal memory tools / 记忆工具（内置）
        tools.extend(self.mcp.get_all_tools_openai_format())  # MCP tools / MCP 工具
        tools.extend(self.skills.get_all_tools_openai_format())  # Skill tools / Skill 工具
        return tools

    async def _handle_tool_call(self, tool_name: str, arguments: dict) -> str:
        """
        Dispatch tool calls to the corresponding subsystem / 分发工具调用到对应的子系统处理。

        Routing Rules / 路由规则：
        - memory_*    → MemoryManager
        - mcp_*       → MCPRegistry
        - skill_*     → SkillLoader
        """
        logger.debug(f"[Agent] Tool Call / 工具调用: {tool_name}({arguments})")

        if tool_name.startswith("memory_"):
            return self.memory.handle_tool_call(tool_name, arguments)

        elif self.mcp.is_mcp_tool(tool_name):
            return await self.mcp.call_tool(tool_name, arguments)

        elif self.skills.is_skill_tool(tool_name):
            return await self.skills.handle_tool_call(tool_name, arguments)

        else:
            return f"❌ Unknown tool type / 未知工具类型：{tool_name}"

    def _get_session_path(self, session_id: str) -> Path:
        """Get the file path for a session / 获取会话的文件保存路径"""
        # Sanitize filename (basic)
        safe_id = "".join([c for c in session_id if c.isalnum() or c in ("-", "_")])
        return self.session_dir / f"{safe_id}.json"

    def _save_session_to_disk(self, session_id: str, history: list[dict]):
        """Persist session history to disk / 将会话历史持久化到磁盘"""
        path = self._get_session_path(session_id)
        
        # Sanitize OpenAI objects before saving / 保存前净化对象
        def _sanitize(obj):
            if obj is None: return None
            if isinstance(obj, list): return [_sanitize(i) for i in obj]
            if isinstance(obj, dict): return {k: _sanitize(v) for k, v in obj.items()}
            if hasattr(obj, "model_dump"): return _sanitize(obj.model_dump())
            if hasattr(obj, "to_dict"): return _sanitize(obj.to_dict())
            return str(obj)

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(_sanitize(history), f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[Agent] Failed to save session {session_id}: {e}")

    def _load_session_from_disk(self, session_id: str) -> list[dict]:
        """Load session history from disk / 从磁盘加载会话历史"""
        path = self._get_session_path(session_id)
        if not path.exists():
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"[Agent] Failed to load session {session_id}: {e}")
            return []

    async def chat(
        self, 
        user_message: str, 
        session_id: Optional[str] = "default",
        system_override: Optional[str] = None
    ) -> str:
        """
        Process a user message and return the Agent's response. / 处理一条用户消息。
        Session isolation and DISK PERSISTENCE enabled. / 支持多会话隔离及磁盘持久化。
        """
        sid = session_id or "default"
        
        # 1. Load from disk if not in memory cache / 如果内存没有，尝试从磁盘加载
        if sid not in self._sessions:
            self._sessions[sid] = self._load_session_from_disk(sid)
        
        history = self._sessions[sid]

        # 2. Process chat / 执行对话
        history.append({"role": "user", "content": user_message})

        # Sliding window / 滑动窗口
        if len(history) > self.max_context_turns * 2:
            history[:] = history[-(self.max_context_turns * 2):]

        # Build full message list / 构建完整消息列表
        system_msg = system_override or self._build_system_prompt()
        messages = [
            {"role": "system", "content": system_msg},
            *history,
        ]

        tools = self._get_all_tools()
        final_response = ""

        # Tool use loop / Tool use 循环
        for iteration in range(self.max_tool_iterations):
            # --- PHASE 1: NORMALIZE HISTORY TO CLEAN DICTS ---
            raw_history_dicts = []
            for msg in history:
                m_to_append = {"role": msg["role"]}
                if msg.get("tool_calls"):
                    # Use None for content when tool_calls are present
                    m_to_append["content"] = msg.get("content") or None
                    m_to_append["tool_calls"] = msg["tool_calls"]
                else:
                    m_to_append["content"] = msg.get("content") or ""
                
                if msg.get("tool_call_id"):
                    m_to_append["tool_call_id"] = msg["tool_call_id"]
                
                raw_history_dicts.append(m_to_append)

            # --- PHASE 2: MERGE CONSECUTIVE ROLES & ENFORCE SEQUENCE ---
            api_messages = [{"role": "system", "content": system_msg}]
            
            for m in raw_history_dicts:
                prev = api_messages[-1]
                
                # Merge consecutive identical roles (system+system, user+user, assistant+assistant)
                # Note: Assistant with tool_calls is handled as a distinct state
                if m["role"] == prev["role"] and m["role"] in ("system", "user"):
                    prev["content"] = f"{prev.get('content','')}\n{m.get('content','')}".strip()
                elif m["role"] == "assistant" and prev["role"] == "assistant" and not m.get("tool_calls") and not prev.get("tool_calls"):
                    prev["content"] = f"{prev.get('content','')}\n{m.get('content','')}".strip()
                elif m["role"] == "tool" and prev["role"] != "assistant" and not any(msg.get("tool_calls") for msg in api_messages[::-1] if msg["role"] == "assistant"):
                    # Orphan tool message? Drop it to prevent 400 error
                    continue
                else:
                    # Specific check: Can't have Tool right after System/User (must follow Assistant)
                    if m["role"] == "tool" and prev["role"] not in ("assistant", "tool"):
                        # If tool follows user, it's invalid. Skip it.
                        continue
                    # Normal case: Append message
                    api_messages.append(m)

            # --- PHASE 3: FINAL SAFETY CHECK (Ensuring correct order for strict APIs) ---
            # Some APIs like Doubao forbid Tool -> User. Must be Assistant -> User.
            # We'll ensure it ends with user or assistant (not tool).
            
            # Debug roles sequence
            logger.debug(f"[Agent] API Sequence: {[m['role'] for m in api_messages]}")

            response_msg = await self.model.chat(
                messages=api_messages,
                tools=tools if tools else None,
            )

            # 1. Normalize response to clean dict / 将模型响应规范化为干净的字典
            msg_to_store = {
                "role": response_msg.role,
                "content": response_msg.content or None, # Use None for empty content
            }
            if hasattr(response_msg, "tool_calls") and response_msg.tool_calls:
                msg_to_store["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        }
                    } for tc in response_msg.tool_calls
                ]
            
            history.append(msg_to_store)

            # 2. Check for tool calls / 检查工具调用
            if "tool_calls" in msg_to_store and msg_to_store["tool_calls"]:
                for tool_call_data in msg_to_store["tool_calls"]:
                    t_name = tool_call_data["function"]["name"]
                    t_id = tool_call_data["id"]
                    try:
                        args = json.loads(tool_call_data["function"]["arguments"])
                    except (json.JSONDecodeError, KeyError):
                        args = {}

                    t_res = await self._handle_tool_call(t_name, args)
                    logger.info(f"[Agent] [{sid}] Tool {t_name} → {t_res[:100]}")

                    # Add tool result to history / 将工具执行结果存入历史
                    history.append({
                        "role": "tool",
                        "tool_call_id": t_id,
                        "content": t_res,
                    })
                # Continue iterations for model to process tool results
                continue
            else:
                # No tool calls, we have the final answer
                final_response = msg_to_store.get("content") or ""
                break
        else:
            final_response = "（Max tool iterations reached）"
        
        # Add assistant's final response to history / 将回复加入历史
        if final_response:
            history.append({"role": "assistant", "content": final_response})

        # 3. Synchronize to disk after each turn / 每一轮对话结束，同步保存到磁盘
        self._save_session_to_disk(sid, history)

        return final_response

    async def run_background_task(
        self,
        task_description: str,
        system_override: Optional[str] = None,
    ) -> str:
        """
        Execute a background task in an isolated context (for heartbeats/timers) / 在独立上下文中执行后台任务（心跳/定时任务专用）。
        Does not affect main conversation history / 不影响主对话历史。

        Args:
            task_description: Description of the task / 任务描述（Agent 将根据此执行）
            system_override: Optional custom System Prompt / 可选的自定义 System Prompt 覆盖

        Returns:
            Task execution result / 任务执行结果字符串
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

    def clear_history(self, session_id: Optional[str] = None):
        """Clear session history (memory + disk) / 清除对话历史（内存+磁盘）"""
        sid = session_id or "default"
        if sid in self._sessions:
            self._sessions[sid].clear()
        
        # Also delete local file / 同时删除本地文件
        path = self._get_session_path(sid)
        if path.exists():
            path.unlink()
        
        logger.info(f"[Agent] Cleared history for session: {sid}")

    @property
    def history_length(self) -> int:
        # Default to "default" session for CLI status / 针对 CLI 默认返回 default 会话的长度
        return len(self._sessions.get("default", []))
