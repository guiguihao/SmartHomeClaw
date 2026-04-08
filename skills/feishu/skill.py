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
        
        msg_id_info = "N/A"
        try:
            msg_id_info = json.loads(response.data.content).get("message_id", "N/A") if hasattr(response.data, 'content') else "N/A"
            # Some versions use response.data.message_id
            if hasattr(response.data, 'message_id'):
                msg_id_info = response.data.message_id
        except:
            pass

    async def _add_reaction(self, message_id: str, emoji_type: str, client: Optional[lark.Client] = None) -> None:
        """
        Add an emoji reaction to a specific message / 给某个特定消息打表情表态
        """
        client = client or self.client
        if not client or not message_id:
            return
            
        try:
            req = lark.im.v1.CreateMessageReactionRequest.builder() \
                .message_id(message_id) \
                .request_body(lark.im.v1.CreateMessageReactionRequestBody.builder()
                    .reaction_type(lark.im.v1.Emoji.builder().emoji_type(emoji_type).build())
                    .build()) \
                .build()
            
            resp = await client.im.v1.message_reaction.acreate(req)
            if not resp.success():
                logger.error(f"[Feishu] Failed to add reaction '{emoji_type}': {resp.msg}. (Please ensure 'im:message.reaction:read' & 'im:message.reaction:write' permissions are enabled in Feishu Developer Console / 请确保飞书开放平台开启了应用表态权限)")
        except Exception as e:
            logger.error(f"[Feishu] Add reaction error: {e}")

    async def _handle_ai_reply(self, receive_id: str, text: str, agent: Any, message_id: Optional[str] = None, app_name: Optional[str] = None):
        """
        Isolated AI processing for Feishu messages. Triggered in main process via queue.
        针对飞书消息的独立 AI 处理逻辑。由主进程队列轮询器触发。
        """
        logger.info(f"🤖 [Feishu AI] Thinking for {receive_id}...")
        # Select appropriate client based on app_name
        client = self._get_client(app_name)
        
        # 像 OpenClaw 一样显示"正在思考/敲打键盘"的表情状态
        if message_id:
            await self._add_reaction(message_id, "THINKING", client=client)
            
        # 获取核心系统的基础提示词（包含记忆、角色、思维模式等）
        base_system = agent._build_system_prompt()
        
        # 叠加飞书渠道特有的交互约束
        feishu_constraints = """
        ### 飞书交互规范 (Feishu Channel Rules)
        - **简洁性**：飞书是即时通讯工具，回复请尽量精炼，避免大段冗余信息。
        - **表情反馈**：你目前的思考和完成状态已通过消息表态（Reaction）反馈给用户，回复文本中无需重复说明“正在思考”等。
        - **排版**：使用清晰的换行或列表展示设备状态。
        """
        full_system = f"{base_system}\n{feishu_constraints}"
        
        # Use a scoped session_id that includes the app_name to ensure 
        # separate conversation histories for different bots.
        # 使用包含 app_name 的 session_id，确保不同机器人的对话历史完全隔离。
        scoped_session_id = f"{app_name}:{receive_id}" if app_name else receive_id

        # 使用 agent.chat 接口，并传入 session_id 以实现多轮对话上下文追踪
        response = await agent.chat(
            user_message=text,
            session_id=scoped_session_id,
            system_override=full_system,
        )
        
        if response:
            await self._send_text_message(
                receive_id=receive_id, 
                content=response, 
                receive_id_type="open_id",
                client=client,
            )
            # 在发送完毕后再打一个 DONE 的表态
            if message_id:
                await self._add_reaction(message_id, "DONE", client=client)

    def start_listener(self) -> dict[str, multiprocessing.queues.Queue] | None:
        """
        Start WS listeners (isolated processes) for each configured Feishu app that has listener enabled.
        Returns a mapping of app_name -> queue.
        """
        # Determine which apps should start listeners
        apps_to_start: dict[str, dict] = {}
        # Default app (if configured)
        if getattr(self, "app_id", None) and getattr(self, "app_secret", None):
            apps_to_start["default"] = {"app_id": self.app_id, "app_secret": self.app_secret}
        # Additional apps
        for name, cfg in self._additional_clients.items():
            cred = self.app_configs.get(name, {})
            if cred.get("app_id") and cred.get("app_secret"):
                apps_to_start[name] = {"app_id": cred["app_id"], "app_secret": cred["app_secret"]}
        if not apps_to_start:
            return None
        
        from skills.feishu.listener import run_process_listener
        
        queues: dict[str, multiprocessing.queues.Queue] = {}
        for app_name, creds in apps_to_start.items():
            msg_queue = multiprocessing.Queue()
            process = multiprocessing.Process(
                target=run_process_listener,
                args=(app_name, creds["app_id"], creds["app_secret"], msg_queue),
                daemon=True,
            )
            process.start()
            queues[app_name] = msg_queue
            logger.info(f"[Feishu:{app_name}] Listener process started.")
        return queues


