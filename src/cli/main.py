"""
CLI Main Entry - Command Line Interface based on Click + Rich / 
CLI 主入口 - 基于 Click + Rich 的命令行交互界面
Provides dialogue, status, config, and cron management / 提供对话、状态、配置、定时任务等完整命令
"""
from __future__ import annotations

import asyncio
import os
import sys
import logging
from pathlib import Path
from typing import Optional

import click
import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich import print as rprint

# Ensure project root is in Python path / 确保项目根目录在 Python 路径中
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

load_dotenv()
console = Console()


def load_config() -> dict:
    """Load agent.yaml configuration / 加载 agent.yaml 配置文件"""
    config_path = ROOT / "config" / "agent.yaml"
    if not config_path.exists():
        console.print("[red]❌ Configuration file not found: config/agent.yaml / 找不到配置文件[/red]")
        sys.exit(1)
    
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


async def build_agent(cfg: dict):
    """Build and initialize Agent and all subsystems / 根据配置构建并初始化 Agent 和所有子系统"""
    from src.core.model import load_model_from_config
    from src.memory.manager import MemoryManager
    from src.mcp.client import MCPRegistry
    from src.skills.loader import SkillLoader
    from src.core.agent import Agent

    # Change to project root / 切换到项目根目录（确保相对路径正确）
    os.chdir(ROOT)

    console.print("[dim]Initializing subsystems... / 正在初始化各子系统...[/dim]")

    # 1. Initialize Model / 初始化模型
    model_client = load_model_from_config(cfg.get("model", {}))
    console.print(f"  ✓ Model / 模型：[cyan]{model_client.current_provider}[/cyan] / [bold]{model_client.current_model}[/bold]")

    # 2. Initialize Memory / 初始化记忆
    memory_dir = cfg.get("memory", {}).get("dir", "memory")
    memory = MemoryManager(memory_dir=str(ROOT / memory_dir))
    console.print(f"  ✓ Memory system loaded / 记忆系统已加载")

    # 3. Connect MCP Servers / 连接 MCP Servers
    mcp = MCPRegistry()
    mcp_servers = cfg.get("mcp_servers", []) or []
    if mcp_servers:
        await mcp.connect_all(mcp_servers)
        console.print(f"  ✓ MCP: {len(mcp.list_servers())} servers connected / 个 Server 已连接")
    else:
        console.print("  ○ MCP: No servers configured / 未配置 Server（可在 config/agent.yaml 中添加）")

    # 4. Load Skills / 加载 Skills
    skills = SkillLoader(skills_dir=str(ROOT / "skills"))
    loaded = skills.load_all(cfg.get("skills", {}))
    
    # 5. Build Agent / 构建 Agent
    agent = Agent(
        name=cfg.get("agent", {}).get("name", "SmartHome Agent"),
        model_client=model_client,
        memory=memory,
        mcp_registry=mcp,
        skill_loader=skills,
        max_context_turns=cfg.get("cli", {}).get("max_context_turns", 20),
        session_dir=cfg.get("agent", {}).get("session_dir", "sessions"),
    )
    return agent, cfg

@click.group()
def cli():
    """
    🏠 SmartHome AI Agent

    充分利用 AI 的智能家居控制中型。
    运行子命令来启动对应模式。
    """
    pass  # 不默认进入任何模式，显示帮助信息 / Show help by default


@cli.command("chat")
def chat_cmd():
    """Enter interactive chat mode / 进入对话模式"""
    asyncio.run(run_chat())

@cli.command("serve")
def serve_cmd():
    """Start Agent backend services only (no CLI chat) / 仅启动后台服务，不进入对话"""
    asyncio.run(run_serve())

async def run_serve():
    """
    Start all background services without interactive chat.
    仅启动叿书监听、心跳、Cron 等后台服务，不开启 CLI 对话。
    """
    cfg = load_config()
    console.print(Panel.fit(
        f"[bold cyan]🏠 {cfg.get('agent', {}).get('name', 'SmartHome Agent')}[/bold cyan]\n"
        f"[dim]Version / 版本 {cfg.get('agent', {}).get('version', '1.0.0')} — Backend Mode / 后台模式[/dim]",
        border_style="cyan",
    ))

    agent, cfg = await build_agent(cfg)

    # Start Heartbeat / 启动心跳
    hb_cfg = cfg.get("heartbeat", {})
    heartbeat = None
    if hb_cfg.get("enabled", True):
        from src.core.heartbeat import HeartbeatScheduler
        heartbeat = HeartbeatScheduler(
            agent=agent,
            interval_minutes=hb_cfg.get("interval_minutes", 5),
            task_file=str(ROOT / hb_cfg.get("task_file", "config/HEARTBEAT.md")),
        )
        await heartbeat.start()
        # 将心跳调度器注入 Agent
        agent.set_heartbeat(heartbeat)
        console.print(f"  ✓ Heartbeat: every {hb_cfg.get('interval_minutes', 5)} min")

    # Start Cron / 启动Cron
    from src.core.cron import CronScheduler
    cron = CronScheduler(agent=agent)
    await cron.start()
    # 将定时调度器注入 Agent
    agent.set_cron(cron)
    console.print(f"  ✓ Cron: Scheduler started")

    console.print("\n[bold green]一切后台服务已启动，按 Ctrl+C 来停止...[/bold green]")

    try:
        # Keep the process alive / 保持运行
        import asyncio as _asyncio
        while True:
            await _asyncio.sleep(60)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        if heartbeat:
            await heartbeat.stop()
        await cron.stop()
        console.print("\n[dim]👋 Backend services stopped / 后台服务已停止[/dim]")


async def run_chat():
    """Main conversation loop / 对话主循环"""
    cfg = load_config()

    # Display startup panel / 显示启动面板
    console.print(Panel.fit(
        f"[bold cyan]🏠 {cfg.get('agent', {}).get('name', 'SmartHome Agent')}[/bold cyan]\n"
        f"[dim]Version / 版本 {cfg.get('agent', {}).get('version', '1.0.0')}[/dim]\n\n"
        "[dim]Enter [bold]/help[/bold] for commands, [bold]/quit[/bold] to exit / 输入 /help 查看命令，/quit 退出[/dim]",
        border_style="cyan",
    ))

    agent, cfg = await build_agent(cfg)

    # Start Heartbeat (Background) / 启动心跳（后台静默运行）
    hb_cfg = cfg.get("heartbeat", {})
    heartbeat = None
    if hb_cfg.get("enabled", True):
        from src.core.heartbeat import HeartbeatScheduler
        heartbeat = HeartbeatScheduler(
            agent=agent,
            interval_minutes=hb_cfg.get("interval_minutes", 5),
            task_file=str(ROOT / hb_cfg.get("task_file", "config/HEARTBEAT.md")),
        )
        await heartbeat.start()
        # 将心跳调度器注入 Agent，使其可通过对话操作心跳配置
        agent.set_heartbeat(heartbeat)
        console.print(f"\n  ✓ Heartbeat: every {hb_cfg.get('interval_minutes', 5)} min / 心跳：每 5 分钟自检一次")

    # Start Cron Scheduler / 启动定时任务（Cron）
    from src.core.cron import CronScheduler
    cron = CronScheduler(agent=agent)
    await cron.start()
    # 将定时调度器注入 Agent，使其可通过对话管理定时任务
    agent.set_cron(cron)
    console.print(f"  ✓ Cron: Scheduler started / APScheduler 已启动")

    prompt = cfg.get("cli", {}).get("prompt", "🏠 > ")

    console.print("\n[bold green]Ready! Please start chatting... / 就绪！请开始对话...[/bold green]\n")

    try:
        while True:
            try:
                user_input = console.input(f"[bold cyan]{prompt}[/bold cyan]").strip()
            except (EOFError, KeyboardInterrupt):
                break

            if not user_input:
                continue

            # Handle internal commands / 内置命令处理
            if user_input.startswith("/"):
                handled = await handle_slash_command(
                    user_input, agent, cron, heartbeat, cfg
                )
                if handled == "quit":
                    break
                continue

            # Send to Agent / 发送给 Agent
            with console.status("[dim]Thinking... / 思考中...[/dim]", spinner="dots"):
                response = await agent.chat(user_input)

            # Render response with Markdown / 使用 Rich Markdown 渲染回复
            console.print()
            console.print(Markdown(response))
            console.print()

    finally:
        if heartbeat:
            await heartbeat.stop()
        await cron.stop()
        console.print("\n[dim]👋 Agent Exited / 已退出[/dim]")


async def handle_slash_command(
    cmd: str,
    agent,
    cron,
    heartbeat,
    cfg: dict,
) -> Optional[str]:
    """
    Handle / slash commands. / 处理 / 斜杠命令。

    Returns:
        "quit" to exit, None to continue / "quit" 表示退出，None 表示继续
    """
    parts = cmd.split(maxsplit=2)
    command = parts[0].lower()

    if command in ("/quit", "/exit", "/q"):
        return "quit"

    elif command == "/help":
        help_text = """
## Available Commands / 可用命令

| Command / 命令 | Description / 说明 |
|------|------|
| `/help` | Show this help / 显示此帮助 |
| `/quit` | Exit Agent / 退出 Agent |
| `/clear` | Clear chat history / 清除对话历史 |
| `/status` | View Agent status / 查看 Agent 状态 |
| `/model [name]` | View or switch model / 查看或切换模型 |
| `/memory` | View memory content / 查看记忆文件内容 |
| `/cron list` | List cron tasks / 列出定时任务 |
| `/cron add` | Add cron task (Interactive) / 添加定时任务（引导式） |
| `/cron del <id>` | Delete cron task / 删除定时任务 |
| `/heartbeat` | Trigger heartbeat now / 立即触发心跳检查 |
| `/skills` | List loaded skills / 列出已加载的 Skills |
| `/mcp` | List MCP connection status / 列出 MCP 连接状态 |
"""
        console.print(Markdown(help_text))

    elif command == "/clear":
        agent.clear_history()
        console.print("[green]✓ Chat history cleared / 对话历史已清除[/green]")

    elif command == "/status":
        _print_status(agent, cron, heartbeat, cfg)

    elif command == "/model":
        if len(parts) > 1:
            await _switch_model(agent, parts[1], cfg)
        else:
            console.print(
                f"Current Model / 当前模型：[cyan]{agent.model.current_provider}[/cyan] / "
                f"[bold]{agent.model.current_model}[/bold]"
            )
            _print_model_list(cfg)

    elif command == "/memory":
        content = agent.memory.load_all()
        if content:
            console.print(Markdown(content))
        else:
            console.print("[dim]Memory file is empty / 记忆文件为空[/dim]")

    elif command == "/cron":
        if len(parts) < 2:
            _print_cron_list(cron)
        elif parts[1] == "list":
            _print_cron_list(cron)
        elif parts[1] == "add":
            await _add_cron_interactive(cron)
        elif parts[1] == "del" and len(parts) > 2:
            result = cron.remove_task(parts[2])
            console.print(result)
        else:
            console.print("[yellow]Usage / 用法：/cron [list|add|del <id>][/yellow]")

    elif command == "/heartbeat":
        if heartbeat:
            console.print("[dim]Triggering heartbeat manually... / 正在手动触发心跳...[/dim]")
            await heartbeat.trigger_now()
        else:
            console.print("[yellow]Heartbeat scheduler disabled / 心跳调度器未启用[/yellow]")

    elif command == "/skills":
        _print_skills(agent)

    elif command == "/mcp":
        _print_mcp_status(agent)

    else:
        console.print(f"[yellow]Unknown command / 未知命令：{command}. Enter /help for help.[/yellow]")

    return None


def _print_status(agent, cron, heartbeat, cfg: dict):
    """Print Agent Status Panel / 打印 Agent 状态面板"""
    table = Table(title="Agent Status / 状态", show_header=False, border_style="cyan")
    table.add_column("Item / 项目", style="dim")
    table.add_column("Status / 状态", style="bold")

    agent_cfg = cfg.get("agent", {})
    table.add_row("Agent Name / 名称", agent_cfg.get("name", "-"))
    table.add_row("Current Model / 当前模型", f"{agent.model.current_provider} / {agent.model.current_model}")
    table.add_row("Dialogue Turns / 对话轮数", str(agent.history_length // 2))
    table.add_row("Heartbeat Status / 心跳状态", "✓ Running / 运行中" if heartbeat else "○ Disabled / 未启用")
    table.add_row("MCP Servers", str(len(agent.mcp.list_servers())))
    table.add_row("Skills", str(len(agent.skills.list_skills())))
    table.add_row("Cron Tasks / 任务", str(len(cron.list_tasks())))

    console.print(table)


def _print_model_list(cfg: dict):
    """Print Available Models / 打印可用模型列表"""
    providers = cfg.get("model", {}).get("providers", [])
    table = Table(title="Available Models / 可用模型", border_style="dim")
    table.add_column("Provider / 供应商")
    table.add_column("Model / 模型")
    table.add_column("Base URL")

    for provider in providers:
        for model in provider.get("models", []):
            table.add_row(
                provider["name"],
                model,
                provider.get("base_url", ""),
            )
    console.print(table)
    console.print("[dim]Switch command / 切换命令：/model <model_name>[/dim]")


async def _switch_model(agent, model_name: str, cfg: dict):
    """Switch to specified model / 切换到指定模型"""
    import os
    from src.core.model import ModelConfig, ModelClient

    providers = cfg.get("model", {}).get("providers", [])
    for provider in providers:
        if model_name in provider.get("models", []):
            api_key = os.environ.get(provider.get("api_key_env", ""), "")
            new_config = ModelConfig(
                name=model_name,
                provider=provider["name"],
                base_url=provider["base_url"],
                api_key=api_key,
            )
            agent.model.switch_model(new_config)
            console.print(f"[green]✓ Switched to {provider['name']} / {model_name} / 已切换[/green]")
            return

    console.print(f"[red]❌ Model not found / 未找到模型：{model_name}[/red]")
    _print_model_list(cfg)


def _print_cron_list(cron):
    """Print Cron Task List / 打印 Cron 任务列表"""
    tasks = cron.list_tasks()
    if not tasks:
        console.print("[dim]No cron tasks found. Use /cron add to add one. / 暂无 Cron 任务[/dim]")
        return

    table = Table(title="Cron Tasks / 定时任务", border_style="cyan")
    table.add_column("ID")
    table.add_column("Name / 名称")
    table.add_column("Cron")
    table.add_column("Next Run / 下次执行")
    table.add_column("Status / 状态")
    table.add_column("Description / 描述")

    for t in tasks:
        status = "[green]Enabled / 启用[/green]" if t["enabled"] else "[red]Disabled / 禁用[/red]"
        table.add_row(t["id"], t["name"], t["cron"], t["next_run"], status, t["description"])

    console.print(table)


async def _add_cron_interactive(cron):
    """Interactive guided cron task adding / 引导式添加 Cron 任务"""
    console.print("[bold]Add Cron Task / 添加 Cron 任务[/bold] (Press Ctrl+C to cancel)\n")
    try:
        task_id = console.input("Task ID (English, e.g. morning_routine) / 任务 ID：").strip()
        name = console.input("Task Name (e.g. Morning Mode) / 任务名称：").strip()
        cron_expr = console.input("Cron Expression (min hour day month week, e.g. 0 7 * * * ) / Cron 表达式：").strip()
        description = console.input("Task Description (Instructions for Agent) / 任务描述：").strip()

        if not all([task_id, name, cron_expr, description]):
            console.print("[red]All fields are required / 所有字段不能为空[/red]")
            return

        result = cron.add_task(task_id, name, cron_expr, description)
        console.print(result)
    except KeyboardInterrupt:
        console.print("\n[dim]Cancelled / 已取消[/dim]")


def _print_skills(agent):
    """Print Skills Status / 打印 Skills 状态"""
    skills = agent.skills.list_skills()
    if not skills:
        console.print("[dim]No skills loaded / 暂无已加载的 Skill[/dim]")
        return

    table = Table(title="Loaded Skills / 已加载 Skills", border_style="cyan")
    table.add_column("Name / 名称")
    table.add_column("Description / 描述")
    table.add_column("Tools / 工具数")

    for s in skills:
        table.add_row(s["name"], s["description"], str(len(s["tools"])))

    console.print(table)


def _print_mcp_status(agent):
    """Print MCP connection status / 打印 MCP 连接状态"""
    servers = agent.mcp.list_servers()
    if not servers:
        console.print("[dim]No MCP connections / 暂无 MCP Server 连接[/dim]")
        return

    table = Table(title="MCP Server Status / 状态", border_style="cyan")
    table.add_column("Name / 名称")
    table.add_column("Tools / 工具数")
    table.add_column("Tool List / 工具列表")

    for s in servers:
        table.add_row(
            s["name"],
            str(s["tools_count"]),
            ", ".join(s["tools"][:5]) + ("..." if len(s["tools"]) > 5 else ""),
        )

    console.print(table)


if __name__ == "__main__":
    cli()
