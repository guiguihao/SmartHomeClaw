#!/usr/bin/env python3
"""
SmartHome Agent Entry Point / 智能家居 Agent 启动入口
Usage: python main.py or python main.py chat / 用法: python main.py 或 python main.py chat
"""
import sys
import logging
import os
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler

# Ensure project root is in the system path / 确保项目根目录在路径中
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))


def setup_logging():
    """
    Initialize logging system / 初始化日志系统：
    - File: logs/agent.log, all levels, daily rotation (keeps 7 days) / 文件：logs/agent.log，所有级别，按天滚动保留 7 天
    - Console: WARNING and above to avoid cluttering the chat / 终端：WARNING 以上，不刷屏
    Log level can be controlled via LOG_LEVEL in .env / 日志级别可通过 .env 中 LOG_LEVEL 变量控制
    """
    log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    # Log directory / 日志目录
    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "agent.log"

    # Log format / 日志格式
    fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # File Handler: daily rotation, keep 7 days / 文件 Handler：按天滚动，保留 7 天
    file_handler = TimedRotatingFileHandler(
        log_file,
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(fmt)

    # Console Handler: WARNING and above only to keep CLI clean / 终端 Handler：只显示 WARNING 以上，不打扰对话界面
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(fmt)

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Silence noisy third-party libraries / 屏蔽第三方库的过度日志
    for noisy_lib in ("httpx", "httpcore", "openai", "apscheduler"):
        logging.getLogger(noisy_lib).setLevel(logging.WARNING)


# Run logging setup / 执行日志初始化
setup_logging()

from src.cli.main import cli

if __name__ == "__main__":
    cli()
