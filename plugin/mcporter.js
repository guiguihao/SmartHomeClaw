import { createRuntime, createServerProxy } from 'mcporter';

/**
 * MCPorter 插件 — MCP Server 客户端
 * 通过 mcporter 连接外部 MCP Server，动态发现工具并注入 CoreAgent
 *
 * 工作流程：
 * 1. createRuntime() 发现并连接配置中的 MCP Server
 * 2. listTools() 获取所有 server 的工具列表
 * 3. 将工具转换为 OpenAI function-calling 格式，注入 CoreAgent._getAllTools()
 * 4. CoreAgent 工具调用时，通过 mcp_{server}_{tool} 前缀路由到 mcporter
 * 5. callTool() / createServerProxy() 执行实际调用
 */
class MCPorterService {
  constructor(config, agent) {
    this.agent = agent;
    this.enabled = config.enabled !== false;
    this.configPath = config.config_path || './config/mcporter.json';
    this.rootDir = config.root_dir || process.cwd();
    this.timeout = config.timeout || 30000;

    this.runtime = null;
    this.serverProxies = {};  // serverName → ServerProxy
    this.mcpTools = [];       // OpenAI function-calling 格式的工具列表
    this.toolMap = {};        // toolPrefix → { server, toolName, schema }
  }

  /**
   * 启动 MCP 服务 — 连接所有配置的 MCP Server
   */
  async start() {
    if (!this.enabled) {
      console.log('[MCPorter] Disabled, skipping...');
      return;
    }

    console.log('[MCPorter] Starting...');

    try {
      // 1. 创建 runtime（自动发现配置中的 MCP Server）
      this.runtime = await createRuntime({
        configPath: this.configPath,
        rootDir: this.rootDir,
      });

      // 2. 遍历所有 server，获取工具列表
      const servers = this.runtime.getServerNames();
      console.log(`[MCPorter] Discovered ${servers.length} servers: ${servers.join(', ')}`);

      for (const serverName of servers) {
        try {
          const tools = await this.runtime.listTools(serverName);
          console.log(`[MCPorter] ${serverName}: ${tools.length} tools`);

          // 创建 server proxy（友好调用接口）
          this.serverProxies[serverName] = createServerProxy(this.runtime, serverName);

          // 3. 将 MCP 工具转换为 OpenAI function-calling 格式
          for (const tool of tools) {
            const toolPrefix = `mcp_${serverName}_${tool.name}`;
            const openaiTool = this._convertToOpenAITool(toolPrefix, tool);
            this.mcpTools.push(openaiTool);
            this.toolMap[toolPrefix] = {
              server: serverName,
              toolName: tool.name,
              schema: tool,
            };
          }
        } catch (error) {
          console.warn(`[MCPorter] Failed to connect ${serverName}: ${error.message}`);
        }
      }

      // 4. 注入工具到 CoreAgent
      if (this.agent && this.mcpTools.length > 0) {
        this.agent.setMCPTools(this.mcpTools, this.toolMap, this);
        console.log(`[MCPorter] ✅ Injected ${this.mcpTools.length} MCP tools into CoreAgent`);
      }

      console.log(`[MCPorter] ✅ Started successfully`);
    } catch (error) {
      console.error(`[MCPorter] Failed to start: ${error.message}`);
    }
  }

  /**
   * 停止 MCP 服务
   */
  async stop() {
    console.log('[MCPorter] Stopping...');
    if (this.runtime) {
      try {
        await this.runtime.close();
      } catch (e) {
        console.warn(`[MCPorter] Runtime close error: ${e.message}`);
      }
      this.runtime = null;
    }
    console.log('[MCPorter] Stopped');
  }

  /**
   * 执行 MCP 工具调用
   * @param {string} toolPrefix - 如 "mcp_context7_resolve-library-id"
   * @param {object} args - 工具参数
   * @returns {string} 工具结果
   */
  async callTool(toolPrefix, args = {}) {
    const mapping = this.toolMap[toolPrefix];
    if (!mapping) {
      return `未知 MCP 工具: ${toolPrefix}`;
    }

    const { server, toolName } = mapping;

    try {
      const proxy = this.serverProxies[server];
      if (!proxy) {
        return `MCP Server ${server} 未连接`;
      }

      // 使用 camelCase 方法名调用（mcporter 自动转换）
      // 但也支持直接通过 runtime.callTool 调用
      const result = await this.runtime.callTool(server, toolName, { args });

      // CallResult 有 .text() / .json() / .markdown() 等方法
      if (result && typeof result.text === 'function') {
        return result.text();
      }

      // fallback：直接返回 JSON 字符串
      return JSON.stringify(result, null, 2);
    } catch (error) {
      console.error(`[MCPorter] Call ${toolPrefix} error: ${error.message}`);
      return `MCP 工具调用失败: ${error.message}`;
    }
  }

  /**
   * 将 MCP 工具 schema 转换为 OpenAI function-calling 格式
   * @param {string} toolPrefix - 工具前缀名
   * @param {object} tool - MCP 工具对象 { name, description, inputSchema }
   * @returns {object} OpenAI tool definition
   */
  _convertToOpenAITool(toolPrefix, tool) {
    // MCP inputSchema → OpenAI parameters
    const parameters = tool.inputSchema || { type: 'object', properties: {}, required: [] };

    return {
      type: 'function',
      function: {
        name: toolPrefix,
        description: `[MCP:${tool.name}] ${tool.description || '无描述'}`,
        parameters: parameters,
      },
    };
  }

  /**
   * 获取已注入的工具列表
   */
  getInjectedTools() {
    return this.mcpTools;
  }

  /**
   * 获取工具映射
   */
  getToolMap() {
    return this.toolMap;
  }
}

export default MCPorterService;