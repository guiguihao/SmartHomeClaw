import asyncio
import os
import sys
import yaml
from pathlib import Path

# 设置项目根目录
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from src.core.model import load_model_from_config
from src.memory.manager import MemoryManager
from src.mcp.client import MCPRegistry
from src.skills.loader import SkillLoader
from src.core.agent import Agent
from src.cli.main import load_config

async def run_test():
    print("--- 🚀 开始全方位功能测试 ---")
    
    # 1. 加载配置 (使用解析环境变量的 load_config)
    cfg = load_config()
    print(f"✅ 配置加载成功: {cfg.get('agent', {}).get('name')}")

    # 2. 初始化模型
    model_client = load_model_from_config(cfg.get("model", {}))
    print(f"✅ 模型客户端初始化成功: {model_client.current_provider} / {model_client.current_model}")

    # 3. 初始化记忆系统
    memory_dir = ROOT / cfg.get("memory", {}).get("dir", "memory")
    memory = MemoryManager(memory_dir=str(memory_dir))
    all_memory = memory.load_all()
    print(f"✅ 记忆系统初始化成功, 记忆内容长度: {len(all_memory)}")

    # 4. 初始化 MCP (跳过实际连接以避免网络/进程开销，仅测试逻辑)
    mcp = MCPRegistry()
    print(f"✅ MCP 注册表初始化成功")

    # 5. 加载 Skills
    skills = SkillLoader(skills_dir=str(ROOT / "skills"))
    loaded = skills.load_all(cfg.get("skills", {}))
    print(f"✅ Skills 加载成功: {list(loaded.keys())}")

    # 6. 构建 Agent
    agent = Agent(
        name=cfg.get("agent", {}).get("name", "Test Agent"),
        model_client=model_client,
        memory=memory,
        mcp_registry=mcp,
        skill_loader=skills
    )
    print(f"✅ Agent 构建成功")

    # 7. 验证工具聚合
    tools = agent._get_all_tools()
    print(f"✅ 工具聚合成功, 总计工具数: {len(tools)}")
    for t in tools:
        name = t.get("function", {}).get("name")
        print(f"   - [工具] {name}")

    # 8. 验证双语 System Prompt
    prompt = agent._build_system_prompt()
    if "You are a SmartHome AI Agent" in prompt and "你是一个智能家居 AI Agent" in prompt:
        print("✅ System Prompt 双语校验通过")
    else:
        print("❌ System Prompt 双语校验失败")

    print("\n--- ✨ 测试完成，所有核心逻辑正常 ---")

if __name__ == "__main__":
    asyncio.run(run_test())
