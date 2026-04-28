import json
import uuid
import asyncio
import time
import sys
import ssl
from typing import Dict, Any, List, Optional
import paho.mqtt.client as mqtt
from config import config
from state_cache import state_cache
from audit_logger import audit_logger

# 维护请求与响应的匹配 (msgid -> future)
_pending_requests: Dict[str, asyncio.Future] = {}

class MqttClient:
    """智能家居 MQTT 客户端类，处理设备控制和多设备状态查询。"""
    def __init__(self):
        self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self._is_connected = False
        self.active_sn: Optional[str] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        """MQTT 连通回调"""
        if rc == 0:
            print("MQTT Connected successfully.", file=sys.stderr)
            self._is_connected = True
        else:
            print(f"MQTT Connection failed with code {rc}", file=sys.stderr)

    def _on_message(self, client, userdata, msg):
        """收到 MQTT 消息时的回调处理"""
        try:
            raw_payload = msg.payload.decode()
            # 记录审计日志
            audit_logger.log_message("RECV", msg.topic, raw_payload)
            
            payload = json.loads(raw_payload)
            msgid = payload.get('msgid')
            method = payload.get('method', 'N/A')
            direction = payload.get('dir', 'ukn')
            sn = payload.get('sn')
            data = payload.get('data', {})

            print(f"DEBUG: [MQTT Recv] Topic: {msg.topic}, Method: {method}, Dir: {direction}, MsgID: {msgid}", file=sys.stderr)

            # 1. 状态同步逻辑：无论是推送通知 (ntf) 还是特定解析方法，都尝试同步状态
            # 兼容两种格式：
            # A. {"data": {"statlist": [...]}}
            # B. {"data": {"devlist": [{"did": 100, "statlist": [...]}]}}
            
            # 处理直接嵌套在 data 下的 statlist
            if "statlist" in data:
                self._update_cache_from_list(sn, data.get("statlist", []))
            
            # 处理嵌套在 devlist 下的 statlist
            if "devlist" in data:
                for dev_item in data.get("devlist", []):
                    dev_did = dev_item.get('did')
                    dev_statlist = dev_item.get('statlist', [])
                    self._update_cache_from_list(sn, dev_statlist, did_override=dev_did)

            # 2. 如果是正在进行的请求响应 (dir='rsp')，满足 Future
            if msgid and msgid in _pending_requests:
                future = _pending_requests[msgid]
                if not future.done():
                    if self.loop and self.loop.is_running():
                        try:
                            self.loop.call_soon_threadsafe(future.set_result, payload)
                        except RuntimeError:
                            pass

        except Exception as e:
            print(f"Error processing MQTT message: {e}", file=sys.stderr)

    def _update_cache_from_list(self, sn: str, statlist: List[Dict], did_override: Optional[int] = None):
        """辅助方法：从状态列表更新缓存"""
        for item in statlist:
            did = did_override if did_override is not None else item.get('did')
            node = item.get('node')
            idx = item.get('idx', 0)
            value = item.get('value')
            if did is not None and node is not None:
                state_cache.update_state(sn, did, node, idx, value)

    async def connect(self, host: str, port: int, username: str = None, password: str = None):
        """异步连接到 MQTT 服务器并开启后台循环"""
        self.loop = asyncio.get_running_loop()
        
        # 处理 SSL/TLS (针对 8883, 443, 8084 等加密端口)
        if port in [8883, 443, 8084]:
            print(f"Enabling TLS for port {port} (Insecure mode for testing)", file=sys.stderr)
            try:
                # 针对测试环境，暂时禁用证书强校验
                self.client.tls_set(cert_reqs=ssl.CERT_NONE)
                self.client.tls_insecure_set(True)
            except Exception as e:
                print(f"Warning: Failed to set TLS: {e}", file=sys.stderr)

        if username and password:
            self.client.username_pw_set(username, password)
        
        # 将阻塞的 connect 调用放入线程池执行，避免卡死 event loop
        print(f"Connecting to MQTT {host}:{port}...", file=sys.stderr)
        try:
            await self.loop.run_in_executor(None, lambda: self.client.connect(host, port, 60))
        except Exception as e:
            print(f"MQTT Connect call failed: {e}", file=sys.stderr)
            return

        self.client.loop_start()  # paho-mqtt 自带线程循环
        
        # 等待连接建立且无错误 (增加超时到 15 秒)
        for _ in range(30):
            if self._is_connected: break
            await asyncio.sleep(0.5)
        
        if not self._is_connected:
            print("Warning: MQTT connection check timeout. It might still be connecting in background.", file=sys.stderr)
            
    def subscribe_gateway(self, sn: str):
        """订阅指定网关的推送频道（单订阅独占模式）"""
        if self.active_sn == sn:
            return
            
        # 如果当前有活跃订阅，先退订
        if self.active_sn:
            old_topic = config.MQTT_SUB_TOPIC_TEMPLATE.format(sn=self.active_sn)
            print(f"Unsubscribing from old topic: {old_topic}", file=sys.stderr)
            result = self.client.unsubscribe(old_topic)
            # unsubscribe 返回 (result, mid)，等待一小段时间确保退订完成
            if result[0] == mqtt.MQTT_ERR_SUCCESS:
                time.sleep(0.2)
            
        # 订阅新主题
        topic = config.MQTT_SUB_TOPIC_TEMPLATE.format(sn=sn)
        print(f"Subscribing to new topic: {topic}", file=sys.stderr)
        self.client.subscribe(topic)
        self.active_sn = sn

    async def _send_request(self, sn: str, method: str, data: Dict[str, Any], timeout: int = 8) -> Dict[str, Any]:
        """封装请求-响应模式。"""
        if not self.loop:
            self.loop = asyncio.get_running_loop()

        msgid = str(uuid.uuid4()).upper() # 使用大写 UUID 匹配参考报文
        request = {
            "msgid": msgid,
            "dir": "req",
            "method": method,
            "token": config.TOKEN,
            "data": data,
            "pwd": config.MQTT_GATEWAY_PWD,
            "sn": sn
        }

        future = self.loop.create_future()
        _pending_requests[msgid] = future
        
        # 发布到统一管理通道 $Client/Gw/Manage
        topic = config.MQTT_PUB_TOPIC
        payload_json = json.dumps(request)
        info = self.client.publish(topic, payload_json)
        
        # 记录审计日志
        audit_logger.log_message("SEND", topic, payload_json, msgid)
        
        print(f"DEBUG: [MQTT Send] Topic: {topic}, MsgID: {msgid}, Status: {info.rc}", file=sys.stderr)
        
        # 等待响应
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            print(f"MQTT Request timeout: {msgid} (method: {method})", file=sys.stderr)
            return None
        finally:
            _pending_requests.pop(msgid, None)

    async def control_device(self, sn: str, did: int, node: str, idx: int, value: Any) -> bool:
        """发送控制报文 (ctrldev)"""
        # 确保已订阅该网关
        self.subscribe_gateway(sn)
        
        data = {
            "ctrllist": [
                {"did": did, "node": node, "idx": idx, "value": value}
            ]
        }
        res = await self._send_request(sn, "ctrldev", data)
        print(f"MQTT Response for control: {res}", file=sys.stderr)
        return res and res.get('code') == 0

    async def query_device_status(self, sn: str, did: int) -> List[Dict[str, Any]]:
        """发送状态查询报文 (querydevstat)"""
        # 确保已订阅该网关
        self.subscribe_gateway(sn)
        
        data = {
            "devlist": [did]
        }
        res = await self._send_request(sn, "querydevstat", data)
        
        # 由于 _on_message 会在收到响应时自动通过 _update_cache_from_list 更新缓存，
        # 此处只需从响应中提取并返回特定 did 的 statlist 即可。
        if res and res.get('code') == 0:
            devlist = res.get('data', {}).get('devlist', [])
            for dev in devlist:
                if dev.get('did') == did:
                    return dev.get('statlist', [])
        return []

# 初始化单例
mqtt_client = MqttClient()
