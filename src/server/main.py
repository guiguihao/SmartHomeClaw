"""
Agent Core Server - FastAPI Gateway
Provides HTTP endpoints for external services (like Feishu Gateway) to interact with the Agent.
"""
import os
import sys
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
import yaml

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.cli.main import build_agent

agent_instance = None
cron_instance = None
heartbeat_instance = None

def load_config() -> dict:
    config_path = ROOT / "config" / "agent.yaml"
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown events using lifespan context manager."""
    global agent_instance, cron_instance, heartbeat_instance
    os.chdir(ROOT)
    
    # --- Startup ---
    cfg = load_config()
    agent_instance, _ = await build_agent(cfg)

    # Start Heartbeat
    hb_cfg = cfg.get("heartbeat", {})
    if hb_cfg.get("enabled", True):
        from src.core.heartbeat import HeartbeatScheduler
        heartbeat_instance = HeartbeatScheduler(
            agent=agent_instance,
            interval_minutes=hb_cfg.get("interval_minutes", 5),
            task_file=str(ROOT / hb_cfg.get("task_file", "config/HEARTBEAT.md")),
        )
        await heartbeat_instance.start()

    # Start Cron
    from src.core.cron import CronScheduler
    cron_instance = CronScheduler(agent=agent_instance)
    await cron_instance.start()
    
    print("🚀 Agent Core Server is up and running.")
    
    yield
    
    # --- Shutdown ---
    if heartbeat_instance:
        await heartbeat_instance.stop()
    if cron_instance:
        await cron_instance.stop()
    print("👋 Agent Core Server shutdown complete.")

app = FastAPI(title="SmartHome Agent Core API", lifespan=lifespan)

class ChatRequest(BaseModel):
    session_id: str
    message: str
    app_name: Optional[str] = None
    system_override: Optional[str] = None

class ChatResponse(BaseModel):
    response: str

@app.post("/v1/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    if not agent_instance:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    
    # Use agent's chat method
    response = await agent_instance.chat(
        user_message=req.message,
        session_id=req.session_id,
        system_override=req.system_override
    )
    
    return {"response": response}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.server.main:app", host="127.0.0.1", port=8000, reload=False)
