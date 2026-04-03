"""
Feishu (Lark) Skill Implementation / 飞书 Skill 实现
Supports sending messages via Lark Open API / 支持通过飞书开放平台发送消息
"""
from __future__ import annotations

import json
import logging
import os
import multiprocessing
import multiprocessing.queues
from typing import Any, Optional

import lark_oapi as lark

from src.skills.base import BaseSkill

logger = logging.getLogger(__name__)

class FeishuSkill(BaseSkill):
    """
    Feishu Skill for Lark integration. / 飞书 Skill 插件。
    Requires App ID and App Secret from config/agent.yaml. / 需要从配置文件加载 App ID 和 App Secret。
    """

    def __init__(self, config: dict = None):
        """
        Initialize Lark Client with config. / 使用配置初始化飞书客户端。
        Args:
            config: Skill configuration from agent.yaml / 来自 agent.yaml 的配置
        """
        self.config = config or {}
        
        # Priority: app_id_env (env var name) > app_id (direct value) / 优先级：解析环境变量名 > 直接配置值
        app_id_env = self.config.get("app_id_env")
        self.app_id = os.environ.get(app_id_env) if app_id_env else self.config.get("app_id")
        
        app_secret_env = self.config.get("app_secret_env")
        self.app_secret = os.environ.get(app_secret_env) if app_secret_env else self.config.get("app_secret")
        
        if not self.app_id or not self.app_secret:
            logger.warning("[Feishu] Missing app_id or app_secret in config/env / 凭证缺失")
            self.client = None
        else:
            # 1. Initialize API Client (used for sending messages in main process) / 
            # 初始化 API 客户端（用于主进程主动发消息）
            self.client = lark.Client.builder() \
                .app_id(self.app_id) \
                .app_secret(self.app_secret) \
                .build()
            
            logger.info("[Feishu] API Sender Client initialized / 飞书发送客户端已就绪")

    @property
    def name(self) -> str:
        return "feishu"

    @property
    def description(self) -> str:
        return "Feishu/Lark Messaging Plugin / 飞书消息插件"

    def get_tools(self) -> list[dict]:
        """Define Feishu tools in OpenAI format / 定义飞书工具（OpenAI 格式）"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "send_text_message",
                    "description": "Send a text message to a user or group on Feishu. / 向飞书用户或群聊发送文本消息。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "receive_id": {
                                "type": "string", 
                                "description": "The receiver's ID (Open ID, Union ID, Chat ID, or Email). / 接收者 ID (Open ID, Chat ID 等)"
                            },
                            "receive_id_type": {
                                "type": "string", 
                                "enum": ["open_id", "union_id", "chat_id", "email"],
                                "default": "open_id",
                                "description": "Type of receive_id. / 接收者 ID 类型"
                            },
                            "content": {
                                "type": "string", 
                                "description": "The text content of the message. / 消息文本内容"
                            },
                        },
                        "required": ["receive_id", "content"],
                    },
                },
            }
        ]

    async def handle_tool_call(self, tool_name: str, args: dict) -> str:
        """Entry point for Feishu tool execution / 飞书工具执行入口"""
        if not self.client:
            return "❌ Feishu client not configured. Please check agent.yaml / 飞书客户端未配置，请检查配置文件。"

        logger.info(f"[Feishu] Attempting tool: {tool_name} with args: {args}")

        if tool_name == "send_text_message":
            return await self._send_text_message(
                receive_id=args["receive_id"],
                content=args["content"],
                receive_id_type=args.get("receive_id_type", "open_id")
            )
        
        return f"❌ Unknown tool / 未知工具：{tool_name}"

    async def _send_text_message(self, receive_id: str, content: str, receive_id_type: str) -> str:
        """
        Internal implementation of sending text message. / 发送文本消息的内部实现。
        """
        # Create message content JSON / 构造消息内容 JSON
        msg_content = json.dumps({"text": content})
        
        # Build request / 构造请求
        request: lark.im.v1.CreateMessageRequest = lark.im.v1.CreateMessageRequest.builder() \
            .receive_id_type(receive_id_type) \
            .request_body(lark.im.v1.CreateMessageRequestBody.builder() \
                .receive_id(receive_id) \
                .msg_type("text") \
                .content(msg_content) \
                .build()) \
            .build()

        # Send request asynchronously / 异步发送请求
        response: lark.im.v1.CreateMessageResponse = await self.client.im.v1.message.acreate(request)

        if not response.success():
            logger.error(f"[Feishu] API Error: {response.code} {response.msg}. LogID: {response.get_log_id()}")
            return f"❌ Feishu API Error: {response.msg} (Code: {response.code})"
        
        msg_id_info = "N/A"
        try:
            msg_id_info = json.loads(response.data.content).get("message_id", "N/A") if hasattr(response.data, 'content') else "N/A"
            # Some versions use response.data.message_id
            if hasattr(response.data, 'message_id'):
                msg_id_info = response.data.message_id
        except:
            pass

    async def _handle_ai_reply(self, receive_id: str, text: str, agent: Any):
        """
        Isolated AI processing for Feishu messages. Triggered in main process via queue.
        针对飞书消息的独立 AI 处理逻辑。由主进程队列轮询器触发。
        """
        logger.info(f"🤖 [Feishu AI] Thinking for {receive_id}...")
        
        # Use background task mode to avoid polluting main history / 
        # 使用后台任务模式，避免污染主对话历史
        response = await agent.run_background_task(
            task_description=f"User via Feishu says: {text} / 飞书用户说：{text}",
            system_override=None # Uses default system prompt / 使用默认系统提示词
        )
        
        if response:
            await self._send_text_message(
                receive_id=receive_id, 
                content=response, 
                receive_id_type="open_id"
            )

    def start_listener(self) -> multiprocessing.queues.Queue | None:
        """
        Start WS listener in an isolated process and return the IPC queue. / 
        在独立的后台进程启动监听器，并返回 IPC 通信队列。
        """
        if not self.app_id or not self.app_secret:
            return None
            
        logger.info("[Feishu] Spawning isolated listener process... / 正在孵化独立监听子进程...")
        
        # Create cross-process queue / 创建跨进程队列
        msg_queue = multiprocessing.Queue()
        
        # Spawn the isolated process using absolutely resolvable module path /
        # 使用原生包路径结构引用执行函数，确保子进程能成功解析环境
        from skills.feishu.listener import run_process_listener
        
        process = multiprocessing.Process(
            target=run_process_listener,
            args=(self.app_id, self.app_secret, msg_queue),
            daemon=True
        )
        process.start()
        
        return msg_queue


