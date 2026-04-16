/**
 * CoreAgent - SmartHomeClaw 核心 Agent 引擎
 * 基于 guiguihao/SmartHomeClaw/src/core/agent.py 设计
 * 支持工具调用循环、记忆管理、定时任务、心跳巡检
 */
import fs from 'fs/promises';
import path from 'path';
import OpenAI from 'openai';
import dotenv from 'dotenv';

dotenv.config();

const BASE_SYSTEM_PROMPT = `你是一个极其聪明、动作果断的 SmartHomeClaw 智能家居 AI 管家，名叫 "{name}"。
你驻留在用户的家庭服务器中，通过各种工具感知并控制物理世界。

### 行动准则
1. **探测优先**：如果用户的意图涉及查询，严禁反向询问用户。你拥有工具，应该立即调用工具自助查询。
2. **拒绝平庸**：不要做只会复读的机器人。你的价值在于通过后台操作减少用户的认知负担。
3. **静默多步执行**：如果一个任务需要多步，请在一次回复前连续调用所有必要工具，直接汇报最终结果。
4. **歧义处理**：只有当工具返回依然存在无法确定的多项选择时，才礼貌地请用户选择。

### 你的能力
1. 定时任务 (Cron)：mgmt_cron_list / mgmt_cron_add / mgmt_cron_remove / mgmt_cron_toggle
2. 心跳巡检 (Heartbeat)：mgmt_heartbeat_get / mgmt_heartbeat_set
3. 长期记忆 (Memory)：memory_* 工具

### 当前时间
{time}

请开始你的服务。少说话，多干活。`;

class CoreAgent {
  constructor(modelConfig = {}) {
    this.name = modelConfig.name || 'SmartHomeClaw';
    this.maxContextTurns = modelConfig.maxContextTurns || 20;
    this.maxToolIterations = modelConfig.maxToolIterations || 10;
    this.sessionDir = modelConfig.sessionDir || './sessions';
    console.log(`[CoreAgent] model=${modelConfig.model}, baseUrl=${modelConfig.baseUrl}`);
    
    this.client = new OpenAI({
      baseURL: modelConfig.baseUrl,
      apiKey: modelConfig.apiKey,
      timeout: modelConfig.timeout || 60000,
    });
    this.model = modelConfig.model;

    this._sessions = {};
    this._memoryService = null;
    this._scheduler = null;
    this._heartbeat = null;
    this._onCronTaskExecute = null;
  }

  setMemory(memoryService) {
    this._memoryService = memoryService;
  }

  setScheduler(scheduler) {
    this._scheduler = scheduler;
  }

  setHeartbeat(heartbeat) {
    this._heartbeat = heartbeat;
  }

  /**
   * 设置 Cron 任务触发时的执行回调
   * @param {Function} handler - 接收 (description, taskConfig) 的异步函数
   */
  setOnCronTaskExecute(handler) {
    this._onCronTaskExecute = handler;
  }

  async init() {
    await fs.mkdir(this.sessionDir, { recursive: true });
  }

  /**
   * 获取记忆上下文（异步）
   */
  async _loadMemoryContext() {
    if (!this._memoryService) return '';
    try {
      const all = await this._memoryService.getAll();
      const profile = all.userProfile || '';
      const habits = all.habits || '';
      const facts = all.facts || '';
      return `用户偏好：${profile || '无'}\n习惯记录：${habits || '无'}\n家居事实：${facts || '无'}`;
    } catch {
      return '';
    }
  }

  _buildSystemPrompt() {
    return BASE_SYSTEM_PROMPT
      .replace('{name}', this.name)
      .replace('{time}', new Date().toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }));
  }

  _getAllTools() {
    const tools = [];

    if (this._memoryService) {
      tools.push(
        {
          type: 'function',
          function: {
            name: 'memory_get_user_profile',
            description: '获取用户偏好设置',
            parameters: { type: 'object', properties: {}, required: [] },
          },
        },
        {
          type: 'function',
          function: {
            name: 'memory_update_user_profile',
            description: '更新用户偏好设置',
            parameters: {
              type: 'object',
              properties: {
                content: { type: 'string', description: '新的偏好内容' },
              },
              required: ['content'],
            },
          },
        },
        {
          type: 'function',
          function: {
            name: 'memory_get_habits',
            description: '获取用户习惯记录',
            parameters: { type: 'object', properties: {}, required: [] },
          },
        },
        {
          type: 'function',
          function: {
            name: 'memory_update_habits',
            description: '更新用户习惯记录',
            parameters: {
              type: 'object',
              properties: {
                content: { type: 'string', description: '新的习惯内容' },
              },
              required: ['content'],
            },
          },
        },
        {
          type: 'function',
          function: {
            name: 'memory_get_facts',
            description: '获取重要事实记录',
            parameters: { type: 'object', properties: {}, required: [] },
          },
        },
        {
          type: 'function',
          function: {
            name: 'memory_update_facts',
            description: '更新重要事实记录',
            parameters: {
              type: 'object',
              properties: {
                content: { type: 'string', description: '新的事实内容' },
              },
              required: ['content'],
            },
          },
        }
      );
    }

    if (this._scheduler) {
      tools.push(
        {
          type: 'function',
          function: {
            name: 'mgmt_cron_list',
            description: '列出当前所有定时任务',
            parameters: { type: 'object', properties: {}, required: [] },
          },
        },
        {
          type: 'function',
          function: {
            name: 'mgmt_cron_add',
            description: '添加一个新的定时任务',
            parameters: {
              type: 'object',
              properties: {
                task_id: { type: 'string', description: '唯一英文 ID' },
                name: { type: 'string', description: '任务名称' },
                cron: { type: 'string', description: '5段 cron 表达式' },
                description: { type: 'string', description: '任务指令' },
              },
              required: ['task_id', 'name', 'cron', 'description'],
            },
          },
        },
        {
          type: 'function',
          function: {
            name: 'mgmt_cron_remove',
            description: '删除一个定时任务',
            parameters: {
              type: 'object',
              properties: {
                task_id: { type: 'string', description: '任务 ID' },
              },
              required: ['task_id'],
            },
          },
        },
        {
          type: 'function',
          function: {
            name: 'mgmt_cron_toggle',
            description: '启用或禁用一个定时任务',
            parameters: {
              type: 'object',
              properties: {
                task_id: { type: 'string', description: '任务 ID' },
                enabled: { type: 'boolean', description: 'true=启用，false=禁用' },
              },
              required: ['task_id', 'enabled'],
            },
          },
        }
      );
    }

    if (this._heartbeat) {
      tools.push(
        {
          type: 'function',
          function: {
            name: 'mgmt_heartbeat_get',
            description: '读取当前心跳巡检的任务指令内容',
            parameters: { type: 'object', properties: {}, required: [] },
          },
        },
        {
          type: 'function',
          function: {
            name: 'mgmt_heartbeat_set',
            description: '修改心跳巡检任务的指令内容',
            parameters: {
              type: 'object',
              properties: {
                content: { type: 'string', description: '新的心跳任务指令' },
              },
              required: ['content'],
            },
          },
        }
      );
    }

    return tools;
  }

  /**
   * 处理工具调用（异步）
   */
  async _handleToolCall(toolName, args = {}) {
    if (toolName.startsWith('memory_')) {
      return await this._handleMemoryTool(toolName, args);
    } else if (toolName.startsWith('mgmt_')) {
      return this._handleManagementTool(toolName, args);
    }
    return `未知工具: ${toolName}`;
  }

  /**
   * 处理记忆工具调用（异步，通过 MemoryService 的正式方法读写）
   */
  async _handleMemoryTool(toolName, args = {}) {
    if (!this._memoryService) return '记忆服务未配置';

    try {
      switch (toolName) {
        case 'memory_get_user_profile':
          return await this._memoryService.loadUserProfile();
        case 'memory_update_user_profile':
          await this._memoryService.updateUserProfile(args.content);
          return '已更新用户偏好';
        case 'memory_get_habits':
          return await this._memoryService.loadHabits();
        case 'memory_update_habits':
          await this._memoryService.updateHabits(args.content);
          return '已更新习惯记录';
        case 'memory_get_facts':
          return await this._memoryService.loadFacts();
        case 'memory_update_facts':
          await this._memoryService.updateFacts(args.content);
          return '已更新事实记录';
        default:
          return `未知记忆工具: ${toolName}`;
      }
    } catch (e) {
      return `错误: ${e.message}`;
    }
  }

  /**
   * 处理管理工具调用
   */
  _handleManagementTool(toolName, args = {}) {
    switch (toolName) {
      case 'mgmt_cron_list':
        if (!this._scheduler) return '调度器未配置';
        const tasks = this._scheduler.listTasks() || [];
        if (!tasks.length) return '无定时任务';
        return tasks.map(t => `[${t.id}] ${t.name} (${t.cron})`).join('\n');

      case 'mgmt_cron_add':
        if (!this._scheduler) return '调度器未配置';
        const taskConfig = {
          id: args.task_id,
          name: args.name,
          cron: args.cron,
          prompt: args.description,
          enabled: true,
        };
        this._scheduler.register(args.task_id, args.cron, async () => {
          if (this._onCronTaskExecute) {
            await this._onCronTaskExecute(args.description, taskConfig);
          } else {
            console.warn(`[CoreAgent] Cron task ${args.task_id} fired but no executor set`);
          }
        }, { name: args.name });
        return `已添加定时任务: ${args.task_id}`;

      case 'mgmt_cron_remove':
        if (!this._scheduler) return '调度器未配置';
        this._scheduler.unregister(args.task_id);
        return `已删除定时任务: ${args.task_id}`;

      case 'mgmt_cron_toggle':
        if (!this._scheduler) return '调度器未配置';
        if (args.enabled) {
          const ok = this._scheduler.enable(args.task_id);
          return ok ? `已启用任务: ${args.task_id}` : `任务 ${args.task_id} 不存在，无法启用`;
        } else {
          const ok = this._scheduler.disable(args.task_id);
          return ok ? `已禁用任务: ${args.task_id}` : `任务 ${args.task_id} 不存在，无法禁用`;
        }

      case 'mgmt_heartbeat_get':
        if (!this._heartbeat) return '心跳未配置';
        return this._heartbeat.getTaskContent() || '';

      case 'mgmt_heartbeat_set':
        if (!this._heartbeat) return '心跳未配置';
        this._heartbeat.setTaskContent(args.content);
        return '已更新心跳任务';

      default:
        return `未知管理工具: ${toolName}`;
    }
  }

  /**
   * 截断历史消息，保留完整的 tool_call ↔ tool_result 配对
   * @param {Array} history - 原始历史
   * @param {number} maxLen - 最大保留条数
   * @returns {Array} 截断后的历史
   */
  _trimHistory(history, maxLen) {
    if (history.length <= maxLen) return history;

    let trimmed = history.slice(history.length - maxLen);

    // 检查开头是否有孤立的 tool_result（对应的 tool_call 被截掉了）
    const orphanStart = trimmed.findIndex(
      (msg, idx) => msg.role === 'tool' && idx === 0
    );
    if (orphanStart !== -1 && orphanStart === 0) {
      // 跳过所有连续的 orphan tool_result
      let skip = 0;
      while (skip < trimmed.length && trimmed[skip].role === 'tool') {
        skip++;
      }
      trimmed = trimmed.slice(skip);
    }

    // 同样检查开头是否有 tool_calls 但缺少后续 tool_result 的 assistant 消息
    while (trimmed.length > 0) {
      const first = trimmed[0];
      if (first.role === 'assistant' && first.tool_calls && first.tool_calls.length > 0) {
        // 检查紧跟的消息是否是对应第一个 tool_call 的 tool_result
        if (trimmed.length > 1 && trimmed[1].role === 'tool') {
          break; // 配对完整，保留
        }
        // 缺少 tool_result，移除这条 assistant 消息
        trimmed = trimmed.slice(1);
      } else {
        break;
      }
    }

    return trimmed;
  }

  _normalizeMessages(history) {
    const messages = [];
    for (const msg of history) {
      if (msg.tool_calls) {
        messages.push({
          role: msg.role,
          content: msg.content || null,
          tool_calls: msg.tool_calls,
        });
      } else if (msg.tool_call_id) {
        messages.push({
          role: 'tool',
          tool_call_id: msg.tool_call_id,
          content: msg.content,
        });
      } else {
        messages.push({
          role: msg.role,
          content: msg.content || '',
        });
      }
    }
    return messages;
  }

  async _saveSession(sessionId, history) {
    const sessionPath = path.join(this.sessionDir, `${sessionId}.json`);
    try {
      await fs.writeFile(sessionPath, JSON.stringify(history, null, 2), 'utf-8');
    } catch (e) {
      console.error(`[CoreAgent] 保存会话失败: ${e.message}`);
    }
  }

  async _loadSession(sessionId) {
    const sessionPath = path.join(this.sessionDir, `${sessionId}.json`);
    try {
      const data = await fs.readFile(sessionPath, 'utf-8');
      return JSON.parse(data);
    } catch {
      return [];
    }
  }

  /**
   * 核心对话方法
   * @param {string} prompt - 用户消息
   * @param {object} options - 可选参数
   * @returns {object} AI 响应
   */
  async decide(prompt, options = {}) {
    const sessionId = options.sessionId || 'default';

    if (!this._sessions[sessionId]) {
      this._sessions[sessionId] = await this._loadSession(sessionId);
    }

    const history = this._sessions[sessionId];
    history.push({ role: 'user', content: prompt });

    const maxLen = this.maxContextTurns * 2;
    this._sessions[sessionId] = this._trimHistory(history, maxLen);
    const trimmedHistory = this._sessions[sessionId];

    let systemPrompt = this._buildSystemPrompt();
    let ctx = await this._loadMemoryContext();
    if (options.appendSystemPrompt) {
      ctx = ctx ? `${ctx}\n${options.appendSystemPrompt}` : options.appendSystemPrompt;
    }
    if (ctx) {
      systemPrompt += `\n\n## 上下文\n${ctx}`;
    }

    const messages = [{ role: 'system', content: systemPrompt }];
    messages.push(...this._normalizeMessages(trimmedHistory));

    const tools = this._getAllTools();
    let finalResponse = '';

    for (let i = 0; i < this.maxToolIterations; i++) {
      const response = await this.client.chat.completions.create({
        model: this.model,
        messages: messages,
        tools: tools.length > 0 ? tools : undefined,
        temperature: 0.7,
      });

      const choice = response.choices[0];
      const msgToStore = {
        role: choice.message.role,
        content: choice.message.content,
      };

      if (choice.message.tool_calls) {
        msgToStore.tool_calls = choice.message.tool_calls.map(tc => ({
          id: tc.id,
          type: tc.type,
          function: {
            name: tc.function.name,
            arguments: tc.function.arguments,
          },
        }));
      }

      trimmedHistory.push(msgToStore);
      messages.push(msgToStore);

      if (msgToStore.tool_calls && msgToStore.tool_calls.length > 0) {
        for (const tc of msgToStore.tool_calls) {
          let args = {};
          try {
            args = JSON.parse(tc.function.arguments);
          } catch (e) {
            console.warn(`[CoreAgent] 工具参数解析失败: ${tc.function.name}, raw: ${tc.function.arguments}`);
          }

          const result = await this._handleToolCall(tc.function.name, args);
          console.log(`[CoreAgent] 工具: ${tc.function.name} → ${String(result).substring(0, 80)}`);

          const toolResult = { role: 'tool', tool_call_id: tc.id, content: String(result) };
          trimmedHistory.push(toolResult);
          messages.push(toolResult);
        }
        continue;
      } else {
        finalResponse = msgToStore.content || '';
        break;
      }
    }

    await this._saveSession(sessionId, trimmedHistory);

    return this.parseOutput(finalResponse);
  }

  /**
   * 持续对话
   * @param {string} sessionId - 会话 ID
   * @param {string} prompt - 后续消息
   * @returns {object} AI 响应
   */
  async continue(sessionId, prompt) {
    return this.decide(prompt, { sessionId });
  }

  /**
   * 解析输出 — 能 JSON.parse 就解析，否则直接当文本返回
   * @param {string} output - 原始输出
   * @returns {object} 解析后对象
   */
  parseOutput(output) {
    if (!output) return { response: '无响应' };

    try {
      return JSON.parse(output);
    } catch {
      return { response: output };
    }
  }

  /**
   * 清除会话历史
   * @param {string} sessionId - 会话 ID
   */
  async clearHistory(sessionId = 'default') {
    if (this._sessions[sessionId]) {
      this._sessions[sessionId] = [];
    }
    const sessionPath = path.join(this.sessionDir, `${sessionId}.json`);
    await fs.unlink(sessionPath).catch(() => {});
  }
}

export default CoreAgent;