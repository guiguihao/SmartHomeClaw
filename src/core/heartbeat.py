"""
心跳调度器 - 定时唤醒 Agent 执行后台检查任务
读取 config/HEARTBEAT.md 作为任务描述，后台静默运行
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.core.agent import Agent

logger = logging.getLogger(__name__)


class HeartbeatScheduler:
    """
    心跳调度器。
    按照配置的间隔定时唤醒 Agent，执行 HEARTBEAT.md 中描述的检查任务。
    心跳是后台静默任务，不影响用户的主对话流。
    """

    def __init__(
        self,
        agent: "Agent",
        interval_minutes: int = 5,
        task_file: str = "config/HEARTBEAT.md",
    ):
        self.agent = agent
        self.interval_seconds = interval_minutes * 60
        self.task_file = Path(task_file)
        self._task: Optional[asyncio.Task] = None
        self._running = False

    def _load_heartbeat_task(self) -> str:
        """读取心跳任务描述文档"""
        if not self.task_file.exists():
            return "请检查设备状态，如有异常请通知用户。"
        return self.task_file.read_text(encoding="utf-8").strip()

    async def start(self):
        """启动心跳后台循环"""
        if self._running:
            logger.warning("[心跳] 调度器已在运行")
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(f"[心跳] 调度器已启动，间隔 {self.interval_seconds // 60} 分钟")

    async def stop(self):
        """停止心跳"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[心跳] 调度器已停止")

    async def _loop(self):
        """心跳主循环"""
        while self._running:
            try:
                await asyncio.sleep(self.interval_seconds)
                if self._running:
                    await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[心跳] 执行异常: {e}")

    async def _tick(self):
        """执行一次心跳任务"""
        now = datetime.now().strftime("%H:%M")
        logger.debug(f"[心跳] {now} 开始心跳检查")

        heartbeat_prompt = self._load_heartbeat_task()
        system_message = (
            "你正在执行定期心跳检查。请遵循以下任务描述安静地完成检查，"
            "只在发现异常时才打印警告信息。\n\n"
            f"{heartbeat_prompt}"
        )

        try:
            result = await self.agent.run_background_task(
                task_description=heartbeat_prompt,
                system_override=system_message,
            )
            # 只打印非空的结果（正常情况下心跳静默）
            if result and result.strip() and result.strip() != "[心跳] 一切正常 ✓":
                print(f"\n{result}")
        except Exception as e:
            logger.error(f"[心跳] 任务执行失败: {e}")

    async def trigger_now(self) -> str:
        """手动触发一次心跳（用于调试）"""
        await self._tick()
        return "心跳已手动触发"
