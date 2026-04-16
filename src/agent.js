import fs from 'fs/promises';
import yaml from 'yaml';
import dotenv from 'dotenv';
import CoreAgent from './services/coreagent.js';
import Scheduler from './services/scheduler.js';
import Heartbeat from './services/heartbeat.js';
import MemoryService from './services/memory.js';
import FeishuService from '../plugin/feishu.js';

// 加载环境变量
dotenv.config();

/**
 * SmartHomeClaw Agent 主入口
 * 基于 Qwen Code 无头模式驱动的智能家居 AI Agent
 */
class SmartHomeAgent {
  constructor() {
    this.config = null;
    this.agent = null;
    this.scheduler = null;
    this.heartbeat = null;
    this.memory = null;
    this.feishu = null;
  }

  /**
   * 初始化 Agent
   */
  async init() {
    console.log('[Agent] Initializing SmartHomeClaw...');
    
    // 1. 加载配置
    await this.loadConfig();
    
    // 2. 初始化记忆服务
    this.memory = new MemoryService(this.config.memory);
    await this.memory.init();

    // 3. 初始化 CoreAgent - 使用配置中的模型
    const modelConfig = this._buildModelConfig();
    this.agent = new CoreAgent(modelConfig);
    this.agent.setMemory(this.memory);
    await this.agent.init();

    // 4. 初始化调度器
    this.scheduler = new Scheduler();

    // 5. 初始化心跳
    this.heartbeat = new Heartbeat(this.agent, this.config.heartbeat);

    // 6. 初始化飞书服务
    if (this.config.plugins?.feishu?.enabled) {
      this.feishu = new FeishuService(this.config.plugins.feishu, this.agent);
    }
    
    console.log('[Agent] Initialized');
  }

  /**
   * 启动 Agent
   */
  async start() {
    console.log('[Agent] Starting SmartHomeClaw...');
    
    // 1. 注册 Cron 任务
    await this.registerCronTasks();
    
    // 2. 启动心跳
    this.heartbeat.start();
    
    // 3. 启动调度器
    this.scheduler.startAll();
    
    // 4. 启动飞书服务
    if (this.feishu) {
      await this.feishu.start();
    }
    
    console.log('[Agent] SmartHomeClaw is running...');
    console.log('[Agent] Press Ctrl+C to stop');
  }

  /**
   * 停止 Agent
   */
  async stop() {
    console.log('[Agent] Stopping SmartHomeClaw...');
    
    this.heartbeat.stop();
    this.scheduler.stopAll();
    
    // 停止飞书服务
    if (this.feishu) {
      await this.feishu.stop();
    }
    
    console.log('[Agent] Stopped');
  }

  /**
   * 加载配置文件
   */
  async loadConfig() {
    try {
      const [agentConfig, heartbeatConfig, cronConfig, pluginConfig] = await Promise.all([
        this.loadYaml('./config/agent.yaml'),
        this.loadYaml('./config/heartbeat.yaml'),
        this.loadYaml('./config/cron.yaml'),
        this.loadYaml('./config/plugin.yaml'),
      ]);

      this.config = {
        agent: agentConfig.agent || {},
        qwen: agentConfig.qwen || {},
        mcp: agentConfig.mcp || {},
        memory: agentConfig.memory || {},
        models: agentConfig.models || {},
        heartbeat: heartbeatConfig.heartbeat || {},
        cron: cronConfig.cron || {},
        plugins: pluginConfig.plugins || {},
      };

      console.log('[Agent] Config loaded');
    } catch (error) {
      console.error('[Agent] Config load error:', error.message);
      throw error;
    }
  }

  /**
   * 从配置中构建模型配置
   *
   * default 格式为 "provider/modelId"，其中 provider 是配置中的顶级键，
   * modelId 是该 provider 下某个模型条目的 id 字段。
   * 例如: "navida/openai/gpt-oss-120b" → provider=navida, modelId=openai/gpt-oss-120b
   */
  _buildModelConfig() {
    const models = this.config.models || {};
    const defaultModelId = models.default;

    if (!defaultModelId) {
      throw new Error('No default model configured');
    }

    // 从 default 中分离 provider 前缀与实际模型 ID
    const slashIndex = defaultModelId.indexOf('/');
    let providerName;
    let modelId;

    if (slashIndex !== -1) {
      providerName = defaultModelId.slice(0, slashIndex);
      modelId = defaultModelId.slice(slashIndex + 1);
    } else {
      // 没有 provider 前缀，遍历所有 provider 查找
      providerName = null;
      modelId = defaultModelId;
    }

    let modelConfig = null;

    if (providerName) {
      // 在指定 provider 中查找
      const providerModels = models[providerName];
      if (providerModels && Array.isArray(providerModels)) {
        modelConfig = providerModels.find(m => m.id === modelId || m.id === defaultModelId);
      }
    }

    // 若未找到，遍历所有 provider
    if (!modelConfig) {
      for (const [key, providerModels] of Object.entries(models)) {
        if (key === 'default' || !Array.isArray(providerModels)) continue;
        modelConfig = providerModels.find(m => m.id === modelId || m.id === defaultModelId);
        if (modelConfig) break;
      }
    }

    if (!modelConfig) {
      throw new Error(`Model ${defaultModelId} not found in config`);
    }

    console.log(`[Agent] Using model: ${modelConfig.id}`);

    return {
      name: 'SmartHomeClaw',
      model: modelConfig.id,
      baseUrl: modelConfig.baseUrl,
      apiKey: modelConfig.apiKey,
    };
  }

  /**
   * 注册定时任务
   */
  async registerCronTasks() {
    const tasks = this.config.cron.tasks || [];
    
    this.scheduler.registerTasks(tasks, async (prompt, taskConfig) => {
      console.log(`[Agent] Cron triggered: ${taskConfig.name}`);
      await this.thinkAndAct(prompt);
    });
  }

  /**
   * AI 思考并执行
   * @param {string} prompt - 问题/指令
   * @param {object} options - 可选参数
   * @returns {object} 决策结果
   */
  async thinkAndAct(prompt, options = {}) {
    try {
      console.log(`[Agent] Thinking: ${prompt}`);

      if (!this.agent) {
        throw new Error('Agent not initialized');
      }

      const decision = await this.agent.decide(prompt, options);
      console.log('[Agent] Decision:', decision);

      return decision;
    } catch (error) {
      console.error('[Agent] ThinkAndAct error:', error.message);
      throw error;
    }
  }

  /**
   * 加载 YAML 文件
   * @param {string} filePath - 文件路径
   * @returns {object} 配置对象
   */
  async loadYaml(filePath) {
    try {
      let content = await fs.readFile(filePath, 'utf-8');
      
      // 替换环境变量 ${VAR} 或 $VAR
      content = content.replace(/\$\{(\w+)\}/g, (match, key) => {
        return process.env[key] || match;
      }).replace(/\$(\w+)/g, (match, key) => {
        return process.env[key] || match;
      });
      
      return yaml.parse(content) || {};
    } catch (error) {
      if (error.code === 'ENOENT') {
        console.warn(`[Agent] Config file not found: ${filePath}`);
        return {};
      }
      throw error;
    }
  }
}

// 启动入口
const agent = new SmartHomeAgent();

// 优雅退出处理
process.on('SIGINT', async () => {
  await agent.stop();
  process.exit(0);
});

process.on('SIGTERM', async () => {
  await agent.stop();
  process.exit(0);
});

// 启动
agent.init()
  .then(() => agent.start())
  .catch((error) => {
    console.error('[Agent] Failed to start:', error.message);
    process.exit(1);
  });

export default SmartHomeAgent;
