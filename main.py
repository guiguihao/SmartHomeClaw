#!/usr/bin/env python3
"""
智能家居 Agent 启动入口
用法: python main.py 或 python main.py chat
"""
import sys
from pathlib import Path

# 确保项目根目录在路径中
sys.path.insert(0, str(Path(__file__).parent))

from src.cli.main import cli

if __name__ == "__main__":
    cli()
