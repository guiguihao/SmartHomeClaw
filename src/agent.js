import fs from 'fs/promises';
import yaml from 'yaml';
import dotenv from 'dotenv';
import QwenAgent from './services/qwen-agent.js';
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
    this.qwen = null;
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
    
    // 3. 初始化 Qwen Agent
    this.qwen = new QwenAgent(this.config.qwen);
    
    // 4. 初始化调度器
    this.scheduler = new Scheduler();
    
    // 5. 初始化心跳
    this.heartbeat = new Heartbeat(this.qwen, this.config.heartbeat);
    
    // 6. 初始化飞书服务
    if (this.config.plugins?.feishu?.enabled) {
      this.feishu = new FeishuService(this.config.plugins.feishu, this.qwen);
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
      
      // 获取记忆上下文
      const memoryContext = await this.memory.getAll();
      
      // 构建 System Prompt
      const systemPrompt = `
你是 SmartHomeClaw 智能家居 AI 助手。
你有以下能力：
1. 控制智能家居设备 (通过 MCP)
2. 学习用户习惯
3. 自主决策优化居住环境
4. 记录和更新记忆

规则：
- 优先参考 memory/ 中的用户偏好
- 发现新习惯时自动记录到 HABITS.md
- 保持克制，只在必要时采取行动
- 通过 MCP Tools 控制设备
`.trim();

      // AI 决策
      const memoryContextText = `用户偏好：${memoryContext.userProfile || '无'}
习惯记录：${memoryContext.habits || '无'}
家居信息：${memoryContext.facts || '无'}`;

      const decision = await this.qwen.decide(prompt, {
        systemPrompt,
        appendSystemPrompt: memoryContextText,
        ...options,
      });

      console.log('[Agent] Decision:', decision);
      
      // 记录决策结果
      // 注意：AI 会通过 MCP 自动执行设备控制，无需手动处理
      
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
