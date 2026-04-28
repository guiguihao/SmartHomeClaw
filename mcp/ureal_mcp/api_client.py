import hashlib
import json
import sys
import time
import httpx
from typing import List, Dict, Any, Optional
from config import config

class ApiClient:
    """智能家居云端 HTTP API 客户端封装 (带 MD5 签名认证)"""
    def __init__(self):
        self.base_url = config.API_BASE_URL
        self.token = config.TOKEN
        self.app_key = config.APP_KEY
        self._client: Optional[httpx.AsyncClient] = None

    def _generate_sign(self, timestamp: int) -> str:
        """生成 API 签名: md5(timestamp + '_hzureal.com_2019')"""
        sign_str = f"{timestamp}_hzureal.com_2019"
        return hashlib.md5(sign_str.encode()).hexdigest()

    async def _get_client(self) -> httpx.AsyncClient:
        """获取或创建复用的 HTTP 客户端（连接池）"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def _post(self, endpoint: str, data: Dict[str, Any] = None, retries: int = 2) -> Dict[str, Any]:
        """封装 POST 请求逻辑，包含签名、认证 Header 和重试机制"""
        url = f"{self.base_url}{endpoint}"
        
        timestamp = int(time.time() * 1000)
        sign = self._generate_sign(timestamp)
        
        headers = {
            "Content-Type": "application/json",
            "timestamp": str(timestamp),
            "sign": sign
        }
        
        payload = data or {}
        if self.token and "token" not in payload:
            payload["token"] = self.token
        if self.app_key and "appKey" not in payload:
            payload["appKey"] = self.app_key
        
        print(f"\n>>> API Request: {endpoint}", file=sys.stderr)
        print(f"Payload: {json.dumps(payload, indent=2)}", file=sys.stderr)
        
        last_error = None
        for attempt in range(retries + 1):
            try:
                client = await self._get_client()
                response = await client.post(url, json=payload, headers=headers)
                print(f"<<< API Response Raw: {response.text[:500]}...", file=sys.stderr)
                response.raise_for_status()
                result = response.json()
                if result.get('code') != 0:
                    print(f"❌ API Error ({result.get('code')}): {result.get('msg')} (URL: {endpoint})", file=sys.stderr)
                    return None
                return result.get('data', {})
            except Exception as e:
                last_error = e
                print(f"HTTP Request failed (attempt {attempt + 1}/{retries + 1}): {e}", file=sys.stderr)
                if attempt < retries:
                    await __import__('asyncio').sleep(1.0 * (attempt + 1))
        
        print(f"HTTP Request failed after {retries + 1} attempts: {last_error}", file=sys.stderr)
        return None

    async def close(self):
        """关闭 HTTP 客户端"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def get_home_list(self) -> List[Dict[str, Any]]:
        """获取用户家庭/网关列表 (API v2)"""
        return await self._post("/host/list2")

    async def get_project(self, sn: str) -> Dict[str, Any]:
        """获取家庭工程数据"""
        return await self._post("/host/project/get", {"sn": sn})

    async def get_mqtt_info(self, client_type: str = "Android") -> Dict[str, Any]:
        """获取 MQTT 连接参数"""
        data = await self._post("/mqtt/cloud/get", {"type": client_type})
        if isinstance(data, list) and len(data) > 0:
            return data[0]
        return data

api_client = ApiClient()
