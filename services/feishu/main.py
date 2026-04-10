"""
Feishu Gateway
Listens to WebSocket events from Lark, forwards them to the Agent API, and sends back the replies.
"""
import asyncio
import json
import logging
import os
import ssl
import sys
import yaml
from pathlib import Path

# Add root to sys.path
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv() # 加载 .env 中的 API 凭证

import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
import requests
from logging.handlers import TimedRotatingFileHandler

# Configure logging to both console and file
log_dir = ROOT / "logs"
log_dir.mkdir(exist_ok=True)
log_file = log_dir / "feishu_gateway.log"

log_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# File handler
file_handler = TimedRotatingFileHandler(log_file, when="midnight", interval=1, backupCount=7, encoding="utf-8")
file_handler.setFormatter(log_formatter)

# Console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_formatter)

logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])
logger = logging.getLogger("FeishuGateway")

AGENT_API_URL = "http://127.0.0.1:8000/v1/chat"

class FeishuAppClient:
    def __init__(self, name: str, app_id: str, app_secret: str):
        self.name = name
        self.app_id = app_id
        self.app_secret = app_secret
        self.client = lark.Client.builder().app_id(app_id).app_secret(app_secret).build()

def add_reaction(client: lark.Client, message_id: str, emoji_type: str):
    """Add an emoji reaction to a specific message"""
    try:
        req = lark.im.v1.CreateMessageReactionRequest.builder() \
            .message_id(message_id) \
            .request_body(lark.im.v1.CreateMessageReactionRequestBody.builder()
                .reaction_type(lark.im.v1.Emoji.builder().emoji_type(emoji_type).build())
                .build()) \
            .build()
        
        # Using sync call in the background or thread
        client.im.v1.message_reaction.create(req)
    except Exception as e:
        logger.error(f"Failed to add reaction: {e}")

def send_text_reply(client: lark.Client, receive_id: str, content: str, app_name: str = "default"):
    """Send text reply back to the user"""
    msg_content = json.dumps({"text": content})
    
    req: lark.im.v1.CreateMessageRequest = lark.im.v1.CreateMessageRequest.builder() \
        .receive_id_type("open_id") \
        .request_body(lark.im.v1.CreateMessageRequestBody.builder() \
            .receive_id(receive_id) \
            .msg_type("text") \
            .content(msg_content) \
            .build()) \
        .build()

    resp = client.im.v1.message.create(req)
    if not resp.success():
        logger.error(f"[{app_name}] Failed to send reply: {resp.msg} (Code: {resp.code})")
    else:
        logger.info(f"📤 [{app_name}] Replied to {receive_id}: {content}")

def handle_message(app_client: FeishuAppClient, sender_id: str, msg_id: str, text: str):
    """Call Agent API and reply"""
    # 1. Add Thinking Reaction
    add_reaction(app_client.client, msg_id, "THINKING")
    
    # 2. Call Agent API
    scoped_session_id = f"{app_client.name}:{sender_id}" if app_client.name != "default" else sender_id
    
    feishu_constraints = """
### 飞书交互规范 (Feishu Channel Rules)
- **简洁性**：飞书是即时通讯工具，回复请尽量精炼，避免大段冗余信息。
- **表情反馈**：你目前的思考和完成状态已通过消息表态 (Reaction) 反馈给用户，回复文本中无需重复说明“正在思考”等。
- **排版**：使用清晰的换行或列表展示设备状态。
"""
    
    payload = {
        "session_id": scoped_session_id,
        "message": text,
        "app_name": app_client.name,
        "system_override": feishu_constraints
    }
    
    try:
        logger.info(f"🤖 [{app_client.name}] Forwarding to Agent API: {text}")
        resp = requests.post(AGENT_API_URL, json=payload, timeout=120)
        resp.raise_for_status()
        reply_text = resp.json().get("response")
        
        if reply_text:
            send_text_reply(app_client.client, sender_id, reply_text, app_name=app_client.name)
            add_reaction(app_client.client, msg_id, "DONE")
            
    except Exception as e:
        logger.error(f"[{app_client.name}] Error communicating with Agent API: {e}")
        add_reaction(app_client.client, msg_id, "CROSS_MARK")

def create_ws_client(app_client: FeishuAppClient):
    """Create a Lark WebSocket client for an app"""
    def _on_message_received(data: P2ImMessageReceiveV1) -> None:
        msg = data.event.message
        if not msg or not msg.content:
            return
            
        try:
            content_dict = json.loads(msg.content)
            text = content_dict.get("text", "").strip()
        except json.JSONDecodeError:
            return

        sender_id = data.event.sender.sender_id.open_id
        msg_id = msg.message_id
        logger.info(f"📩 [{app_client.name}] Received from {sender_id}: {text}")
        
        # Run handling in a background thread to not block WS ping-pongs
        import threading
        threading.Thread(target=handle_message, args=(app_client, sender_id, msg_id, text)).start()
        
    event_handler = lark.EventDispatcherHandler.builder("", "") \
        .register_p2_im_message_receive_v1(_on_message_received) \
        .build()
        
    ws_client = lark.ws.Client(
        app_client.app_id, 
        app_client.app_secret, 
        event_handler=event_handler,
        log_level=lark.LogLevel.INFO
    )
    return ws_client

def _start_ws_process(ac):
    """Worker function for multiprocessing."""
    import ssl
    import os
    
    # Fix SSL Contexts inside the child process
    for key in list(os.environ.keys()):
        if key.lower() in ("http_proxy", "https_proxy", "all_proxy", "no_proxy", "ftp_proxy"):
            del os.environ[key]
            
    try:
        ssl._create_default_https_context = ssl._create_unverified_context
    except AttributeError:
        pass
        
    try:
        import websockets
        _original_connect = websockets.connect
        def _unverified_connect(*args, **kwargs):
            if "ssl" not in kwargs:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                kwargs["ssl"] = ctx
            return _original_connect(*args, **kwargs)
        websockets.connect = _unverified_connect
    except ImportError:
        pass

    # Each process gets its own event loop
    ws = create_ws_client(ac)
    ws.start()

def run_feishu_gateway():
    # Load config
    config_path = ROOT / "config" / "agent.yaml"
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
        
    feishu_cfg = cfg.get("skills", {}).get("feishu", {})
    if not feishu_cfg.get("enable_listener", False):
        logger.info("Feishu listener disabled globally.")
        return
        
    app_clients = []
    
    # Check default bot
    app_id_env = feishu_cfg.get("app_id_env")
    default_app_id = os.environ.get(app_id_env) if app_id_env else feishu_cfg.get("app_id")
    app_secret_env = feishu_cfg.get("app_secret_env")
    default_app_secret = os.environ.get(app_secret_env) if app_secret_env else feishu_cfg.get("app_secret")
    
    if default_app_id and default_app_secret:
        app_clients.append(FeishuAppClient("default", default_app_id, default_app_secret))
        
    # Check extra bots
    apps = feishu_cfg.get("apps", {})
    for name, a_cfg in apps.items():
        if not a_cfg.get("enable_listener", False):
            continue
            
        a_id_env = a_cfg.get("app_id_env")
        a_id = os.environ.get(a_id_env) if a_id_env else a_cfg.get("app_id")
        a_secret_env = a_cfg.get("app_secret_env")
        a_secret = os.environ.get(a_secret_env) if a_secret_env else a_cfg.get("app_secret")
        
        if a_id and a_secret:
            app_clients.append(FeishuAppClient(name, a_id, a_secret))

    if not app_clients:
        logger.error("No valid Feishu credentials found.")
        return
        
    logger.info(f"Starting Feishu Gateway for {len(app_clients)} apps...")
    
    import multiprocessing
    processes = []
    for app_client in app_clients:
        p = multiprocessing.Process(target=_start_ws_process, args=(app_client,), daemon=True)
        p.start()
        processes.append(p)
        
    try:
        for p in processes:
            p.join()
    except KeyboardInterrupt:
        logger.info("Shutting down Feishu Gateway...")

if __name__ == "__main__":
    run_feishu_gateway()
