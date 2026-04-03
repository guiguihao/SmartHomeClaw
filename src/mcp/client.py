"""
MCP Client - Connects to external MCP Servers, discovers and calls tools / 
MCP 客户端 - 连接外部 MCP Server，发现并调用工具
Supports stdio and HTTP (SSE) transports / 支持 stdio 和 HTTP (SSE) 两种传输方式
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class MCPTool:
    """Wraps a single tool discovered from an MCP Server / 封装从 MCP Server 发现的单个工具"""

    def __init__(self, server_name: str, tool_def: dict):
        self.server_name = server_name
        self.name = tool_def["name"]
        self.description = tool_def.get("description", "")
        self.input_schema = tool_def.get("inputSchema", {})

    def to_openai_function(self) -> dict:
        """Convert to OpenAI function calling format / 转换为 OpenAI function calling 格式"""
        return {
            "type": "function",
            "function": {
                "name": f"mcp_{self.server_name}_{self.name}",
                "description": f"[{self.server_name}] {self.description}",
                "parameters": self.input_schema,
            },
        }


class MCPClient:
    """
    Client for connecting to a single MCP Server. / 连接单个 MCP Server 的客户端。
    Supports stdio (local process) and http (remote service) transports. / 
    支持 stdio（本地进程）和 http（远程服务）两种传输方式。
    """

    def __init__(self, name: str, config: dict):
        self.name = name
        self.config = config
        self.transport = config.get("transport", "stdio")
        self._tools: list[MCPTool] = []
        self._session = None  # mcp Session object / mcp Session 对象

    async def connect(self) -> bool:
        """
        Connect to MCP Server and discover tool list. / 连接到 MCP Server 并发现工具列表。

        Returns:
            True if connection successful / True 表示连接成功
        """
        try:
            if self.transport == "stdio":
                return await self._connect_stdio()
            elif self.transport in ("http", "sse"):
                return await self._connect_http()
            else:
                logger.error(f"[MCP] Unsupported transport: {self.transport} / 不支持的传输方式")
                return False
        except Exception as e:
            logger.error(f"[MCP] Failed to connect to {self.name}: {e} / 连接失败")
            return False

    async def _connect_stdio(self) -> bool:
        """Connect to local MCP Server process via stdio / 通过 stdio 连接本地 MCP Server 进程"""
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        command = self.config.get("command", [])
        if not command:
            logger.error(f"[MCP] stdio transport requires 'command' parameter / stdio 模式需要指定 command 参数")
            return False

        server_params = StdioServerParameters(
            command=command[0],
            args=command[1:],
            env=self.config.get("env", None),
        )

        try:
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools_result = await session.list_tools()
                    self._tools = [
                        MCPTool(self.name, t.model_dump())
                        for t in tools_result.tools
                    ]
                    logger.info(f"[MCP] {self.name} connected successfully, found {len(self._tools)} tools / 连接成功")
                    self._session = session
                    return True
        except Exception as e:
            logger.error(f"[MCP] stdio connection failed: {e} / stdio 连接失败")
            return False

    async def _connect_http(self) -> bool:
        """Connect to remote MCP Server via HTTP/SSE / 通过 HTTP/SSE 连接远程 MCP Server"""
        from mcp import ClientSession
        from mcp.client.sse import sse_client

        url = self.config.get("url", "")
        if not url:
            logger.error(f"[MCP] http transport requires 'url' parameter / http 模式需要指定 url 参数")
            return False

        try:
            async with sse_client(url) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools_result = await session.list_tools()
                    self._tools = [
                        MCPTool(self.name, t.model_dump())
                        for t in tools_result.tools
                    ]
                    logger.info(f"[MCP] {self.name} connected successfully, found {len(self._tools)} tools / 连接成功")
                    self._session = session
                    return True
        except Exception as e:
            logger.error(f"[MCP] HTTP connection failed: {e} / HTTP 连接失败")
            return False

    @property
    def tools(self) -> list[MCPTool]:
        return self._tools

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """
        Call a tool on the MCP Server. / 调用 MCP Server 上的某个工具。

        Args:
            tool_name: Raw tool name (without mcp_{server}_ prefix) / 工具原始名称
            arguments: Dictionary of tool arguments / 工具参数字典

        Returns:
            Tool execution result string / 工具执行结果字符串
        """
        if self._session is None:
            return f"❌ MCP {self.name} not connected / 未连接"

        try:
            result = await self._session.call_tool(tool_name, arguments)
            # Extract text content / 提取文本内容
            if result.content:
                texts = []
                for content in result.content:
                    if hasattr(content, "text"):
                        texts.append(content.text)
                    elif hasattr(content, "data"):
                        texts.append(str(content.data))
                return "\n".join(texts) if texts else "✅ Executed successfully (no content) / 执行完成（无返回内容）"
            return "✅ Executed successfully / 执行完成"
        except Exception as e:
            return f"❌ Tool call failed: {e} / 工具调用失败"


class MCPRegistry:
    """
    MCP Tool Registry. / MCP 工具注册中心。
    Manages connections to multiple MCP Servers, provides unified tool discovery and calling. / 
    管理多个 MCP Server 的连接，提供统一的工具发现和调用接口。
    """

    def __init__(self):
        self._clients: dict[str, MCPClient] = {}

    async def connect_all(self, mcp_configs: list[dict]):
        """
        Connect to all configured MCP Servers. / 批量连接配置中的所有 MCP Server。

        Args:
            mcp_configs: list of mcp_servers from agent.yaml / agent.yaml 中 mcp_servers 列表
        """
        if not mcp_configs:
            logger.info("[MCP] No MCP Servers configured, skipping. / 未配置任何 MCP Server，跳过连接")
            return

        for cfg in mcp_configs:
            name = cfg.get("name", "unknown")
            client = MCPClient(name, cfg)
            success = await client.connect()
            if success:
                self._clients[name] = client
            else:
                logger.warning(f"[MCP] {name} connection failed, skipping. / 连接失败，跳过")

        total = sum(len(c.tools) for c in self._clients.values())
        logger.info(f"[MCP] Connected to {len(self._clients)} servers, registered {total} tools / 共注册 {total} 个工具")

    def get_all_tools_openai_format(self) -> list[dict]:
        """Get OpenAI function calling format for all MCP tools / 获取所有 MCP 工具的 OpenAI function calling 格式定义"""
        tools = []
        for client in self._clients.values():
            for tool in client.tools:
                tools.append(tool.to_openai_function())
        return tools

    async def call_tool(self, full_tool_name: str, arguments: dict) -> str:
        """
        Call a tool using its full name (mcp_{server}_{tool}). / 通过完整工具名（mcp_{server}_{tool}）调用工具。

        Args:
            full_tool_name: e.g., mcp_smarthome_control_device / 如 mcp_smarthome_control_device
            arguments: Tool arguments / 工具参数

        Returns:
            Execution result string / 执行结果字符串
        """
        # Parse tool name: mcp_{server_name}_{tool_name} / 解析工具名
        parts = full_tool_name.split("_", 2)  # ['mcp', 'smarthome', 'control_device']
        if len(parts) < 3 or parts[0] != "mcp":
            return f"❌ Invalid MCP tool name format: {full_tool_name} / 无效的 MCP 工具名格式"

        server_name = parts[1]
        tool_name = parts[2]

        client = self._clients.get(server_name)
        if client is None:
            return f"❌ MCP Server '{server_name}' not connected / 未连接"

        return await client.call_tool(tool_name, arguments)

    def list_servers(self) -> list[dict]:
        """List all connected MCP Servers and their tool counts / 列出所有已连接的 MCP Server 及其工具数量"""
        return [
            {
                "name": name,
                "tools_count": len(client.tools),
                "tools": [t.name for t in client.tools],
            }
            for name, client in self._clients.items()
        ]

    def is_mcp_tool(self, tool_name: str) -> bool:
        """Check if a tool name belongs to an MCP tool / 判断工具名是否属于 MCP 工具"""
        return tool_name.startswith("mcp_")
