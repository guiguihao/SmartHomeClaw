import * as lark from '@larksuiteoapi/node-sdk';

/**
 * 飞书 (Feishu/Lark) 插件
 * 基于官方 SDK 实现 WebSocket 长连接实时监听消息与 AI 自动回复
 * 无需公网 IP，本地即可运行
 */
class FeishuService {
  constructor(config, qwenAgent) {
    this.appId = config.app_id || process.env.FEISHU_APP_ID;
    this.appSecret = config.app_secret || process.env.FEISHU_APP_SECRET;
    this.enableListener = config.enable_listener !== false;
    this.autoReply = config.auto_reply !== false;
    this.qwen = qwenAgent;
    
    // 官方 SDK 客户端
    this.client = null;      // HTTP API 客户端
    this.wsClient = null;    // WebSocket 长连接客户端
    this.eventDispatcher = null;
  }

  /**
   * 启动飞书服务
   */
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

      console.log('[Feishu] ✅ Started successfully, listening for messages...');
    } catch (error) {
      console.error('[Feishu] Failed to start:', error.message);
      // 5秒后重试
      setTimeout(() => this.start(), 5000);
    }
  }

  /**
   * 停止飞书服务
   */
  async stop() {
    console.log('[Feishu] Stopping...');
    
    if (this.wsClient) {
      this.wsClient.stop();
      this.wsClient = null;
    }
    
    console.log('[Feishu] Stopped');
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
      
      // 尝试多种路径获取 sender_id
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

      // AI 自动回复
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
   * AI 自动回复
   */
  async replyWithAI(chatId, userMessage, senderId) {
    try {
      console.log(`[Feishu] 🤖 AI processing: ${userMessage}`);
      
      // 调用 AI 决策
      const result = await this.qwen.decide(`
用户在飞书发送消息: "${userMessage}"

你是 SmartHomeClaw 智能家居 AI 助手。
规则：
1. 如果是设备控制请求，通过 MCP 执行
2. 如果是闲聊，友好回复
3. 如果发现用户习惯，记录到 HABITS.md
4. 回复要简洁友好

请返回 JSON:
{
  "type": "reply" | "action" | "none",
  "reply": "回复内容",
  "action": "执行的动作 (如果有)",
  "reason": "为什么这样处理"
}
`, {
        appendSystemPrompt: '参考用户偏好和习惯记录',
      });

      const reply = result.reply || result.response || '收到！';
      
      await this.sendMessage(chatId, reply);
      console.log(`[Feishu] ✅ AI reply sent: ${reply}`);
    } catch (error) {
      console.error('[Feishu] AI reply failed:', error.message);
      // 发送默认回复
      await this.sendMessage(chatId, '抱歉，我遇到了一些问题，请稍后再试。');
    }
  }

  /**
   * 发送消息 (使用官方 SDK)
   */
  async sendMessage(chatId, text) {
    try {
      const res = await this.client.im.message.create({
        params: { receive_id_type: 'chat_id' },
        data: {
          receive_id: chatId,
          msg_type: 'text',
          content: JSON.stringify({ text }),
        },
      });

      if (res.code !== 0) {
        throw new Error(`Failed to send message: ${res.msg}`);
      }

      return res;
    } catch (error) {
      console.error('[Feishu] Send message error:', error.message);
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
    return this.sendMessage(chatId, text);
  }
}

export default FeishuService;
