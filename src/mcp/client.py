"""
MCP 客户端 - 连接外部 MCP Server，发现并调用工具
支持 stdio 和 HTTP (SSE) 两种传输方式
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class MCPTool:
    """封装从 MCP Server 发现的单个工具"""

    def __init__(self, server_name: str, tool_def: dict):
        self.server_name = server_name
        self.name = tool_def["name"]
        self.description = tool_def.get("description", "")
        self.input_schema = tool_def.get("inputSchema", {})

    def to_openai_function(self) -> dict:
        """转换为 OpenAI function calling 格式"""
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
    连接单个 MCP Server 的客户端。
    支持 stdio（本地进程）和 http（远程服务）两种传输方式。
    """

    def __init__(self, name: str, config: dict):
        self.name = name
        self.config = config
        self.transport = config.get("transport", "stdio")
        self._tools: list[MCPTool] = []
        self._session = None  # mcp Session 对象

    async def connect(self) -> bool:
        """
        连接到 MCP Server 并发现工具列表。

        Returns:
            True 表示连接成功
        """
        try:
            if self.transport == "stdio":
                return await self._connect_stdio()
            elif self.transport in ("http", "sse"):
                return await self._connect_http()
            else:
                logger.error(f"[MCP] 不支持的传输方式: {self.transport}")
                return False
        except Exception as e:
            logger.error(f"[MCP] 连接 {self.name} 失败: {e}")
            return False

    async def _connect_stdio(self) -> bool:
        """通过 stdio 连接本地 MCP Server 进程"""
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        command = self.config.get("command", [])
        if not command:
            logger.error(f"[MCP] stdio 模式需要指定 command 参数")
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
                    logger.info(f"[MCP] {self.name} 连接成功，发现 {len(self._tools)} 个工具")
                    self._session = session
                    return True
        except Exception as e:
            logger.error(f"[MCP] stdio 连接失败: {e}")
            return False

    async def _connect_http(self) -> bool:
        """通过 HTTP/SSE 连接远程 MCP Server"""
        from mcp import ClientSession
        from mcp.client.sse import sse_client

        url = self.config.get("url", "")
        if not url:
            logger.error(f"[MCP] http 模式需要指定 url 参数")
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
                    logger.info(f"[MCP] {self.name} 连接成功，发现 {len(self._tools)} 个工具")
                    self._session = session
                    return True
        except Exception as e:
            logger.error(f"[MCP] HTTP 连接失败: {e}")
            return False

    @property
    def tools(self) -> list[MCPTool]:
        return self._tools

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """
        调用 MCP Server 上的某个工具。

        Args:
            tool_name: 工具原始名称（不含 mcp_{server}_ 前缀）
            arguments: 工具参数字典

        Returns:
            工具执行结果字符串
        """
        if self._session is None:
            return f"❌ MCP {self.name} 未连接"

        try:
            result = await self._session.call_tool(tool_name, arguments)
            # 提取文本内容
            if result.content:
                texts = []
                for content in result.content:
                    if hasattr(content, "text"):
                        texts.append(content.text)
                    elif hasattr(content, "data"):
                        texts.append(str(content.data))
                return "\n".join(texts) if texts else "✅ 执行完成（无返回内容）"
            return "✅ 执行完成"
        except Exception as e:
            return f"❌ 工具调用失败: {e}"


class MCPRegistry:
    """
    MCP 工具注册中心。
    管理多个 MCP Server 的连接，提供统一的工具发现和调用接口。
    """

    def __init__(self):
        self._clients: dict[str, MCPClient] = {}

    async def connect_all(self, mcp_configs: list[dict]):
        """
        批量连接配置中的所有 MCP Server。

        Args:
            mcp_configs: agent.yaml 中 mcp_servers 列表
        """
        if not mcp_configs:
            logger.info("[MCP] 未配置任何 MCP Server，跳过连接")
            return

        for cfg in mcp_configs:
            name = cfg.get("name", "unknown")
            client = MCPClient(name, cfg)
            success = await client.connect()
            if success:
                self._clients[name] = client
            else:
                logger.warning(f"[MCP] {name} 连接失败，跳过")

        total = sum(len(c.tools) for c in self._clients.values())
        logger.info(f"[MCP] 共连接 {len(self._clients)} 个 Server，注册 {total} 个工具")

    def get_all_tools_openai_format(self) -> list[dict]:
        """获取所有 MCP 工具的 OpenAI function calling 格式定义"""
        tools = []
        for client in self._clients.values():
            for tool in client.tools:
                tools.append(tool.to_openai_function())
        return tools

    async def call_tool(self, full_tool_name: str, arguments: dict) -> str:
        """
        通过完整工具名（mcp_{server}_{tool}）调用工具。

        Args:
            full_tool_name: 如 mcp_smarthome_control_device
            arguments: 工具参数

        Returns:
            执行结果字符串
        """
        # 解析工具名：mcp_{server_name}_{tool_name}
        parts = full_tool_name.split("_", 2)  # ['mcp', 'smarthome', 'control_device']
        if len(parts) < 3 or parts[0] != "mcp":
            return f"❌ 无效的 MCP 工具名格式: {full_tool_name}"

        server_name = parts[1]
        tool_name = parts[2]

        client = self._clients.get(server_name)
        if client is None:
            return f"❌ MCP Server '{server_name}' 未连接"

        return await client.call_tool(tool_name, arguments)

    def list_servers(self) -> list[dict]:
        """列出所有已连接的 MCP Server 及其工具数量"""
        return [
            {
                "name": name,
                "tools_count": len(client.tools),
                "tools": [t.name for t in client.tools],
            }
            for name, client in self._clients.items()
        ]

    def is_mcp_tool(self, tool_name: str) -> bool:
        """判断工具名是否属于 MCP 工具"""
        return tool_name.startswith("mcp_")
