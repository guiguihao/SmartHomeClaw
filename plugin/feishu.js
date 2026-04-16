import * as lark from '@larksuiteoapi/node-sdk';

/**
 * 飞书 (Feishu/Lark) 插件
 * 基于官方 SDK 实现 WebSocket 长连接实时监听消息与 AI 自动回复
 * 支持流式回复：先发交互式卡片占位 → 逐 chunk patch 更新卡片 → 打字机效果
 */

/**
 * 构建飞书交互式卡片 JSON
 * @param {string} text - 显示文本
 * @returns {string} JSON 字符串
 */
function buildCardContent(text) {
  return JSON.stringify({
    config: { wide_screen_mode: true },
    header: {
      title: { tag: 'plain_text', content: '🏠 SmartHomeClaw' },
      template: 'blue',
    },
    elements: [
      {
        tag: 'div',
        text: { tag: 'lark_md', content: text },
      },
    ],
  });
}

/**
 * 构建纯文本消息 JSON
 */
function buildTextContent(text) {
  return JSON.stringify({ text });
}

class FeishuService {
  constructor(config, agent) {
    this.appId = config.app_id || process.env.FEISHU_APP_ID;
    this.appSecret = config.app_secret || process.env.FEISHU_APP_SECRET;
    this.enableListener = config.enable_listener !== false;
    this.autoReply = config.auto_reply !== false;
    this.streamReply = config.stream_reply !== false;
    this.agent = agent;

    // 流式回复参数
    this.streamPatchInterval = config.stream_patch_interval || 500; // patch 间隔(ms)

    // chatId → sessionId 映射（支持 /new 切换新会话）
    this._chatSessionMap = {};

    // 消息去重：避免飞书重复投递相同消息
    // key: `${chatId}_${messageId}` 或 `${chatId}_${hash(content)}`
    this._processedMessageSet = new Set();
    this._dedupCleanInterval = null;

    this.client = null;      // HTTP API 客户端
    this.wsClient = null;    // WebSocket 长连接客户端
    this.eventDispatcher = null;
  }

  async start() {
    if (!this.appId || !this.appSecret) {
      console.warn('[Feishu] App ID or Secret not configured, skipping...');
      return;
    }

    if (!this.enableListener) {
      console.log('[Feishu] Listener disabled, skipping...');
      return;
    }

    console.log('[Feishu] Starting...');

    try {
      // 确保之前没有启动
      if (this.client || this.wsClient) {
        console.warn('[Feishu] Already initialized, stopping first...');
        await this.stop();
      }

      // 1. 初始化 HTTP 客户端 (用于主动调用 API)
      this.client = new lark.Client({
        appId: this.appId,
        appSecret: this.appSecret,
      });

      // 2. 初始化 WebSocket 长连接客户端
      this.wsClient = new lark.WSClient({
        appId: this.appId,
        appSecret: this.appSecret,
        loggerLevel: lark.LoggerLevel.info,
      });

      // 3. 配置事件监听器
      this.setupEventDispatcher();

      // 4. 启动长连接
      this.wsClient.start({ eventDispatcher: this.eventDispatcher });

      // 5. 启动去重缓存清理定时器（每5分钟清理1分钟前的记录）
      this._startDedupCleaner();

      console.log('[Feishu] ✅ Started successfully, listening for messages...');
    } catch (error) {
      console.error('[Feishu] Failed to start:', error.message);
      setTimeout(() => this.start(), 5000);
    }
  }

  async stop() {
    console.log('[Feishu] Stopping...');

    if (this._dedupCleanInterval) {
      clearInterval(this._dedupCleanInterval);
      this._dedupCleanInterval = null;
    }
    this._processedMessageSet.clear();

    if (this.wsClient) {
      if (typeof this.wsClient.stop === 'function') {
        this.wsClient.stop();
      } else if (typeof this.wsClient.disconnect === 'function') {
        this.wsClient.disconnect();
      }
      this.wsClient = null;
    }

    this.client = null;
    this.eventDispatcher = null;
    console.log('[Feishu] Stopped');
  }

  /**
   * 去重辅助方法
   */
  _startDedupCleaner() {
    if (this._dedupCleanInterval) clearInterval(this._dedupCleanInterval);
    this._dedupCleanInterval = setInterval(() => {
      // 每5分钟清理一次，但实际我们的 Set 会持续累积
      // 如果消息量很大，可以改为使用 Map 记录时间戳，清理超过5分钟的
      // 目前先简单实现，只在 Set 过大时清理
      if (this._processedMessageSet.size > 1000) {
        console.log(`[Feishu] Dedup cache too large (${this._processedMessageSet.size}), clearing...`);
        this._processedMessageSet.clear();
      }
    }, 5 * 60 * 1000); // 5分钟
  }

  /**
   * 检查消息是否已处理过
   * @param {string} chatId - 聊天 ID
   * @param {object} msgData - 消息数据 (包含 message_id, create_time 等)
   * @param {string} content - 消息内容
   * @returns {boolean} true 表示已处理过，应该跳过
   */
  _isDuplicateMessage(chatId, msgData, content) {
    // 优先使用 message_id
    const messageId = msgData.message_id || msgData.msg_id;
    let key = `${chatId}_${messageId}`;

    // 如果无 message_id，使用 chatId+内容哈希（简易）和时间窗口
    if (!messageId) {
      const hash = this._simpleHash(content);
      key = `${chatId}_${hash}`;
    }

    if (this._processedMessageSet.has(key)) {
      console.log(`[Feishu] Duplicate message detected (key=${key}), skipping...`);
      return true;
    }

    // 标记为已处理
    this._processedMessageSet.add(key);
    return false;
  }

  /**
   * 简易字符串哈希（用于去重）
   */
  _simpleHash(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      const chr = str.charCodeAt(i);
      hash = ((hash << 5) - hash) + chr;
      hash |= 0; // 转为32位整数
    }
    return Math.abs(hash).toString(16);
  }

  /**
   * 配置事件分发器
   */
  setupEventDispatcher() {
    this.eventDispatcher = new lark.EventDispatcher({}).register({
      'im.message.receive_v1': async (data) => {
        await this.handleMessage(data);
      },
    });
  }

  /**
   * 处理收到的消息
   */
  async handleMessage(data) {
    try {
      const msgData = data.message;
      const chatId = msgData.chat_id || msgData.chatId;

      const sender = msgData.sender || {};
      const senderId = sender.sender_id?.open_id ||
                       sender.open_id ||
                       sender.user_id ||
                       'unknown';

      const content = this.parseMessageContent(msgData);

      console.log(`[Feishu] 📨 Message from ${senderId}: ${content}`);
      console.log(`[Feishu] Chat ID: ${chatId}`);

      // 忽略机器人自己发的消息
      if (senderId && senderId === this.appId) {
        return;
      }

      // 去重检查：避免重复处理相同消息
      if (this._isDuplicateMessage(chatId, msgData, content)) {
        console.log(`[Feishu] Skip duplicate message from ${senderId}: ${content}`);
        return;
      }

      if (this.autoReply) {
        await this.replyWithAI(chatId, content, senderId);
      }
    } catch (error) {
      console.error('[Feishu] Handle message error:', error.message);
    }
  }

  /**
   * 解析消息内容
   */
  parseMessageContent(msgData) {
    try {
      const content = JSON.parse(msgData.content || '{}');
      return content.text || msgData.content || '';
    } catch {
      return msgData.content || '';
    }
  }

  /**
   * 获取 chatId 对应的 sessionId
   */
  _getSessionId(chatId) {
    if (!this._chatSessionMap[chatId]) {
      this._chatSessionMap[chatId] = `feishu_${chatId}`;
    }
    return this._chatSessionMap[chatId];
  }

  /**
   * AI 自动回复 — 根据 stream 配置选择流式或一次性回复
   */
  async replyWithAI(chatId, userMessage, senderId) {
    const useStream = this.streamReply && this.agent?.stream;
    const sessionId = this._getSessionId(chatId);

    try {
      console.log(`[Feishu] 🤖 AI processing (stream=${useStream}): ${userMessage}`);

      if (!this.agent || typeof this.agent.decide !== 'function') {
        await this.sendTextMessage(chatId, 'AI 服务未初始化');
        return;
      }

      if (useStream) {
        await this.replyWithStream(chatId, userMessage, sessionId);
      } else {
        await this.replyWithNormal(chatId, userMessage, sessionId);
      }
    } catch (error) {
      console.error('[Feishu] AI reply failed:', error.message);
      await this.sendTextMessage(chatId, '抱歉，我遇到了一些问题，请稍后再试。');
    }
  }

  /**
   * 一次性回复（非流式） — 使用交互式卡片
   */
  async replyWithNormal(chatId, userMessage, sessionId) {
    const result = await this.agent.decide(userMessage, {
      sessionId,
      appendSystemPrompt: '用户在飞书发送消息，参考用户偏好和习惯记录',
    });

    // /new 指令：更新 chatId → sessionId 映射
    if (result.command === 'new' && result.sessionId) {
      this._chatSessionMap[chatId] = result.sessionId;
    }

    const reply = result.reply || result.response || '收到！';
    await this.sendCardMessage(chatId, reply);
    console.log(`[Feishu] ✅ AI reply sent`);
  }

  /**
   * 流式回复 — 发交互式卡片占位 → 逐 chunk patch 更新卡片 → 打字机效果
   */
  async replyWithStream(chatId, userMessage, sessionId) {
    // 1. 发占位卡片消息，拿到 message_id
    const msgRes = await this.sendCardMessage(chatId, '🤔 思考中...');
    const messageId = msgRes?.data?.message_id;

    if (!messageId) {
      console.warn('[Feishu] Failed to get message_id for stream reply, fallback to normal');
      const result = await this.agent.decide(userMessage, {
        sessionId,
        appendSystemPrompt: '用户在飞书发送消息，参考用户偏好和习惯记录',
      });
      if (result.command === 'new' && result.sessionId) {
        this._chatSessionMap[chatId] = result.sessionId;
      }
      await this.sendCardMessage(chatId, result.reply || result.response || '收到！');
      return;
    }

    // 2. 累积 buffer + 定时 patch 更新飞书卡片
    let buffer = '';
    let patchTimer = null;
    let lastPatchContent = '🤔 思考中...';

    const flushToFeishu = async () => {
      if (buffer === lastPatchContent) return;
      try {
        await this.patchCardMessage(messageId, buffer);
        lastPatchContent = buffer;
      } catch (e) {
        console.warn(`[Feishu] Stream patch error: ${e.message}`);
      }
    };

    patchTimer = setInterval(() => {
      flushToFeishu().catch(e => console.warn(`[Feishu] Patch timer error: ${e.message}`));
    }, this.streamPatchInterval);

    // 3. 调用 CoreAgent.decide，传入 onChunk 回调
    try {
      const result = await this.agent.decide(userMessage, {
        sessionId,
        appendSystemPrompt: '用户在飞书发送消息，参考用户偏好和习惯记录',
        onChunk: (text) => {
          buffer += text;
        },
      });

      // 4. 流结束后停止定时 patch，做最后一次完整更新
      clearInterval(patchTimer);

      const finalContent = result.reply || result.response || buffer || '收到！';
      if (finalContent !== lastPatchContent) {
        await this.patchCardMessage(messageId, finalContent);
      }

      console.log(`[Feishu] ✅ Stream reply completed`);
    } catch (error) {
      clearInterval(patchTimer);
      try {
        await this.patchCardMessage(messageId, buffer || '抱歉，处理过程中遇到了问题。');
      } catch {}
      throw error;
    }
  }

  /**
   * 发送纯文本消息
   */
  async sendTextMessage(chatId, text) {
    try {
      const res = await this.client.im.message.create({
        params: { receive_id_type: 'chat_id' },
        data: {
          receive_id: chatId,
          msg_type: 'text',
          content: buildTextContent(text),
        },
      });

      if (res.code !== 0) {
        throw new Error(`Failed to send text message: ${res.msg}`);
      }

      return res;
    } catch (error) {
      console.error('[Feishu] Send text message error:', error.message);
      throw error;
    }
  }

  /**
   * 发送交互式卡片消息（可被 patch 更新）
   */
  async sendCardMessage(chatId, text) {
    try {
      const res = await this.client.im.message.create({
        params: { receive_id_type: 'chat_id' },
        data: {
          receive_id: chatId,
          msg_type: 'interactive',
          content: buildCardContent(text),
        },
      });

      if (res.code !== 0) {
        throw new Error(`Failed to send card message: ${res.msg}`);
      }

      return res;
    } catch (error) {
      console.error('[Feishu] Send card message error:', error.message);
      throw error;
    }
  }

  /**
   * 更新交互式卡片消息的内容（用于流式回复打字机效果）
   * im.message.patch 只能更新卡片消息，不能更新纯文本消息
   */
  async patchCardMessage(messageId, text) {
    try {
      const res = await this.client.im.message.patch({
        path: { message_id: messageId },
        data: {
          content: buildCardContent(text),
        },
      });

      if (res.code !== 0) {
        throw new Error(`Failed to patch card message: ${res.msg}`);
      }

      return res;
    } catch (error) {
      console.warn(`[Feishu] Patch card message error: ${error.message}`);
      throw error;
    }
  }

  /**
   * 主动发送消息 (供外部调用)
   */
  async send(chatId, text) {
    if (!this.client) {
      throw new Error('[Feishu] Not initialized');
    }
    return this.sendCardMessage(chatId, text);
  }
}

export default FeishuService;