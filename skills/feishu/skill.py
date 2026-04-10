"""
Feishu (Lark) Skill Implementation / 飞书 Skill 实现
Supports sending messages via Lark Open API / 支持通过飞书开放平台发送消息
"""
from __future__ import annotations

import json
import logging
import os
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
        
        # 1. Resolve default (top-level) app credentials / 解析顶层默认凭证
        app_id_env = self.config.get("app_id_env")
        self.app_id = os.environ.get(app_id_env) if app_id_env else self.config.get("app_id")
        
        app_secret_env = self.config.get("app_secret_env")
        self.app_secret = os.environ.get(app_secret_env) if app_secret_env else self.config.get("app_secret")
        
        self.client = None
        if self.app_id and self.app_secret:
            # Initialize default API Client (used for sending messages in main process) /
            # 初始化 API 客户端（用于主进程主动发消息）
            self.client = lark.Client.builder() \
                .app_id(self.app_id) \
                .app_secret(self.app_secret) \
                .build()
            logger.info("[Feishu] API Sender Client (default) initialized / 飞书发送客户端已就绪")
        
        # 2. Initialize containers for multiple apps / 初始化多应用容器
        self._additional_clients: dict[str, Any] = {}
        self.app_configs: dict[str, dict] = {}
        
        # Load extra Feishu app configurations if provided under 'apps' / 加载 apps 列表下的配置
        extra_apps = self.config.get("apps", {})
        for extra_name, extra_cfg in extra_apps.items():
            # Resolve credentials for each extra app
            extra_app_id = os.getenv(extra_cfg.get("app_id_env")) if extra_cfg.get("app_id_env") else extra_cfg.get("app_id")
            extra_app_secret = os.getenv(extra_cfg.get("app_secret_env")) if extra_cfg.get("app_secret_env") else extra_cfg.get("app_secret")
            
            if not extra_app_id or not extra_app_secret:
                logger.warning(f"[Feishu:{extra_name}] Missing credentials, skipping.")
                continue
                
            client = lark.Client.builder() \
                .app_id(extra_app_id) \
                .app_secret(extra_app_secret) \
                .build()
            self._additional_clients[extra_name] = client
            self.app_configs[extra_name] = {"app_id": extra_app_id, "app_secret": extra_app_secret}
            logger.info(f"[Feishu:{extra_name}] API client initialized.")

    @property
    def name(self) -> str:
        return "feishu"

    @property
    def description(self) -> str:
        return "Feishu/Lark Messaging Plugin / 飞书消息插件"

    def get_tools(self) -> list[dict]:
        """Define Feishu tools in OpenAI format / 定义飞书工具（OpenAI 格式）"""
        base_tool = {
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
        
        # Add app_name if multiple apps are configured to allow targeting specific bots
        if self._additional_clients:
            base_tool["function"]["parameters"]["properties"]["app_name"] = {
                "type": "string",
                "description": "Optional: Which Feishu bot to use (app_name defined in config). / 可选：使用哪个飞书机器人",
                "enum": list(self._additional_clients.keys()) + (["default"] if self.client else [])
            }
            
        return [base_tool]

    def _get_client(self, app_name: str | None = None):
        """Select the appropriate Lark client: specified, default, or first available from apps."""
        if app_name:
            return self._additional_clients.get(app_name) or self.client
        
        # If no name provided, prefer the top-level 'default' client
        if self.client:
            return self.client
            
        # Fallback to the first available client in _additional_clients
        if self._additional_clients:
            return next(iter(self._additional_clients.values()))
            
        return None

    async def handle_tool_call(self, tool_name: str, args: dict) -> str:
        """Entry point for Feishu tool execution / 飞书工具执行入口"""
        # Determine which client to use (default or specified app)
        client = self._get_client(args.get("app_name"))
        if not client:
            return "❌ Feishu client not configured for the requested app. Please check agent.yaml."

        logger.info(f"[Feishu] Attempting tool: {tool_name} with args: {args}")

        if tool_name == "send_text_message":
            return await self._send_text_message(
                receive_id=args["receive_id"],
                content=args["content"],
                receive_id_type=args.get("receive_id_type", "open_id"),
                client=client,
            )
        
        return f"❌ Unknown tool / 未知工具：{tool_name}"

    async def _send_text_message(self, receive_id: str, content: str, receive_id_type: str, client: Optional[lark.Client] = None) -> str:
        """
        Internal implementation of sending text message. / 发送文本消息的内部实现。
        """
        # Use provided client or default
        client = client or self.client
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
        response: lark.im.v1.CreateMessageResponse = await client.im.v1.message.acreate(request)

        if not response.success():
            logger.error(f"[Feishu] API Error: {response.code} {response.msg}. LogID: {response.get_log_id()}")
            return f"❌ Feishu API Error: {response.msg} (Code: {response.code})"
        
        return "✅ Message sent successfully"


