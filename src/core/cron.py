"""
定时任务引擎（Cron）- 基于 APScheduler 的 cron 风格定时系统
支持动态添加/删除/列出任务，任务状态持久化到 config/crons.yaml
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional
import yaml

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

if TYPE_CHECKING:
    from src.core.agent import Agent

logger = logging.getLogger(__name__)
CRONS_FILE = Path("config/crons.yaml")


@dataclass
class CronTask:
    """定时任务数据模型"""
    id: str                    # 唯一 ID，如 morning_routine
    name: str                  # 任务名称，如 早晨起床模式
    cron: str                  # cron 表达式，如 0 7 * * *（每天7点）
    description: str           # 任务描述，Agent 会执行此描述的指令
    enabled: bool = True       # 是否启用
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


class CronScheduler:
    """
    定时任务引擎（Cron）。
    通过 cron 表达式设定触发时间，到时间后让 Agent 执行指定描述的任务。
    """

    def __init__(self, agent: "Agent"):
        self.agent = agent
        self._scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
        self._tasks: dict[str, CronTask] = {}

    async def start(self):
        """启动调度器并加载持久化的任务"""
        self._load_tasks()
        self._scheduler.start()
        # 注册所有已启用的任务
        for task in self._tasks.values():
            if task.enabled:
                self._register_job(task)
        logger.info(f"[Cron] 调度器已启动，共 {len(self._tasks)} 个任务")

    async def stop(self):
        """停止调度器"""
        self._scheduler.shutdown(wait=False)
        logger.info("[Cron] 调度器已停止")

    def _register_job(self, task: CronTask):
        """向 APScheduler 注册一个定时任务"""
        try:
            # 解析 cron 表达式（标准5段格式：分 时 日 月 周）
            cron_parts = task.cron.split()
            if len(cron_parts) == 5:
                minute, hour, day, month, day_of_week = cron_parts
            else:
                logger.error(f"[Cron] 无效的 cron 表达式：{task.cron}")
                return

            trigger = CronTrigger(
                minute=minute,
                hour=hour,
                day=day,
                month=month,
                day_of_week=day_of_week,
                timezone="Asia/Shanghai",
            )

            self._scheduler.add_job(
                self._execute_task,
                trigger=trigger,
                args=[task],
                id=task.id,
                name=task.name,
                replace_existing=True,
            )
            logger.info(f"[Cron] 注册任务：{task.name} ({task.cron})")
        except Exception as e:
            logger.error(f"[Cron] 注册任务 {task.id} 失败: {e}")

    async def _execute_task(self, task: CronTask):
        """定时触发：让 Agent 执行任务描述"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        print(f"\n⏰ [{now}] Cron 任务触发：{task.name}")
        try:
            result = await self.agent.run_background_task(
                task_description=task.description,
                system_override=f"你正在执行定时触发的任务：{task.name}。请根据描述完成操作：\n{task.description}",
            )
            if result:
                print(f"   结果：{result}")
        except Exception as e:
            logger.error(f"[Cron] 任务 {task.id} 执行失败: {e}")

    def add_task(
        self,
        task_id: str,
        name: str,
        cron: str,
        description: str,
    ) -> str:
        """
        动态添加一个新定时任务。

        Args:
            task_id: 唯一标识符
            name: 任务名称
            cron: cron 表达式（5段，标准格式）
            description: 任务内容描述

        Returns:
            操作结果字符串
        """
        task = CronTask(
            id=task_id,
            name=name,
            cron=cron,
            description=description,
        )
        self._tasks[task_id] = task
        self._register_job(task)
        self._save_tasks()
        return f"✅ Cron 任务 '{name}' 已添加，cron: {cron}"

    def remove_task(self, task_id: str) -> str:
        """删除定时任务"""
        if task_id not in self._tasks:
            return f"❌ 未找到任务 ID：{task_id}"

        task = self._tasks.pop(task_id)
        try:
            self._scheduler.remove_job(task_id)
        except Exception:
            pass
        self._save_tasks()
        return f"✅ Cron 任务 '{task.name}' 已删除"

    def toggle_task(self, task_id: str, enabled: bool) -> str:
        """启用或禁用定时任务"""
        if task_id not in self._tasks:
            return f"❌ 未找到任务 ID：{task_id}"

        task = self._tasks[task_id]
        task.enabled = enabled
        self._save_tasks()

        if enabled:
            self._register_job(task)
            return f"✅ Cron 任务 '{task.name}' 已启用"
        else:
            try:
                self._scheduler.remove_job(task_id)
            except Exception:
                pass
            return f"✅ Cron 任务 '{task.name}' 已禁用"

    def list_tasks(self) -> list[dict]:
        """列出所有定时任务"""
        result = []
        for task in self._tasks.values():
            # 计算下次触发时间
            job = self._scheduler.get_job(task.id)
            next_run = (
                job.next_run_time.strftime("%Y-%m-%d %H:%M:%S")
                if job and job.next_run_time
                else "已禁用"
            )
            result.append({
                "id": task.id,
                "name": task.name,
                "cron": task.cron,
                "description": task.description[:50] + "..." if len(task.description) > 50 else task.description,
                "enabled": task.enabled,
                "next_run": next_run,
            })
        return result

    def _save_tasks(self):
        """持久化任务列表到 YAML 文件"""
        CRONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = [asdict(t) for t in self._tasks.values()]
        with open(CRONS_FILE, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)

    def _load_tasks(self):
        """从 YAML 文件加载持久化的任务"""
        if not CRONS_FILE.exists():
            return
        try:
            with open(CRONS_FILE, encoding="utf-8") as f:
                data = yaml.safe_load(f) or []
            for item in data:
                task = CronTask(**item)
                self._tasks[task.id] = task
            logger.info(f"[Cron] 从文件加载了 {len(self._tasks)} 个任务")
        except Exception as e:
            logger.error(f"[Cron] 加载任务文件失败: {e}")
