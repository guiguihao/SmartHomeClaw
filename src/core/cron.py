"""
Cron Engine - APScheduler-based cron timing system / 定时任务引擎（Cron）- 基于 APScheduler 的 cron 风格定时系统
Supports dynamic add/del/list tasks, task status persisted to config/crons.yaml / 
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
    """Cron Task Data Model / 定时任务数据模型"""
    id: str                    # Unique ID, e.g., morning_routine / 唯一 ID，如 morning_routine
    name: str                  # Task name, e.g., Morning Mode / 任务名称，如 早晨起床模式
    cron: str                  # Cron expression, e.g., 0 7 * * * / cron 表达式，如 0 7 * * *（每天7点）
    description: str           # Task description to be executed by the Agent / 任务描述，Agent 会执行此描述的指令
    enabled: bool = True       # Whether the task is enabled / 是否启用
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


class CronScheduler:
    """
    Cron Task Engine. / 定时任务引擎（Cron）。
    Uses cron expressions to trigger tasks for the Agent to execute. / 
    通过 cron 表达式设定触发时间，到时间后让 Agent 执行指定描述的任务。
    """

    def __init__(self, agent: "Agent"):
        self.agent = agent
        self._scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
        self._tasks: dict[str, CronTask] = {}

    async def start(self):
        """Start scheduler and load persisted tasks / 启动调度器并加载持久化的任务"""
        self._load_tasks()
        self._scheduler.start()
        # Register all enabled tasks / 注册所有已启用的任务
        for task in self._tasks.values():
            if task.enabled:
                self._register_job(task)
        logger.info(f"[Cron] Scheduler started with {len(self._tasks)} tasks / 调度器已启动，共 {len(self._tasks)} 个任务")

    async def stop(self):
        """Stop the scheduler / 停止调度器"""
        self._scheduler.shutdown(wait=False)
        logger.info("[Cron] Scheduler stopped / 调度器已停止")

    def _register_job(self, task: CronTask):
        """Register a job with APScheduler / 向 APScheduler 注册一个定时任务"""
        try:
            # Parse cron expression (Standard 5-part: min hour day month week) / 解析 cron 表达式（标准5段格式：分 时 日 月 周）
            cron_parts = task.cron.split()
            if len(cron_parts) == 5:
                minute, hour, day, month, day_of_week = cron_parts
            else:
                logger.error(f"[Cron] Invalid cron expression: {task.cron} / 无效的 cron 表达式")
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
            logger.info(f"[Cron] Registered task: {task.name} ({task.cron}) / 注册任务")
        except Exception as e:
            logger.error(f"[Cron] Failed to register task {task.id}: {e} / 注册任务失败")

    async def _execute_task(self, task: CronTask):
        """Triggered: let Agent execute description / 定时触发：让 Agent 执行任务描述"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        print(f"\n⏰ [{now}] Cron Triggered: {task.name} / Cron 任务触发：{task.name}")
        try:
            result = await self.agent.run_background_task(
                task_description=task.description,
                system_override=f"You are executing a triggered cron task: {task.name}. Follow this description:\n{task.description}",
            )
            if result:
                print(f"   Result: {result} / 结果")
        except Exception as e:
            logger.error(f"[Cron] Task {task.id} execution failed: {e} / 任务执行失败")

    def add_task(
        self,
        task_id: str,
        name: str,
        cron: str,
        description: str,
    ) -> str:
        """
        Dynamically add a new cron task. / 动态添加一个新定时任务。

        Args:
            task_id: Unique identifier / 唯一标识符
            name: Task name / 任务名称
            cron: Cron expression (5 segments) / cron 表达式
            description: Task content description / 任务内容描述

        Returns:
            Result message / 操作结果字符串
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
        return f"✅ Cron task '{name}' added, cron: {cron} / Cron 任务已添加"

    def remove_task(self, task_id: str) -> str:
        """Remove a cron task / 删除定时任务"""
        if task_id not in self._tasks:
            return f"❌ ID not found: {task_id} / 未找到任务 ID"

        task = self._tasks.pop(task_id)
        try:
            self._scheduler.remove_job(task_id)
        except Exception:
            pass
        self._save_tasks()
        return f"✅ Cron task '{task.name}' removed / 定时任务已删除"

    def toggle_task(self, task_id: str, enabled: bool) -> str:
        """Enable or disable a cron task / 启用或禁用定时任务"""
        if task_id not in self._tasks:
            return f"❌ ID not found: {task_id} / 未找到任务 ID"

        task = self._tasks[task_id]
        task.enabled = enabled
        self._save_tasks()

        if enabled:
            self._register_job(task)
            return f"✅ Task '{task.name}' enabled / 任务已启用"
        else:
            try:
                self._scheduler.remove_job(task_id)
            except Exception:
                pass
            return f"✅ Task '{task.name}' disabled / 任务已禁用"

    def list_tasks(self) -> list[dict]:
        """List all cron tasks / 列出所有定时任务"""
        result = []
        for task in self._tasks.values():
            # Calculate next run time / 计算下次触发时间
            job = self._scheduler.get_job(task.id)
            next_run = (
                job.next_run_time.strftime("%Y-%m-%d %H:%M:%S")
                if job and job.next_run_time
                else "Disabled / 已禁用"
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
        """Persist task list to YAML / 持久化任务列表到 YAML 文件"""
        CRONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = [asdict(t) for t in self._tasks.values()]
        with open(CRONS_FILE, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)

    def _load_tasks(self):
        """Load persisted tasks from YAML / 从 YAML 文件加载持久化的任务"""
        if not CRONS_FILE.exists():
            return
        try:
            with open(CRONS_FILE, encoding="utf-8") as f:
                data = yaml.safe_load(f) or []
            for item in data:
                task = CronTask(**item)
                self._tasks[task.id] = task
            logger.info(f"[Cron] Loaded {len(self._tasks)} tasks from file / 从文件加载了任务")
        except Exception as e:
            logger.error(f"[Cron] Failed to load tasks from file: {e} / 加载任务文件失败")
