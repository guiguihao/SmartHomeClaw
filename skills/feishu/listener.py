import json
import traceback
import multiprocessing.queues

def run_process_listener(app_name: str, app_id: str, app_secret: str, msg_queue: multiprocessing.queues.Queue):
    """
    Run the WebSocket listener in a completely isolated process environment.
    """
    import os
    # Aggressively clear ALL proxy environment variables before any network imports
    # 在导入任何网络库之前，彻底清除所有代理相关的环境变量
    for key in list(os.environ.keys()):
        if key.lower() in ("http_proxy", "https_proxy", "all_proxy", "no_proxy", "ftp_proxy"):
            del os.environ[key]

    import logging as _logging
    import ssl
    
    _logger = _logging.getLogger("FeishuListener")
    
    try:
        # Prevent SSL Verification Errors in some environments / 在某些本地环境下阻止自签证书报错导致的连接失败
        ssl._create_default_https_context = ssl._create_unverified_context
    except AttributeError:
        pass
        
    try:
        # 终极修复：很多时候系统的自签名证书(代理/安全路由)拦截导致 websockets 证书不过。
        # 我们 Monkey Patch websockets，强行塞入不验证的 ssl 上下文。
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

        # Import inside the process to ensure fresh state / 
        # 为了保证状态全新，在子进程内部才进行核心包和监听器的组装
        import os
        # 尝试清理代理环境变量或要求请求不进行 SSL 校验
        os.environ['http_proxy'] = ''
        os.environ['https_proxy'] = ''
        os.environ['HTTP_PROXY'] = ''
        os.environ['HTTPS_PROXY'] = ''
        os.environ['CURL_CA_BUNDLE'] = ''
        
        import lark_oapi as _lark
        from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
        
        def _on_message_received(data: P2ImMessageReceiveV1) -> None:
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
            msg_id = msg.message_id
            _logger.info(f"📩 [Feishu Process] Received message '{msg_id}' from {sender_id}: {text}")
            
            # Put to queue, to be processed by main process AI logic /
            # 推入队列，交由主进程的 AI 逻辑处理
            msg_queue.put({
                "receive_id": sender_id,
                "message_id": msg_id,
                "text": text,
                "app_name": app_name,
            })
            
        event_handler = _lark.EventDispatcherHandler.builder("", "") \
            .register_p2_im_message_receive_v1(_on_message_received) \
            .build()
            
        ws_client = _lark.ws.Client(
            app_id, 
            app_secret, 
            event_handler=event_handler,
            log_level=_lark.LogLevel.INFO
        )
        
        _logger.info("[Feishu Process] Isolated WebSocket listener starting...")
        # Since it runs in its own process, it is 100% safe to block the main thread here /
        # 因为这是独立的子进程，所以在这里阻塞其主线程绝对安全
        ws_client.start()
        
    except KeyboardInterrupt:
        _logger.info("[Feishu Process] Exiting Gracefully... / 后台监听进程正常退出")
    except Exception as e:
        _logger.error(f"[Feishu Process] Crashing: {e}\n{traceback.format_exc()}")
