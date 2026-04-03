"""
Feishu (Lark) Skill Implementation / 飞书 Skill 实现
Supports sending messages via Lark Open API / 支持通过飞书开放平台发送消息
"""
from __future__ import annotations

import json
import logging
import os
import threading
import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
from typing import Any, Optional

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
            self.ws_client = None
        else:
            # 1. Initialize API Client / 初始化 API 客户端
            self.client = lark.Client.builder() \
                .app_id(self.app_id) \
                .app_secret(self.app_secret) \
                .build()
            
            # 2. Initialize Event Handler / 初始化事件分发器
            self.event_handler = lark.EventDispatcherHandler.builder("", "") \
                .register_p2_im_message_receive_v1(self._on_message_received) \
                .build()
            
            # 3. Initialize WebSocket Client (don't start yet) / 初始化长连接客户端（暂不启动）
            self.ws_client = lark.ws.Client(
                self.app_id, 
                self.app_secret, 
                event_handler=self.event_handler,
                log_level=lark.LogLevel.INFO
            )
            logger.info("[Feishu] Client and Handler initialized / 飞书客户端与监听器已就绪")

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

    def _on_message_received(self, data: P2ImMessageReceiveV1) -> None:
        """Callback for message events / 收到消息事件的回调"""
        msg = data.event.message
        if not msg or not msg.content:
            return
            
        try:
            content_dict = json.loads(msg.content)
            text = content_dict.get("text", "").strip()
        except json.JSONDecodeError:
            return

        sender_id = data.event.sender.sender_id.open_id
        
        logger.info(f"📩 [Feishu Event] From {sender_id}: {text}")
        
        # Trigger auto-reply if enabled / 如果开启了自动回复，则触发处理
        if self.config.get("auto_reply") and self.agent and self.loop:
            # Dispatch to async handler safely across threads / 安全地跨线程分发到异步处理器
            import asyncio
            asyncio.run_coroutine_threadsafe(
                self._handle_ai_reply(sender_id, text), 
                self.loop
            )

    async def _handle_ai_reply(self, receive_id: str, text: str):
        """
        Isolated AI processing for Feishu messages / 
        针对飞书消息的独立 AI 处理逻辑
        """
        logger.info(f"🤖 [Feishu] AI is thinking for {receive_id}...")
        
        # Use background task mode to avoid polluting main history / 
        # 使用后台任务模式，避免污染主对话历史
        response = await self.agent.run_background_task(
            task_description=f"User via Feishu says: {text} / 飞书用户说：{text}",
            system_override=None # Uses default system prompt / 使用默认系统提示词
        )
        
        if response:
            await self._send_text_message(
                receive_id=receive_id, 
                content=response, 
                receive_id_type="open_id"
            )

    def start_listener(self, agent: Any = None, loop: Any = None):
        """Start WS listener in a background thread / 在后台线程启动监听器"""
        if not self.ws_client:
            return
            
        self.agent = agent
        self.loop = loop
            
        def run_ws():
            """
            Run the WebSocket client in its own completely isolated asyncio event loop.
            This avoids 'event loop is already running' errors from the main thread.
            在完全独立的 asyncio 事件循环中运行 WebSocket，避免与主线程事件循环冲突。
            """
            import asyncio as _asyncio
            logger.info("[Feishu] Background WebSocket listener starting... / 后台长连接监听启动中...")
            
            try:
                # asyncio.run() always creates a brand-new isolated event loop /
                # asyncio.run() 总是创建全新事件循环，与主线程完全隔离
                _asyncio.run(self._async_ws_run())
            except Exception as e:
                logger.error(f"[Feishu] WebSocket listener failed: {e} / 监听器意外中断")

        thread = threading.Thread(target=run_ws, daemon=True)
        thread.start()
        return thread

    async def _async_ws_run(self):
        """
        Async entry point for ws.Client.start() to be used in an isolated event loop.
        在独立事件循环内作为协程运行 WebSocket 客户端。
        """
        self.ws_client.start()
