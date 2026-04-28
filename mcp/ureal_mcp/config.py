import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# 加载项目根目录的 .env 文件
root_dir = Path(__file__).parent.parent.parent
env_path = root_dir / '.env'
load_dotenv(dotenv_path=env_path)

class Config:
    """智能家居项目配置清单"""
    API_BASE_URL = "https://app-user.hzureal.com"
    TOKEN = os.getenv("UREAL_TOKEN", "")
    APP_KEY = os.getenv("UREAL_APP_KEY", "")
    
    # MQTT 配置
    # 发布频道：$Client/Gw/Manage
    # 订阅频道：$Gw/Tx/{sn}
    MQTT_PUB_TOPIC = "$Client/Gw/Manage"
    MQTT_SUB_TOPIC_TEMPLATE = "$Gw/Tx/{sn}"
    
    # MQTT 网关密码（协议固定值）
    MQTT_GATEWAY_PWD = "ureal504"
    
    # 数据库路径（使用脚本所在目录的绝对路径）
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DB_PATH = os.path.join(_BASE_DIR, "smarthome_state.db")
    
    # 设备能力集 Plist 路径
    PLIST_PATH = os.path.join(_BASE_DIR, "YRDevicePower.plist")

config = Config()

# 启动时校验关键配置
if not config.TOKEN:
    print("⚠️  警告: SMARTHOME_TOKEN 未配置，所有 API 调用将失败", file=sys.stderr)
if not config.APP_KEY:
    print("⚠️  警告: SMARTHOME_APP_KEY 未配置，所有 API 调用将失败", file=sys.stderr)
