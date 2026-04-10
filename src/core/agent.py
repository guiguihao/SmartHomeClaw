"""
Agent 核心引擎 - 管理对话循环、工具调用分发、上下文维护。
整合了模型 (Model)、记忆 (Memory)、协议注册 (MCP) 和技能 (Skills) 四个子系统。
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

# Agent 系统提示词基础模板
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
    SmartHome Agent 主引擎。

    负责：
    - 管理多轮对话上下文
    - 整合所有工具（Memory + MCP + Skills）
    - 执行 tool_use 循环（思维链操作）直到任务完成
    - 提供运行后台任务（心跳/定时器）的接口
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
        """
        初始化 Agent 会话。
        :param name: Agent 的显示名称
        :param model_client: 模型客户端实例
        :param memory: 记忆管理器实例
        :param mcp_registry: MCP 协议注册表
        :param skill_loader: 技能加载器
        :param max_context_turns: 最大上下文轮数（超过则滑动）
        :param max_tool_iterations: 一次回复中允许的最大工具调用循环次数
        :param session_dir: 会话历史存储目录
        """
        self.name = name
        self.model = model_client
        self.memory = memory
        self.mcp = mcp_registry
        self.skills = skill_loader
        self.max_context_turns = max_context_turns
        self.max_tool_iterations = max_tool_iterations
        self.session_dir = Path(session_dir)
        
        # 确保会话目录存在
        self.session_dir.mkdir(parents=True, exist_ok=True)

        # 内存中的会话缓存 (ID -> 历史记录列表)
        self._sessions: dict[str, list[dict]] = {}
        # 默认历史记录队列
        self._history: list[dict] = []

    def _build_system_prompt(self) -> str:
        """构建带有动态记忆上下文的系统提示词"""
        memory_ctx = self.memory.load_all()
        return BASE_SYSTEM_PROMPT.format(
            agent_name=self.name,
            current_time=datetime.now().strftime("%Y-%m-%d %H:%M (%A)"),
            memory_context=memory_ctx if memory_ctx else "",
        )

    def _get_all_tools(self) -> list[dict]:
        """
        聚合所有子系统的可用工具：Memory + MCP + Skills
        """
        tools = []
        tools.extend(self.memory.get_memory_tools())       # 内置记忆工具
        tools.extend(self.mcp.get_all_tools_openai_format())  # MCP 协议工具
        tools.extend(self.skills.get_all_tools_openai_format())  # 业务技能工具
        return tools

    async def _handle_tool_call(self, tool_name: str, arguments: dict) -> str:
        """
        将工具调用分发到对应的子系统处理。

        路由规则：
        - memory_*    → 进入 MemoryManager 记忆管理
        - mcp_*       → 进入 MCPRegistry 调用外部服务
        - skill_*     → 进入 SkillLoader 调用封装好的技能模块
        """
        logger.debug(f"[Agent] 工具调用请求: {tool_name}({arguments})")

        if tool_name.startswith("memory_"):
            return self.memory.handle_tool_call(tool_name, arguments)

        elif self.mcp.is_mcp_tool(tool_name):
            return await self.mcp.call_tool(tool_name, arguments)

        elif self.skills.is_skill_tool(tool_name):
            return await self.skills.handle_tool_call(tool_name, arguments)

        else:
            return f"❌ 未知工具类型：{tool_name}"

    def _get_session_path(self, session_id: str) -> Path:
        """计算会话历史的文件存储路径"""
        # 对文件名进行简单的安全过滤
        safe_id = "".join([c for c in session_id if c.isalnum() or c in ("-", "_")])
        return self.session_dir / f"{safe_id}.json"

    def _save_session_to_disk(self, session_id: str, history: list[dict]):
        """将会话历史持久化存储到磁盘"""
        path = self._get_session_path(session_id)
        
        # 保存前净化对象（处理无法序列化的复杂类型）
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
            logger.error(f"[Agent] 无法保存会话 {session_id} 历史记录: {e}")

    def _load_session_from_disk(self, session_id: str) -> list[dict]:
        """从磁盘读取历史会话内容"""
        path = self._get_session_path(session_id)
        if not path.exists():
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"[Agent] 无法读取会话 {session_id} 历史记录: {e}")
            return []

    async def chat(
        self, 
        user_message: str, 
        session_id: Optional[str] = "default",
        system_override: Optional[str] = None
    ) -> str:
        """
        处理用户消息并返回 Agent 回复。
        支持多会话隔离及自动磁盘持久化。
        """
        sid = session_id or "default"
        
        # 1. 缓存处理：如果内存中没有，则从磁盘加载
        if sid not in self._sessions:
            self._sessions[sid] = self._load_session_from_disk(sid)
        
        history = self._sessions[sid]

        # 2. 将用户消息加入历史
        history.append({"role": "user", "content": user_message})

        # 3. 滑动窗口管理：防止上下文过长
        if len(history) > self.max_context_turns * 2:
            history[:] = history[-(self.max_context_turns * 2):]

        # 4. 构建模型所需的完整消息列表
        system_msg = system_override or self._build_system_prompt()
        
        tools = self._get_all_tools()
        final_response = ""

        # --- 核心机制：工具调用思维链循环 (Tool Use Logic) ---
        for iteration in range(self.max_tool_iterations):
            # 阶段 A: 历史消息规范化 (处理嵌套结构)
            raw_history_dicts = []
            for msg in history:
                m_to_append = {"role": msg["role"]}
                if msg.get("tool_calls"):
                    m_to_append["content"] = msg.get("content") or None
                    m_to_append["tool_calls"] = msg["tool_calls"]
                else:
                    m_to_append["content"] = msg.get("content") or ""
                
                if msg.get("tool_call_id"):
                    m_to_append["tool_call_id"] = msg["tool_call_id"]
                
                raw_history_dicts.append(m_to_append)

            # 阶段 B: 合并连续角色 & 维护消息序列完整性 (防止 API 报错)
            api_messages = [{"role": "system", "content": system_msg}]
            
            for m in raw_history_dicts:
                prev = api_messages[-1]
                
                # 合并连续的相同角色（例如：多个连续的 user 消息）
                if m["role"] == prev["role"] and m["role"] in ("system", "user"):
                    prev["content"] = f"{prev.get('content','')}\n{m.get('content','')}".strip()
                elif m["role"] == "assistant" and prev["role"] == "assistant" and not m.get("tool_calls") and not prev.get("tool_calls"):
                    prev["content"] = f"{prev.get('content','')}\n{m.get('content','')}".strip()
                # 过滤掉不合法的顺序（例如：Tool 消息必须紧随 Assistant 的 Tool Call）
                elif m["role"] == "tool" and prev["role"] != "assistant" and not any(msg.get("tool_calls") for msg in api_messages[::-1] if msg["role"] == "assistant"):
                    continue
                else:
                    if m["role"] == "tool" and prev["role"] not in ("assistant", "tool"):
                        continue
                    api_messages.append(m)

            # 调试：输出当前对话序列
            logger.debug(f"[Agent] 发送至 API 的序列: {[m['role'] for m in api_messages]}")

            # 调用模型
            response_msg = await self.model.chat(
                messages=api_messages,
                tools=tools if tools else None,
            )

            # I. 将模型响应规范化为记录字典
            msg_to_store = {
                "role": response_msg.role,
                "content": response_msg.content or None,
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

            # II. 判读模型是否发起工具调用请求
            if "tool_calls" in msg_to_store and msg_to_store["tool_calls"]:
                for tool_call_data in msg_to_store["tool_calls"]:
                    t_name = tool_call_data["function"]["name"]
                    t_id = tool_call_data["id"]
                    try:
                        args = json.loads(tool_call_data["function"]["arguments"])
                    except (json.JSONDecodeError, KeyError):
                        args = {}

                    # 执行本地工具
                    t_res = await self._handle_tool_call(t_name, args)
                    logger.info(f"[Agent] [{sid}] 🛠️ 工具执行: {t_name} → {t_res[:100]}")

                    # 将执行结果回填至对话历史
                    history.append({
                        "role": "tool",
                        "tool_call_id": t_id,
                        "content": t_res,
                    })
                # 继续下一次循环，让模型根据工具结果产生回复
                continue
            else:
                # 模型没有发起更多工具调用，获取最终回复内容并退出循环
                final_response = msg_to_store.get("content") or ""
                break
        else:
            final_response = "（达到最大工具调用循环限制）"
        
        # 5. 每一轮对话结束，将最新历史同步保存到磁盘
        self._save_session_to_disk(sid, history)

        return final_response

    async def run_background_task(
        self,
        task_description: str,
        system_override: Optional[str] = None,
    ) -> str:
        """
        在独立上下文中执行后台任务（心跳、定时触发等专用）。
        不影响主对话历史（Stateless 执行）。

        :param task_description: 任务指令描述
        :param system_override: 可选的系统提示词覆盖
        :return: 任务执行后的文本结论
        """
        system = system_override or self._build_system_prompt()
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": task_description},
        ]

        tools = self._get_all_tools()
        final_response = ""

        # 后台任务同样支持工具调用循环
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
        """清除会话历史记录（包括内存缓存和物理磁盘文件）"""
        sid = session_id or "default"
        if sid in self._sessions:
            self._sessions[sid].clear()
        
        # 同时删除本地 json 文件
        path = self._get_session_path(sid)
        if path.exists():
            path.unlink()
        
        logger.info(f"[Agent] 已清除会话历史: {sid}")

    @property
    def history_length(self) -> int:
        """获取默认会话（CLI）的历史消息条数"""
        return len(self._sessions.get("default", []))

