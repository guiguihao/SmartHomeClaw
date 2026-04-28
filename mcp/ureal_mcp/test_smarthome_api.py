import asyncio
import json
import os
import sys

# Ensure the script can find local modules when run directly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api_client import api_client
from mqtt_client import mqtt_client
from config import config

async def test_all():
    print(f"--- 1. 测试 HTTP API ---")
    print(f"Token: {config.TOKEN[:8]}... (masked)")
    print(f"AppKey: {config.APP_KEY[:8]}... (masked)")
    
    # 1.1 获取家庭列表
    print("\n[API] 获取家庭列表...")
    homes = await api_client.get_home_list()
    if not homes:
        print("❌ 未获取到家庭列表，请检查接口权限或 Token。")
        return
    print(f"✅ 获取到 {len(homes)} 个家庭:")
    for h in homes:
        print(f"  - {h.get('name')} (SN: {h.get('sn')}), 状态: {h.get('online')}")

    # 1.2 获取工程数据 (取第一个 SN)
    sn = homes[0].get('sn')
    print(f"\n[API] 获取 SN: {sn} 的工程数据...")
    project = await api_client.get_project(sn)
    if project:
        print(f"✅ 工程获取成功。包含内容摘要: {str(project)[:100]}...")
    else:
        print(f"❌ 工程获取失败。")

    # 1.3 获取 MQTT 凭证
    print("\n[API] 获取 MQTT 凭证...")
    mqtt_info = await api_client.get_mqtt_info()
    if mqtt_info:
        print(f"✅ MQTT 凭证获取成功: {mqtt_info.get('ip')}:{mqtt_info.get('port')}")
    else:
        print("❌ 未获取到 MQTT 凭证。")
        return

    # 2. 测试 MQTT 连接
    print(f"\n--- 2. 测试 MQTT 连接 ---")
    host = mqtt_info.get('ip')
    port = mqtt_info.get('port', 1883)
    user = mqtt_info.get('username')
    pwd = mqtt_info.get('password')
    
    print(f"正在尝试连接 MQTT: {host}:{port}...")
    try:
        await mqtt_client.connect(host, port, user, pwd)
        print("✅ MQTT 连接成功！")
        
        # 订阅
        mqtt_client.subscribe_gateway(sn)
        print(f"✅ Topic 订阅成功: {config.MQTT_SUB_TOPIC_TEMPLATE.format(sn=sn)}")
        
        # 3. 实时查询状态
        print(f"\n--- 3. 测试设备实时状态查询 (MQTT) ---")
        # 尝试查询第一个 did (通常工程里有 did)
        if 'room' in project and len(project['room']) > 0:
            room = project['room'][0]
            if 'devices' in room and len(room['devices']) > 0:
                did = room['devices'][0].get('did')
                print(f"正在查询设备 did: {did} 的状态...")
                stats = await mqtt_client.query_device_status(sn, did)
                if stats:
                    print(f"✅ 收到状态响应: {json.dumps(stats, indent=2, ensure_ascii=False)}")
                else:
                    print("❌ 查询超时或无响应（可能网关不在线）。")
        else:
            print("未在工程中找到可测试的设备。")

    except Exception as e:
        print(f"❌ MQTT 测试出错: {e}")
    finally:
        # 手动退出异步循环线程
        mqtt_client.client.loop_stop()
        mqtt_client.client.disconnect()

if __name__ == "__main__":
    # 需要先进入 smarthome_mcp 目录或设置 PYTHONPATH
    asyncio.run(test_all())
