import asyncio
import json
import sys
import os
from typing import Optional, List, Dict, Any, Union
from mcp.server.fastmcp import FastMCP, Context
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager

# --- 路径加固：确保脚本无论从哪启动都能找到旁边的组件 ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(CURRENT_DIR)
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

# --- 自定义组件导入 ---
from config import config
from api_client import api_client
from mqtt_client import mqtt_client
from device_power import device_power
from state_cache import state_cache
from history_analyzer import history_analyzer

# 强制所有顶级打印到 stderr，不再劫持 stdout
print("### Smarthome MCP Server loading...", file=sys.stderr)

# 1. 定义生命周期管理：初始化 MQTT 连接
@asynccontextmanager
async def lifespan(server: FastMCP):
    """
    智能家居服务器生命周期管理。
    """
    print("### Lifespan starting...", file=sys.stderr)
    try:
        mqtt_info = await api_client.get_mqtt_info()
        if mqtt_info:
            print(f"### MQTT Config fetched. Connecting to {mqtt_info.get('ip')}...", file=sys.stderr)
            await mqtt_client.connect(
                mqtt_info.get('ip'), 
                mqtt_info.get('port', 1883), 
                mqtt_info.get('username'), 
                mqtt_info.get('password')
            )
            
            # 自动订阅逻辑已移至业务工具层，不再在此处全量启动。
        else:
            print("### Warning: No MQTT credentials.", file=sys.stderr)
    except Exception as e:
        print(f"### Critical error during startup: {e}", file=sys.stderr)
        
    yield
    # 关机清理
    try:
        if mqtt_client.client:
            mqtt_client.client.loop_stop()
            mqtt_client.client.disconnect()
    except Exception as e:
        print(f"### Error during shutdown: {e}", file=sys.stderr)

# 2. 初始化 FastMCP 服务器
mcp = FastMCP("smarthome_mcp", lifespan=lifespan)

# --- 参数模型定义 ---

class LocalSceneAction(BaseModel):
    sn: str = Field(..., description="网关序列号 (Gateway SN)")
    did: int = Field(..., description="设备 ID (did)")
    node: str = Field(..., description="控制节点 (如 Switch)")
    idx: int = Field(default=0, description="索引 idx")
    value: Any = Field(..., description="控制值 (如 'on', 25)")
    delay: int = Field(default=500, description="执行该动作后的等待延时 (单位：毫秒)")

class LocalSceneInput(BaseModel):
    name: str = Field(..., description="场景名称")
    description: Optional[str] = Field(default="", description="场景功能描述")
    actions: List[LocalSceneAction] = Field(..., description="动作序列")

class SceneNameInput(BaseModel):
    name: str = Field(..., description="本地场景名称")

# --- MCP 工具定义 ---

@mcp.tool(name="smarthome_get_homes", annotations={"readOnlyHint": True})
async def get_homes() -> str:
    """获取用户账号下的所有家庭及网关列表。
    
    ⚠️ 重要说明：
    返回结果中的 'hostlist' 或 'snlist' 包含的以 'G' 开头的字符串即为 'Gateway SN'。
    后续所有设备控制和工程查询工具都必须使用此 SN，严禁误用 HomeID。
    """
    homes = await api_client.get_home_list()
    # 在最外层注入一个强引导提示
    result = {
        "AI_GUIDE": "请注意：控制设备时必须使用以 'G' 开头的序列号 (SN)，不要误用纯数字的家庭 ID。",
        "homes": homes
    }
    return json.dumps(result, indent=2, ensure_ascii=False)

@mcp.tool(name="smarthome_get_project")
async def get_project(sn: str, force_update: bool = False) -> str:
    """获取指定网关的工程配置数据。
    
    参数：
    - sn: 网关序列号 (Gateway SN，通常以 G 开头。注意：严禁使用纯数字的家庭 ID)。
    - force_update: 是否强制刷新。
    """
    # 确保在获取工程时，底层 MQTT 自动切换到该网格的单订阅
    mqtt_client.subscribe_gateway(sn)
    
    project_json = None
    if not force_update:
        project_json = state_cache.get_cached_project(sn)
    
    if not project_json:
        print(f"### Fetching fresh project data for {sn}...", file=sys.stderr)
        project_data = await api_client.get_project(sn)
        if project_data:
            project_json = json.dumps(project_data, ensure_ascii=False)
            state_cache.save_project(sn, project_json)
        else:
            return f"Error: 无法从云端获取网关 {sn} 的工程数据。"
    
    return project_json

@mcp.tool(name="smarthome_control_device")
async def control_device(sn: str, did: int, node: str, value: Any, idx: int = 0) -> str:
    """控制智能设备按钮、开关或调节数值。
    
    参数：
    - sn: 网关序列号 (Gateway SN，通常以 G 开头。注意：严禁使用纯数字的家庭 ID)。
    - did: 设备 ID
    - node: 控制节点 (如 Switch, SetTemp)
    - value: 控制值 (如 'on', 'off', 25)
    - idx: 索引 (默认为 0)
    """
    success = await mqtt_client.control_device(sn, did, node, idx, str(value))
    if success:
        task = asyncio.create_task(mqtt_client.query_device_status(sn, did))
        task.add_done_callback(lambda t: t.exception() if t.exception() else None)
        return f"控制成功: 设备 {did} -> {node}={value}"
    return f"控制失败: 网关 {sn} 响应超时。"
    
@mcp.tool(name="smarthome_get_device_capabilities", annotations={"readOnlyHint": True})
async def get_device_capabilities(device_type: str) -> str:
    """获取指定设备型号的物理能力描述（基于 YRDevicePower.plist）。
    
    参数：
    - device_type: 设备型号字符串 (从 get_project 的 devicetype 字段获取)。
    """
    return device_power.describe_device_capabilities(device_type)

@mcp.tool(name="smarthome_query_device_status")
async def query_device_status(sn: str, did: int, node: Optional[str] = None, idx: Optional[int] = None) -> str:
    """实时查询设备当前的状态值。
    
    参数：
    - sn: 网关序列号 (Gateway SN，通常以 G 开头)。
    - did: 设备 ID
    """
    stats = await mqtt_client.query_device_status(sn, did)
    if node:
        _idx = idx if idx is not None else 0
        for item in stats:
            if item.get('node') == node and item.get('idx', 0) == _idx:
                return json.dumps(item, indent=2, ensure_ascii=False)
        return f"未找到节点 {node} (idx={_idx})。"
    return json.dumps(stats, indent=2, ensure_ascii=False)

@mcp.tool(name="smarthome_create_local_scene")
async def create_local_scene(params: LocalSceneInput) -> str:
    """在本地数据库创建一个自定义场景。"""
    actions_data = [action.model_dump() for action in params.actions]
    state_cache.save_local_scene(params.name, json.dumps(actions_data, ensure_ascii=False), params.description)
    return f"本地场景 '{params.name}' 已创建。"

@mcp.tool(name="smarthome_list_local_scenes", annotations={"readOnlyHint": True})
async def list_local_scenes() -> str:
    """列出所有本地定义的自定义场景。"""
    scenes = state_cache.list_all_local_scenes()
    return json.dumps(scenes, indent=2, ensure_ascii=False) if scenes else "无本地场景。"

@mcp.tool(name="smarthome_execute_local_scene")
async def execute_local_scene(params: SceneNameInput) -> str:
    """执行一个在本地定义的自定义场景。"""
    scene = state_cache.get_local_scene(params.name)
    if not scene: return f"未找到场景 '{params.name}'。"
    actions = json.loads(scene["actions_json"])
    results = []
    for action in actions:
        success = await mqtt_client.control_device(
            action['sn'], action['did'], action['node'], action['idx'], action['value']
        )
        results.append(f"{action['did']} {action['node']} -> {'OK' if success else 'FAIL'}")
        
        # 场景指令间默认延时
        delay_ms = action.get('delay', 500)
        await asyncio.sleep(delay_ms / 1000.0)
        
    return f"场景 '{params.name}' 执行完毕：\n" + "\n".join(results)

@mcp.tool(name="smarthome_delete_local_scene")
async def delete_local_scene(params: SceneNameInput) -> str:
    """从数据库中删除一个本地自定义场景。"""
    return f"场景 '{params.name}' 已删除。" if state_cache.delete_local_scene(params.name) else "未找到场景。"

@mcp.tool(name="smarthome_get_mcp_status", annotations={"readOnlyHint": True})
async def get_mcp_status() -> str:
    """获取当前 MCP 服务器的运行状态。"""
    return json.dumps({
        "mqtt_connected": mqtt_client._is_connected,
        "active_gateway_sn": mqtt_client.active_sn
    }, indent=2, ensure_ascii=False)

@mcp.tool(name="smarthome_get_history", annotations={"readOnlyHint": True})
async def get_history(sn: str, did: int, nodes: List[str], hours: int = 24) -> str:
    """获取指定设备节点的历史数据（带时间戳的时序记录）。
    
    数据来源：按月分库的审计日志 (smarthome_logs_YYYY_MM.db)
    
    参数：
    - sn: 网关序列号
    - did: 设备 ID
    - nodes: 要查询的节点列表，如 ["QueryRoomTemp", "QueryHumidity"]
    - hours: 查询过去多少小时的数据（默认 24）
    """
    result = history_analyzer.get_history(sn, did, nodes, hours=hours)
    total = sum(len(v) for v in result.values())
    output = {
        "sn": sn,
        "did": did,
        "hours": hours,
        "total_records": total,
        "data": result
    }
    return json.dumps(output, indent=2, ensure_ascii=False)

@mcp.tool(name="smarthome_get_today_summary", annotations={"readOnlyHint": True})
async def get_today_summary(sn: str, did: int, nodes: List[str]) -> str:
    """获取今天的数据摘要（最大/最小/平均/记录数）。
    
    数据来源：本月审计日志数据库
    
    参数：
    - sn: 网关序列号
    - did: 设备 ID
    - nodes: 要统计的数值型节点列表，如 ["QueryRoomTemp", "QueryHumidity"]
    """
    summary = history_analyzer.get_today_summary(sn, did, nodes)
    output = {
        "sn": sn,
        "did": did,
        "period": "today",
        "summary": summary
    }
    return json.dumps(output, indent=2, ensure_ascii=False)

@mcp.tool(name="smarthome_get_period_summary", annotations={"readOnlyHint": True})
async def get_period_summary(sn: str, did: int, nodes: List[str], days: int = 7) -> str:
    """获取多天数据摘要（按天分组统计）。
    
    数据来源：跨月审计日志数据库自动合并
    
    参数：
    - sn: 网关序列号
    - did: 设备 ID
    - nodes: 要统计的数值型节点列表
    - days: 查询过去多少天（默认 7）
    """
    summary = history_analyzer.get_period_summary(sn, did, nodes, days=days)
    output = {
        "sn": sn,
        "did": did,
        "days": days,
        "summary": summary
    }
    return json.dumps(output, indent=2, ensure_ascii=False)

# --- MCP Prompts ---

@mcp.prompt(name="首次使用引导", description="作为您的智能家居管家，引导您完成网关发现、工程加载与场景确认")
def initialize_home() -> str:
    return """
您好！我是您的智能家居助理。我是第一次为您服务，请允许我按以下步骤帮您建立连接：

1. **获取家庭列表**：我将先调用 `smarthome_get_homes` 看看您的账号下有多少个家。
2. **为您展示并请您选择**：我会列出所有发现的家庭名称及对应网关 SN。
   - ⚠️ **请注意：** 如果您有多个网关，我会询问您："建议先加载哪一个家的工程配置？"
3. **精准加载工程**：在您确认后，我才会对选定的网关调用 `smarthome_get_project` 以展示详细设备。
4. **场景扫描**：最后我会确认您在本地数据库中是否有已保存的联动场景。

如果您已经准备好了，请对我说："开始扫描我名下的家庭列表"。
"""

@mcp.prompt(name="设备深度诊断", description="对特定设备进行多维度体检，包括故障码分析")
def device_diagnostic(sn: str, did: int) -> str:
    return f"""
请对网关 {sn} (请确保是以 G 开头的 SN) 下的设备 {did} 进行深度检查：

1. 调用 `smarthome_query_device_status` 获取实时节点状态。
2. 重点分析 QueryErrCode 字段（如有），判断设备是否有故障。
3. 检查设备在线状态 (QueryLinkStat)，确认通信是否正常。
4. 如有必要，可调用 `smarthome_get_device_capabilities` 查看该设备支持的控制节点。
"""

@mcp.prompt(name="全屋场景设计大师", description="为您量身定制并保存本地场景")
def scenario_advisor(sn: str) -> str:
    return f"""
您是资深架构师。网关 SN 是 {sn}。
1. 请先查询 `smarthome_get_project` 获取该网关下的所有设备和房间信息。
2. 了解各设备的控制节点（可用 `smarthome_get_device_capabilities` 查看具体型号的能力）。
3. 构思 3 路本地场景方案，例如：
   - "离家模式"：关闭所有空调、地暖、新风
   - "回家模式"：开启空调、调节温度到舒适区间
   - "睡眠模式"：关闭灯光、调节地暖温度
4. 利用 `smarthome_create_local_scene` 将场景写入本地数据库。

**⚠️ 写入格式规范 ⚠️**
```json
{{
  "name": "场景名称",
  "description": "场景功能描述",
  "actions": [
    {{"sn": "{sn}", "did": 1001, "node": "Switch", "idx": 0, "value": "on", "delay": 500}},
    {{"sn": "{sn}", "did": 1002, "node": "SetTemp", "idx": 0, "value": "24", "delay": 1000}}
  ]
}}
```

创建后可使用 `smarthome_execute_local_scene` 执行场景进行验证。
"""

@mcp.prompt(name="温湿度历史分析", description="分析指定设备一段时间内的温湿度变化趋势")
def temperature_humidity_analysis(sn: str, did: int, days: int = 7) -> str:
    return f"""
请对网关 {sn} 下设备 {did} 进行温湿度历史分析：

1. 首先获取设备信息：`smarthome_get_project` 确认设备类型和名称。
2. 调用 `smarthome_get_period_summary` 查询过去 {days} 天的温湿度数据。
   - 节点：QueryRoomTemp（室温）、QueryHumidity（湿度）
3. 分析数据趋势：
   - 最高/最低温度出现在什么时段
   - 温度波动范围是否正常
   - 湿度变化是否在舒适区间 (40%-60%)
4. 如需查看更详细的小时级数据，可使用 `smarthome_get_history`。

请给出分析结论和建议。
"""

@mcp.prompt(name="今日环境健康报告", description="生成当天室内环境舒适度报告")
def daily_environment_report(sn: str, did: int) -> str:
    return f"""
请为网关 {sn} 下设备 {did} 生成今日环境健康报告：

1. 调用 `smarthome_get_today_summary` 获取今日统计数据。
2. 关注以下指标：
   - 温度 (QueryRoomTemp)：最佳舒适区间 20-26°C
   - 设定温度 (QuerySetTemp)：是否与实际温度匹配
   - 湿度 (QueryHumidity)：最佳舒适区间 40%-60%
   - 设备开关状态 (QuerySwitch)
3. 根据数据给出舒适度评分和建议：
   - 温度是否适宜
   - 是否需要加湿/除湿
   - 设备运行是否正常
4. 额外检查：设备在线状态、加热状态等。

生成一个简洁的健康报告给用户。
"""

@mcp.prompt(name="全屋设备对比分析", description="对比多个同类设备的运行状态")
def multi_device_comparison(sn: str, dids: List[int]) -> str:
    return f"""
请对网关 {sn} 下的多个设备进行对比分析：

1. 首先调用 `smarthome_get_project` 获取该网关下所有设备列表。
2. 从设备列表中筛选出需要对比的设备 ID：{dids}
3. 逐个调用 `smarthome_query_device_status` 获取各设备实时状态。
4. 对比维度：
   - 各设备的开关状态
   - 设定温度 vs 实际温度
   - 运行模式 (制冷/制热/地暖等)
   - 在线状态
5. 生成对比表格，帮助用户了解全屋设备差异。

注意：如设备离线，需标注并提示用户检查设备电源/网络。
"""

@mcp.prompt(name="智能家居节能建议", description="基于设备运行数据给出节能优化建议")
def energy_saving_advice(sn: str) -> str:
    return f"""
请对网关 {sn} 进行节能分析：

1. 调用 `smarthome_get_project` 获取该网关下所有设备。
2. 筛选出耗能设备类型：空调、地暖、锅炉、新风等。
3. 调用 `smarthome_get_period_summary` (建议查询7天或30天数据)。
4. 分析各设备的：
   - 运行时间占比
   - 温度设定是否合理
   - 是否存在不必要的长时间运行
5. 根据分析结果给出节能建议，例如：
   - 建议温度降低/升高 X 度
   - 离家模式未启用，建议添加
   - 非必要设备建议定时关闭
   - 根据室外温度建议调整运行策略

请给出具体可操作的节能方案。
"""

if __name__ == "__main__":
    mcp.run()
