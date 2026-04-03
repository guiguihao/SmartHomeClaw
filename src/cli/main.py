"""
CLI 主入口 - 基于 Click + Rich 的命令行交互界面
提供对话、状态、配置、定时任务等完整命令
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

# 确保项目根目录在 Python 路径中
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

load_dotenv()
console = Console()


def load_config() -> dict:
    """加载 agent.yaml 配置文件"""
    config_path = ROOT / "config" / "agent.yaml"
    if not config_path.exists():
        console.print("[red]❌ 找不到配置文件：config/agent.yaml[/red]")
        sys.exit(1)
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


async def build_agent(cfg: dict):
    """根据配置构建并初始化 Agent 和所有子系统"""
    from src.core.model import load_model_from_config
    from src.memory.manager import MemoryManager
    from src.mcp.client import MCPRegistry
    from src.skills.loader import SkillLoader
    from src.core.agent import Agent

    # 切换到项目根目录（确保相对路径正确）
    os.chdir(ROOT)

    console.print("[dim]正在初始化各子系统...[/dim]")

    # 1. 初始化模型
    model_client = load_model_from_config(cfg.get("model", {}))
    console.print(f"  ✓ 模型：[cyan]{model_client.current_provider}[/cyan] / [bold]{model_client.current_model}[/bold]")

    # 2. 初始化记忆
    memory_dir = cfg.get("memory", {}).get("dir", "memory")
    memory = MemoryManager(memory_dir=str(ROOT / memory_dir))
    console.print(f"  ✓ 记忆系统已加载")

    # 3. 连接 MCP Servers
    mcp = MCPRegistry()
    mcp_servers = cfg.get("mcp_servers", []) or []
    if mcp_servers:
        await mcp.connect_all(mcp_servers)
        console.print(f"  ✓ MCP：{len(mcp.list_servers())} 个 Server 已连接")
    else:
        console.print("  ○ MCP：未配置 Server（可在 config/agent.yaml 中添加）")

    # 4. 加载 Skills
    skills = SkillLoader(skills_dir=str(ROOT / "skills"))
    loaded = skills.load_all()
    if loaded:
        console.print(f"  ✓ Skills：{len(loaded)} 个插件已加载 ({', '.join(loaded.keys())})")
    else:
        console.print("  ○ Skills：未发现插件（可在 skills/ 目录下添加）")

    # 5. 构建 Agent
    agent = Agent(
        name=cfg.get("agent", {}).get("name", "SmartHome Agent"),
        model_client=model_client,
        memory=memory,
        mcp_registry=mcp,
        skill_loader=skills,
        max_context_turns=cfg.get("cli", {}).get("max_context_turns", 20),
    )
    return agent, cfg


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """🏠 智能家居 AI Agent - 命令行交互界面"""
    if ctx.invoked_subcommand is None:
        # 默认进入对话模式
        asyncio.run(run_chat())


@cli.command("chat")
def chat_cmd():
    """进入对话模式（默认模式）"""
    asyncio.run(run_chat())


async def run_chat():
    """对话主循环"""
    cfg = load_config()

    # 显示启动面板
    console.print(Panel.fit(
        f"[bold cyan]🏠 {cfg.get('agent', {}).get('name', 'SmartHome Agent')}[/bold cyan]\n"
        f"[dim]版本 {cfg.get('agent', {}).get('version', '1.0.0')}[/dim]\n\n"
        "[dim]输入 [bold]/help[/bold] 查看命令，[bold]/quit[/bold] 退出[/dim]",
        border_style="cyan",
    ))

    agent, cfg = await build_agent(cfg)

    # 启动心跳（后台静默运行）
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
        console.print(f"\n  ✓ 心跳：每 {hb_cfg.get('interval_minutes', 5)} 分钟自检一次")

    # 启动定时任务（Cron）
    from src.core.cron import CronScheduler
    cron = CronScheduler(agent=agent)
    await cron.start()
    console.print(f"  ✓ Cron：APScheduler 已启动\n")

    prompt = cfg.get("cli", {}).get("prompt", "🏠 > ")

    console.print("[bold green]就绪！请开始对话...[/bold green]\n")

    try:
        while True:
            try:
                user_input = console.input(f"[bold cyan]{prompt}[/bold cyan]").strip()
            except (EOFError, KeyboardInterrupt):
                break

            if not user_input:
                continue

            # 内置命令处理
            if user_input.startswith("/"):
                handled = await handle_slash_command(
                    user_input, agent, cron, heartbeat, cfg
                )
                if handled == "quit":
                    break
                continue

            # 发送给 Agent
            with console.status("[dim]思考中...[/dim]", spinner="dots"):
                response = await agent.chat(user_input)

            # 使用 Rich Markdown 渲染回复
            console.print()
            console.print(Markdown(response))
            console.print()

    finally:
        if heartbeat:
            await heartbeat.stop()
        await cron.stop()
        console.print("\n[dim]👋 Agent 已退出[/dim]")


async def handle_slash_command(
    cmd: str,
    agent,
    cron,
    heartbeat,
    cfg: dict,
) -> Optional[str]:
    """
    处理 / 斜杠命令。

    Returns:
        "quit" 表示退出，None 表示继续
    """
    parts = cmd.split(maxsplit=2)
    command = parts[0].lower()

    if command in ("/quit", "/exit", "/q"):
        return "quit"

    elif command == "/help":
        help_text = """
## 可用命令

| 命令 | 说明 |
|------|------|
| `/help` | 显示此帮助 |
| `/quit` | 退出 Agent |
| `/clear` | 清除对话历史 |
| `/status` | 查看 Agent 状态 |
| `/model [名称]` | 查看或切换模型 |
| `/memory` | 查看记忆文件内容 |
| `/cron list` | 列出定时任务 |
| `/cron add` | 添加定时任务（引导式） |
| `/cron del <id>` | 删除定时任务 |
| `/heartbeat` | 立即触发心跳检查 |
| `/skills` | 列出已加载的 Skills |
| `/mcp` | 列出 MCP 连接状态 |
"""
        console.print(Markdown(help_text))

    elif command == "/clear":
        agent.clear_history()
        console.print("[green]✓ 对话历史已清除[/green]")

    elif command == "/status":
        _print_status(agent, cron, heartbeat, cfg)

    elif command == "/model":
        if len(parts) > 1:
            await _switch_model(agent, parts[1], cfg)
        else:
            console.print(
                f"当前模型：[cyan]{agent.model.current_provider}[/cyan] / "
                f"[bold]{agent.model.current_model}[/bold]"
            )
            _print_model_list(cfg)

    elif command == "/memory":
        content = agent.memory.load_all()
        if content:
            console.print(Markdown(content))
        else:
            console.print("[dim]记忆文件为空[/dim]")

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
            console.print("[yellow]用法：/cron [list|add|del <id>][/yellow]")

    elif command == "/heartbeat":
        if heartbeat:
            console.print("[dim]正在手动触发心跳...[/dim]")
            await heartbeat.trigger_now()
        else:
            console.print("[yellow]心跳调度器未启用[/yellow]")

    elif command == "/skills":
        _print_skills(agent)

    elif command == "/mcp":
        _print_mcp_status(agent)

    else:
        console.print(f"[yellow]未知命令：{command}，输入 /help 查看帮助[/yellow]")

    return None


def _print_status(agent, cron, heartbeat, cfg: dict):
    """打印 Agent 状态面板"""
    table = Table(title="Agent 状态", show_header=False, border_style="cyan")
    table.add_column("项目", style="dim")
    table.add_column("状态", style="bold")

    agent_cfg = cfg.get("agent", {})
    table.add_row("Agent 名称", agent_cfg.get("name", "-"))
    table.add_row("当前模型", f"{agent.model.current_provider} / {agent.model.current_model}")
    table.add_row("对话轮数", str(agent.history_length // 2))
    table.add_row("心跳状态", "✓ 运行中" if heartbeat else "○ 未启用")
    table.add_row("MCP Server", str(len(agent.mcp.list_servers())) + " 个")
    table.add_row("Skills", str(len(agent.skills.list_skills())) + " 个")
    table.add_row("Cron 任务", str(len(cron.list_tasks())) + " 个")

    console.print(table)


def _print_model_list(cfg: dict):
    """打印可用模型列表"""
    providers = cfg.get("model", {}).get("providers", [])
    table = Table(title="可用模型", border_style="dim")
    table.add_column("供应商")
    table.add_column("模型")
    table.add_column("Base URL")

    for provider in providers:
        for model in provider.get("models", []):
            table.add_row(
                provider["name"],
                model,
                provider.get("base_url", ""),
            )
    console.print(table)
    console.print("[dim]切换命令：/model <模型名>[/dim]")


async def _switch_model(agent, model_name: str, cfg: dict):
    """切换到指定模型"""
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
            console.print(f"[green]✓ 已切换到 {provider['name']} / {model_name}[/green]")
            return

    console.print(f"[red]❌ 未找到模型：{model_name}[/red]")
    _print_model_list(cfg)


def _print_cron_list(cron):
    """打印 Cron 任务列表"""
    tasks = cron.list_tasks()
    if not tasks:
        console.print("[dim]暂无 Cron 任务，使用 /cron add 添加[/dim]")
        return

    table = Table(title="定时任务", border_style="cyan")
    table.add_column("ID")
    table.add_column("名称")
    table.add_column("Cron")
    table.add_column("下次执行")
    table.add_column("状态")
    table.add_column("描述")

    for t in tasks:
        status = "[green]启用[/green]" if t["enabled"] else "[red]禁用[/red]"
        table.add_row(t["id"], t["name"], t["cron"], t["next_run"], status, t["description"])

    console.print(table)


async def _add_cron_interactive(cron):
    """引导式添加 Cron 任务"""
    console.print("[bold]添加 Cron 任务[/bold]（按 Ctrl+C 取消）\n")
    try:
        task_id = console.input("任务 ID（英文，如 morning_routine）：").strip()
        name = console.input("任务名称（如 早晨起床模式）：").strip()
        cron_expr = console.input("Cron 表达式（分 时 日 月 周，如 0 7 * * * 表示每天7点）：").strip()
        description = console.input("任务描述（Agent 将执行的操作）：").strip()

        if not all([task_id, name, cron_expr, description]):
            console.print("[red]所有字段不能为空[/red]")
            return

        result = cron.add_task(task_id, name, cron_expr, description)
        console.print(result)
    except KeyboardInterrupt:
        console.print("\n[dim]已取消[/dim]")


def _print_skills(agent):
    """打印 Skills 状态"""
    skills = agent.skills.list_skills()
    if not skills:
        console.print("[dim]暂无已加载的 Skill[/dim]")
        console.print("[dim]在 skills/ 目录下添加 Skill 插件目录[/dim]")
        return

    table = Table(title="已加载 Skills", border_style="cyan")
    table.add_column("名称")
    table.add_column("描述")
    table.add_column("工具数")

    for s in skills:
        table.add_row(s["name"], s["description"], str(len(s["tools"])))

    console.print(table)


def _print_mcp_status(agent):
    """打印 MCP 连接状态"""
    servers = agent.mcp.list_servers()
    if not servers:
        console.print("[dim]暂无 MCP Server 连接[/dim]")
        console.print("[dim]在 config/agent.yaml 的 mcp_servers 中添加配置[/dim]")
        return

    table = Table(title="MCP Server 状态", border_style="cyan")
    table.add_column("名称")
    table.add_column("工具数")
    table.add_column("工具列表")

    for s in servers:
        table.add_row(
            s["name"],
            str(s["tools_count"]),
            ", ".join(s["tools"][:5]) + ("..." if len(s["tools"]) > 5 else ""),
        )

    console.print(table)


if __name__ == "__main__":
    cli()
