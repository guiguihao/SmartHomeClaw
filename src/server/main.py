"""
Agent 核心服务器 - FastAPI 网关
为外部服务（如飞书网关）提供 HTTP 接口，用于与 Agent 进行交互。
"""
import os
import sys
from pathlib import Path
from typing import Optional
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
import yaml

# 设置根目录路径
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.cli.main import build_agent

# 全局实例
agent_instance = None
cron_instance = None
heartbeat_instance = None

def load_config() -> dict:
    """加载 Agent 配置文件"""
    config_path = ROOT / "config" / "agent.yaml"
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """使用 lifespan 上下文管理器管理服务的启动和关闭事件。"""
    global agent_instance, cron_instance, heartbeat_instance
    os.chdir(ROOT)
    
    # --- 启动阶段 ---
    cfg = load_config()
    agent_instance, _ = await build_agent(cfg)

    # 启动心跳检测 (Heartbeat)
    hb_cfg = cfg.get("heartbeat", {})
    if hb_cfg.get("enabled", True):
        from src.core.heartbeat import HeartbeatScheduler
        heartbeat_instance = HeartbeatScheduler(
            agent=agent_instance,
            interval_minutes=hb_cfg.get("interval_minutes", 5),
            task_file=str(ROOT / hb_cfg.get("task_file", "config/HEARTBEAT.md")),
        )
        await heartbeat_instance.start()
        # 将心跳调度器注入 Agent，使其可通过工具调用读写心跳指令
        agent_instance.set_heartbeat(heartbeat_instance)

    # 启动定时任务 (Cron)
    from src.core.cron import CronScheduler
    cron_instance = CronScheduler(agent=agent_instance)
    await cron_instance.start()
    # 将定时调度器注入 Agent，使其可通过工具调用管理定时任务
    agent_instance.set_cron(cron_instance)
    
    print("🚀 Agent 核心服务器已启动并运行。")
    
    yield
    
    # --- 关闭阶段 ---
    if heartbeat_instance:
        await heartbeat_instance.stop()
    if cron_instance:
        await cron_instance.stop()
    print("👋 Agent 核心服务器已安全关闭。")

import logging

# 配置日志格式和级别
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

# 获取日志记录器
app_logger = logging.getLogger("AgentAPI")
app = FastAPI(title="SmartHome Agent Core API", lifespan=lifespan)

class ChatRequest(BaseModel):
    """聊天请求模型"""
    session_id: str
    message: str
    app_name: Optional[str] = None
    system_override: Optional[str] = None

class ChatResponse(BaseModel):
    """聊天响应模型"""
    response: str

@app.post("/v1/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    """对话接口：接收用户消息并返回 Agent 的回复"""
    if not agent_instance:
        raise HTTPException(status_code=500, detail="Agent 未初始化")
    
    # 记录请求进入
    app_logger.info(f"📩 [{req.app_name or 'Unknown'}] 收到请求: session_id={req.session_id}, 内容=\"{req.message[:500]}...\"")
    start_time = datetime.now()
    
    # 调用 Agent 实例的 chat 方法
    response = await agent_instance.chat(
        user_message=req.message,
        session_id=req.session_id,
        system_override=req.system_override
    )
    
    # 记录请求完成及耗时
    duration = (datetime.now() - start_time).total_seconds()
    app_logger.info(f"📤 [{req.app_name or 'Unknown'}] 回复已生成 (耗时 {duration:.2f}s): \"{response[:500]}...\"")
    
    return {"response": response}

if __name__ == "__main__":
    import uvicorn
    # 启动 Uvicorn 服务器
    uvicorn.run("src.server.main:app", host="127.0.0.1", port=8000, reload=False)

