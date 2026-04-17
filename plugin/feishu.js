import * as lark from '@larksuiteoapi/node-sdk';

/**
 * 飞书 (Feishu/Lark) 插件
 * 基于官方 SDK 实现 WebSocket 长连接实时监听消息与 AI 自动回复
 * 支持流式回复：先发交互式卡片占位 → 逐 chunk patch 更新卡片 → 打字机效果
 */

/**
 * 飞书专用追加提示词
 * lark_md 语法有限，但飞书卡片支持原生 table 组件展示表格
 */
const FEISHU_SYSTEM_PROMPT = `用户在飞书发送消息，参考用户偏好和习惯记录。

### 输出格式要求
你的回复将通过飞书卡片渲染。文本部分使用 lark_md，表格部分使用卡片原生 table 组件。

lark_md 仅支持以下语法：
- 加粗 **text**、斜体 *text*、删除线 ~~text~~
- 无序列表 - text 或 * text
- 有序列表 1. text
- 行内代码 \`code\`（不支持多行代码块）
- 链接 [text](url)
- 颜色 <font color='red'>text</font>（支持 red/green/grey/orange/blue/purple）

❌ lark_md 不支持：标题 #、引用 >、分割线 ---、代码块 \`\`\`、任务列表 - [ ]

表格请使用标准 Markdown 表格语法，我们会自动转为飞书卡片原生 table：
| DID | 别名 | 型号 | 房间 | 楼层 | 备注 |
|-----|------|------|------|------|------|
| 1001 | 温控器 | RL-01 | 餐厅 | -1F | 自动模式 |`;

/**
 * 解析 Markdown 表格的一行
 * @param {string} line - 如 "| DID | 别名 | 型号 |" 或 "| 1001 | 温控器 | RL-01 |"
 * @returns {Array<string>} 单元格内容数组
 */
function parseTableRow(line) {
  const trimmed = line.trim();
  const inner = trimmed.startsWith('|') ? trimmed.slice(1) : trimmed;
  const inner2 = inner.endsWith('|') ? inner.slice(0, -1) : inner;
  return inner2.split('|').map(c => c.trim());
}

/**
 * 判断一行是否是 Markdown 表格分隔行（|---|---|）
 */
function isTableSeparatorLine(line) {
  const trimmed = line.trim();
  if (!trimmed.startsWith('|')) return false;
  const inner = trimmed.slice(1);
  const inner2 = inner.endsWith('|') ? inner.slice(0, -1) : inner;
  const cells = inner2.split('|').map(c => c.trim());
  return cells.length > 0 && cells.every(c => /^[\s\-:]+$/.test(c));
}

/**
 * 将 Markdown 表格转为飞书卡片 table 组件
 * @param {string} headerLine - 表头行
 * @param {Array<string>} dataLines - 数据行数组
 * @returns {object} 飞书卡片 table 元素
 */
function markdownTableToFeishuTable(headerLine, dataLines) {
  const headers = parseTableRow(headerLine);
  const columns = headers.map((h, idx) => ({
    name: `col_${idx}`,
    display_name: h,
    data_type: 'text',
    width: 'auto',
  }));

  const rows = dataLines.map(line => {
    const cells = parseTableRow(line);
    const row = {};
    columns.forEach((col, idx) => {
      row[col.name] = cells[idx] || '–';
    });
    return row;
  });

  return {
    tag: 'table',
    page_size: rows.length > 5 ? 5 : rows.length,
    columns,
    rows,
  };
}

/**
 * 将 AI 输出的 Markdown 文本拆分为飞书卡片元素数组
 * 表格 → table 组件；其他文本 → lark_md div
 * @param {string} text - Markdown 文本
 * @returns {Array} 飞书卡片 elements 数组
 */
function parseMarkdownToCardElements(text) {
  if (!text || typeof text !== 'string') {
    return [{ tag: 'div', text: { tag: 'lark_md', content: text || '无内容' } }];
  }

  const lines = text.split('\n');
  const elements = [];
  let i = 0;

  // 表格收集状态
  let tableHeaderLine = null;
  let tableDataLines = [];
  let inTable = false;

  // 段落收集状态
  let paragraphLines = [];

  function flushParagraph() {
    if (paragraphLines.length === 0) return;
    const content = paragraphLines.join('\n');
    // 去除 lark_md 不支持的语法
    const cleaned = cleanLarkMd(content);
    elements.push({ tag: 'div', text: { tag: 'lark_md', content: cleaned } });
    paragraphLines = [];
  }

  function flushTable() {
    if (!tableHeaderLine || tableDataLines.length === 0) {
      inTable = false;
      tableHeaderLine = null;
      tableDataLines = [];
      return;
    }
    elements.push(markdownTableToFeishuTable(tableHeaderLine, tableDataLines));
    inTable = false;
    tableHeaderLine = null;
    tableDataLines = [];
  }

  while (i < lines.length) {
    const line = lines[i];

    // ── 表格行 ──
    if (line.trim().startsWith('|')) {
      flushParagraph();

      if (isTableSeparatorLine(line)) {
        // 分隔行，跳过（已处于表格模式中）
        i++;
        continue;
      }

      if (!inTable) {
        // 表头行开始
        inTable = true;
        tableHeaderLine = line;
      } else {
        // 数据行
        tableDataLines.push(line);
      }
      i++;
      continue;
    } else if (inTable) {
      // 表格结束（当前行不是表格行）
      flushTable();
      // 不跳过当前行，继续处理
    }

    // ── 普通段落 ──
    paragraphLines.push(line);
    i++;
  }

  // 最后 flush 所有未输出内容
  flushParagraph();
  flushTable();

  // 安全兜底
  if (elements.length === 0) {
    elements.push({ tag: 'div', text: { tag: 'lark_md', content: cleanLarkMd(text) } });
  }

  return elements;
}

/**
 * 清理 lark_md 不支持的 Markdown 语法
 * 移除标题符号 #、引用 >、分割线 ---、代码块 ``` 包裹等
 * @param {string} text - 原始 Markdown
 * @returns {string} 清理后的文本
 */
function cleanLarkMd(text) {
  return text
    // 移除标题符号（# 开头的行 → 去掉 #，保留文本）
    .replace(/^#{1,6}\s+/gm, '')
    // 移除引用符号
    .replace(/^>\s+/gm, '')
    // 移除分割线（---、***、___ 独占一行）
    .replace(/^[-*_]{3,}\s*$/gm, '')
    // 移除代码块包裹（```行本身），保留内容
    .replace(/^```[\s\S]*?```$/gm, (match) => {
      // 提取代码块内容，转为行内展示
      const content = match.replace(/^```\w*\n?/, '').replace(/\n?```$/, '');
      return content;
    });
}

/**
 * 构建飞书交互式卡片 JSON（智能解析 Markdown，表格用原生 table 组件）
 * @param {string} text - Markdown 文本
 * @returns {string} JSON 字符串
 */
function buildCardContent(text) {
  const elements = parseMarkdownToCardElements(text);
  return JSON.stringify({
    config: { wide_screen_mode: true },
    header: {
      title: { tag: 'plain_text', content: '🏠 SmartHomeClaw' },
      template: 'blue',
    },
    elements,
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

    // 消息去重：避免飞书重复投递相同消息（飞书保证 at-least-once 投递，可能重复）
    // 使用 Map(key → timestamp) 而非 Set，支持按时间过期
    this._processedMessageMap = new Map(); // key: `${chatId}_${messageId}` → 处理时间戳
    this._dedupTTL = 10 * 60 * 1000; // 去重窗口：10分钟（覆盖飞书最长重试间隔）
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
    this._processedMessageMap.clear();

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
    // 每 2 分钟清理过期记录（超过 TTL 的）
    this._dedupCleanInterval = setInterval(() => {
      const now = Date.now();
      const expiredKeys = [];
      for (const [key, ts] of this._processedMessageMap) {
        if (now - ts > this._dedupTTL) {
          expiredKeys.push(key);
        }
      }
      if (expiredKeys.length > 0) {
        for (const key of expiredKeys) {
          this._processedMessageMap.delete(key);
        }
        console.log(`[Feishu] Dedup: cleaned ${expiredKeys.length} expired entries, ${this._processedMessageMap.size} remaining`);
      }
    }, 2 * 60 * 1000);
  }

  /**
   * 检查消息是否已处理过
   * @param {string} chatId - 聊天 ID
   * @param {object} msgData - 消息数据 (包含 message_id, create_time 等)
   * @param {string} content - 消息内容
   * @returns {boolean} true 表示已处理过，应该跳过
   */
  _isDuplicateMessage(chatId, msgData, content) {
    const messageId = msgData.message_id || msgData.msg_id;
    let key = `${chatId}_${messageId}`;

    // 如果无 message_id，使用 chatId+内容哈希
    if (!messageId) {
      const hash = this._simpleHash(content);
      key = `${chatId}_${hash}`;
    }

    // 检查是否已处理且未过期
    const lastProcessed = this._processedMessageMap.get(key);
    if (lastProcessed && (Date.now() - lastProcessed < this._dedupTTL)) {
      console.log(`[Feishu] Duplicate message detected (key=${key}, age=${Math.round((Date.now() - lastProcessed) / 1000)}s), skipping...`);
      return true;
    }

    // 标记为已处理（记录时间戳而非简单标记）
    this._processedMessageMap.set(key, Date.now());
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
      appendSystemPrompt: FEISHU_SYSTEM_PROMPT,
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
        appendSystemPrompt: FEISHU_SYSTEM_PROMPT,
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
      // buffer 为空时不 patch，保持"思考中..."
      if (!buffer || buffer === lastPatchContent) return;
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
        appendSystemPrompt: FEISHU_SYSTEM_PROMPT,
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