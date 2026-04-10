"""
飞书网关 (Feishu Gateway)
监听来自飞书的 WebSocket 事件，将其转发至 Agent API，并将回复发送回飞书。
"""
import asyncio
import json
import logging
import os
import ssl
import sys
import yaml
from pathlib import Path

# 将项目根目录添加到 sys.path，以便导入本地模块
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv() # 加载 .env 中的环境变量（包含 API 凭证）

import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
import requests
from logging.handlers import TimedRotatingFileHandler

# 同时将日志输出到控制台和文件
log_dir = ROOT / "logs"
log_dir.mkdir(exist_ok=True)
log_file = log_dir / "feishu_gateway.log"

log_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# 文件日志处理器：按天切分，保留 7 天
file_handler = TimedRotatingFileHandler(log_file, when="midnight", interval=1, backupCount=7, encoding="utf-8")
file_handler.setFormatter(log_formatter)

# 控制台日志处理器
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_formatter)

logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])
logger = logging.getLogger("FeishuGateway")

# 减少来自飞书 SDK 的噪音（它会在 INFO 级别记录原始的请求/响应体）
logging.getLogger("lark_oapi").setLevel(logging.WARNING)

# Agent 服务的基础 URL
AGENT_API_URL = "http://127.0.0.1:8000/v1/chat"

class FeishuAppClient:
    """飞书应用客户端，封装了应用凭证和 SDK 客户端对象"""
    def __init__(self, name: str, app_id: str, app_secret: str):
        self.name = name
        self.app_id = app_id
        self.app_secret = app_secret
        self.client = lark.Client.builder().app_id(app_id).app_secret(app_secret).build()

def add_reaction(client: lark.Client, message_id: str, emoji_type: str):
    """向特定消息添加表情回复（Reaction）"""
    try:
        req = lark.im.v1.CreateMessageReactionRequest.builder() \
            .message_id(message_id) \
            .request_body(lark.im.v1.CreateMessageReactionRequestBody.builder()
                .reaction_type(lark.im.v1.Emoji.builder().emoji_type(emoji_type).build())
                .build()) \
            .build()
        
        # 在处理过程中同步调用
        client.im.v1.message_reaction.create(req)
    except Exception as e:
        logger.error(f"添加表情反馈失败: {e}")

# 用于记录已发送的消息 ID，防止死循环
sent_message_ids = set()

def send_text_reply(client: lark.Client, receive_id: str, content: str, app_name: str = "default"):
    """将文本回复发送回用户，并追踪消息 ID 以避免无限回显。"""
    msg_content = json.dumps({"text": content})
    logger.info(f"📩 [{app_name}] 发送给 {receive_id} 的消息: {content}")
    
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
        logger.error(f"[{app_name}] 发送回复失败: {resp.msg} (代码: {resp.code})")
    else:
        # 提取消息 ID 以防止处理我们自己的回复
        msg_id = None
        try:
            if hasattr(resp.data, "message_id"):
                msg_id = resp.data.message_id
            elif hasattr(resp.data, "content"):
                msg_id = json.loads(resp.data.content).get("message_id")
        except Exception:
            pass
        if msg_id:
            sent_message_ids.add(msg_id)
        logger.info(f"📤 [{app_name}] 已回复 {receive_id}: {content[:200].replace('\n', ' ')}")

def handle_message(app_client: FeishuAppClient, sender_id: str, msg_id: str, text: str):
    """调用 Agent API 并将结果回复给用户"""
    # 1. 添加“思考中”表情
    add_reaction(app_client.client, msg_id, "THINKING")
    
    # 2. 调用 Agent API
    # 如果不是默认机器人，则在 Session ID 中加入前缀进行隔离
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
        logger.info(f"1 [{app_client.name}] 正在转发请求至 Agent API: {text}")
        # 超时时间设置为 300 秒，以适应长文本回答
        resp = requests.post(AGENT_API_URL, json=payload, timeout=300)
        logger.info(f"2 [{app_client.name}] 已转发请求至 Agent API: {resp.text}")
        resp.raise_for_status()
        reply_text = resp.json().get("response")
        logger.info(f"3 [{app_client.name}] 回复reply_text: {reply_text}")
        if reply_text:
            send_text_reply(app_client.client, sender_id, reply_text, app_name=app_client.name)
            # 3. 回复成功，添加“已完成”表情
            add_reaction(app_client.client, msg_id, "DONE")
            
    except Exception as e:
        logger.error(f"[{app_client.name}] 与 Agent API 通信时出错: {e}")
        # 4. 出错，添加“错误”表情
        add_reaction(app_client.client, msg_id, "CROSS_MARK")

def create_ws_client(app_client: FeishuAppClient):
    """为飞书应用创建一个 WebSocket 客户端"""
    def _on_message_received(data: P2ImMessageReceiveV1) -> None:
        """接收到消息时的回调逻辑"""
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

        # 过滤掉由我们自己发送的消息（避免死循环）
        if msg_id in sent_message_ids:
            sent_message_ids.discard(msg_id)
            return
            
        logger.info(f"📩 [{app_client.name}] 收到来自 {sender_id} 的消息: {text}")
        
        # 在后台线程中处理业务逻辑，防止阻塞 WebSocket 的心跳维持 (Ping-Pong)
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
    """多进程工作负载函数。"""
    import ssl
    import os
    
    # 修复子进程中的环境：删除可能干扰连接的代理设置
    for key in list(os.environ.keys()):
        if key.lower() in ("http_proxy", "https_proxy", "all_proxy", "no_proxy", "ftp_proxy"):
            del os.environ[key]
            
    # 全局禁用 SSL 验证（在某些代理/严格 DNS 环境下飞书 SDK WebSocket 连接可能需要此操作）
    try:
        ssl._create_default_https_context = ssl._create_unverified_context
    except AttributeError:
        pass
        
    # 为 websockets 模块打补丁，强制跳过 SSL 验证
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

    # 每个进程启动独立的 WebSocket 事件循环
    ws = create_ws_client(ac)
    ws.start()

def run_feishu_gateway():
    """读取配置并启动飞书网关服务"""
    # 加载配置
    config_path = ROOT / "config" / "agent.yaml"
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
        
    feishu_cfg = cfg.get("skills", {}).get("feishu", {})
    if not feishu_cfg.get("enable_listener", False):
        logger.info("飞书监听器在配置文件中已禁用。")
        return
        
    # 汇总应用客户端，避免对同一凭证启动多个监听器
    app_clients = []
    
    # 1. 首先加载额外的机器人配置并记录它们的凭证
    apps = feishu_cfg.get("apps", {})
    extra_credentials = set()
    for name, a_cfg in apps.items():
        if not a_cfg.get("enable_listener", False):
            continue
        # 支持从环境变量读取 app_id/secret
        a_id_env = a_cfg.get("app_id_env")
        a_id = os.environ.get(a_id_env) if a_id_env else a_cfg.get("app_id")
        a_secret_env = a_cfg.get("app_secret_env")
        a_secret = os.environ.get(a_secret_env) if a_secret_env else a_cfg.get("app_secret")
        
        if a_id and a_secret:
            app_clients.append(FeishuAppClient(name, a_id, a_secret))
            extra_credentials.add((a_id, a_secret))
    
    # 2. 只有当默认机器人的凭证不在额外机器人中时，才加载默认机器人
    app_id_env = feishu_cfg.get("app_id_env")
    default_app_id = os.environ.get(app_id_env) if app_id_env else feishu_cfg.get("app_id")
    app_secret_env = feishu_cfg.get("app_secret_env")
    default_app_secret = os.environ.get(app_secret_env) if app_secret_env else feishu_cfg.get("app_secret")
    
    if default_app_id and default_app_secret and (default_app_id, default_app_secret) not in extra_credentials:
        app_clients.append(FeishuAppClient("default", default_app_id, default_app_secret))

    if not app_clients:
        logger.error("未找到有效的飞书凭证（App ID/Secret）。")
        return
        
    logger.info(f"正在启动带有 {len(app_clients)} 个机器人的飞书网关...")
    
    # 使用多进程模式运行，每个机器人独占一个进程，确保隔离性
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
        logger.info("飞书网关已停止。")

if __name__ == "__main__":
    run_feishu_gateway()

