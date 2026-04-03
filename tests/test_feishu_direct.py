"""
Direct Feishu API Test Script / 飞书 API 直连测试脚本
Used to diagnose connection and permission issues without Agent logic.
用于在脱离 Agent 逻辑的情况下诊断连接和权限问题。
"""
import os
import asyncio
import json
import logging
from dotenv import load_dotenv
import lark_oapi as lark

# Setup basic logging / 设置基础日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

async def test_send_message(receive_id: str, receive_id_type: str = "open_id"):
    # 1. Load environment variables / 加载环境变量
    load_dotenv()
    app_id = os.environ.get("FEISHU_APP_ID")
    app_secret = os.environ.get("FEISHU_APP_SECRET")

    if not app_id or not app_secret:
        logger.error("❌ FEISHU_APP_ID or FEISHU_APP_SECRET not found in .env!")
        return

    logger.info(f"Connecting with App ID: {app_id}")

    # 2. Build Client / 创建客户端
    client = lark.Client.builder() \
        .app_id(app_id) \
        .app_secret(app_secret) \
        .build()

    # 3. Prepare Request / 准备请求
    content = json.dumps({"text": "Hello! This is a direct test from SmartHomeClaw diagnostic script. / 这是一个来自诊断脚本的测试消息。"})
    
    request = lark.im.v1.CreateMessageRequest.builder() \
        .receive_id_type(receive_id_type) \
        .request_body(lark.im.v1.CreateMessageRequestBody.builder() \
            .receive_id(receive_id) \
            .msg_type("text") \
            .content(content) \
            .build()) \
        .build()

    # 4. Send / 发送
    logger.info(f"Sending to {receive_id} (Type: {receive_id_type})...")
    response = await client.im.v1.message.acreate(request)

    # 5. Analyze Response / 分析响应
    if response.success():
        logger.info("✅ SUCCESS! Message sent.")
        logger.info(f"Response Data: {response.data}")
    else:
        logger.error(f"❌ FAILED! Code: {response.code}, Msg: {response.msg}")
        logger.error(f"Log ID: {response.get_log_id()}")
        
        # Explain common error codes / 解释常见错误码
        if response.code == 99991663:
            logger.warning("Suggestion: Missing 'im:message:send_as_bot' permission. / 建议：缺少发送消息权限。")
        elif response.code == 99991664:
            logger.warning("Suggestion: The bot is not in the chat or the receive_id is invalid. / 建议：机器人不在会话中或 ID 无效。")
        elif response.code == 40006:
            logger.warning("Suggestion: App Secret is incorrect. / 建议：App Secret 不正确。")

if __name__ == "__main__":
    # --- USER: CONFIGURE TEST PARAMETERS HERE / 用户：请在此配置测试参数 ---
    # 1. Use your Open ID (get it from Lark developer console personal info)
    # 2. Or use your email with receive_id_type="email"
    
    TEST_RECEIVE_ID = "ou_xxxxxx"      # Replace with your ID / 替换为您的 ID
    TEST_TYPE = "open_id"             # open_id / email / chat_id
    
    if TEST_RECEIVE_ID == "ou_xxxxxx":
        print("\n[!] Please edit this file and replace TEST_RECEIVE_ID with your real ID.")
        print("[!] 请编辑此文件，将 TEST_RECEIVE_ID 替换为您真实的 ID（例如您的 Open ID 或邮箱）。\n")
    else:
        asyncio.run(test_send_message(TEST_RECEIVE_ID, TEST_TYPE))
