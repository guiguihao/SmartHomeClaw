import WebSocket from 'ws';
import dotenv from 'dotenv';

dotenv.config();

/**
 * 飞书 (Feishu/Lark) 插件
 * 支持 WebSocket 长连接实时监听消息与 AI 自动回复
 * 无需公网 IP，本地即可运行
 */
class FeishuService {
  constructor(config, qwenAgent) {
    this.appId = config.app_id || process.env.FEISHU_APP_ID;
    this.appSecret = config.app_secret || process.env.FEISHU_APP_SECRET;
    this.enableListener = config.enable_listener !== false;
    this.autoReply = config.auto_reply !== false;
    this.qwen = qwenAgent;
    
    this.ws = null;
    this.accessToken = null;
    this.reconnectTimer = null;
    this.heartbeatTimer = null;
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
      // 1. 获取 Access Token
      await this.getAccessToken();
      
      // 2. 建立 WebSocket 长连接
      await this.connectWebSocket();
      
      console.log('[Feishu] Started successfully');
    } catch (error) {
      console.error('[Feishu] Failed to start:', error.message);
      // 5秒后重试
      this.reconnectTimer = setTimeout(() => this.start(), 5000);
    }
  }

  /**
   * 停止飞书服务
   */
  async stop() {
    console.log('[Feishu] Stopping...');
    
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
    
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    
    console.log('[Feishu] Stopped');
  }

  /**
   * 获取 Access Token
   */
  async getAccessToken() {
    const url = 'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal';
    
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        app_id: this.appId,
        app_secret: this.appSecret,
      }),
    });

    const data = await response.json();
    
    if (data.code !== 0) {
      throw new Error(`Failed to get access token: ${data.msg}`);
    }

    this.accessToken = data.tenant_access_token;
    console.log('[Feishu] Access token obtained');
  }

  /**
   * 连接 WebSocket
   */
  async connectWebSocket() {
    const url = `wss://open.feishu.cn/open-apis/im/v1/connections/${this.accessToken}`;
    
    this.ws = new WebSocket(url, {
      headers: {
        'Authorization': `Bearer ${this.accessToken}`,
      },
    });

    this.ws.on('open', () => {
      console.log('[Feishu] WebSocket connected');
      this.startHeartbeat();
    });

    this.ws.on('message', (data) => {
      this.handleMessage(data.toString());
    });

    this.ws.on('error', (error) => {
      console.error('[Feishu] WebSocket error:', error.message);
    });

    this.ws.on('close', (code, reason) => {
      console.log(`[Feishu] WebSocket closed: ${code} ${reason}`);
      this.handleReconnect();
    });
  }

  /**
   * 启动心跳
   */
  startHeartbeat() {
    // 飞书要求每30秒发送一次心跳
    this.heartbeatTimer = setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.ping();
      }
    }, 30000);
  }

  /**
   * 处理重连
   */
  handleReconnect() {
    if (this.reconnectTimer) return;
    
    console.log('[Feishu] Reconnecting in 3 seconds...');
    this.reconnectTimer = setTimeout(async () => {
      this.reconnectTimer = null;
      await this.getAccessToken(); // 重新获取 token
      await this.connectWebSocket();
    }, 3000);
  }

  /**
   * 处理收到的消息
   */
  async handleMessage(data) {
    try {
      const message = JSON.parse(data);
      
      // 忽略心跳响应等非消息事件
      if (message.event?.message) {
        const msgData = message.event.message;
        const chatId = msgData.chat_id;
        const content = this.parseMessageContent(msgData);
        const senderId = msgData.sender?.sender_id?.open_id;

        console.log(`[Feishu] Message from ${senderId}: ${content}`);

        // 如果是 AI 自动回复，跳过
        if (senderId === this.appId) {
          return;
        }

        // AI 自动回复
        if (this.autoReply) {
          await this.replyWithAI(chatId, content, senderId);
        }
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
      console.log(`[Feishu] AI replying to: ${userMessage}`);
      
      // 获取记忆上下文
      const memoryContext = await this.qwen.decide(`
用户消息: ${userMessage}
请以智能家居 AI 助手的身份回复。
规则：
1. 如果是设备控制请求，通过 MCP 执行
2. 如果是闲聊，友好回复
3. 如果发现用户习惯，记录到 memory/HABITS.md
`, {
        appendSystemPrompt: `参考用户偏好和习惯记录`,
      });

      const reply = memoryContext.response || memoryContext.reason || '收到！';
      
      await this.sendMessage(chatId, reply);
      console.log(`[Feishu] AI reply sent: ${reply}`);
    } catch (error) {
      console.error('[Feishu] AI reply failed:', error.message);
      // 发送默认回复
      await this.sendMessage(chatId, '抱歉，我遇到了一些问题，请稍后再试。');
    }
  }

  /**
   * 发送消息
   */
  async sendMessage(chatId, text) {
    const url = 'https://open.feishu.cn/open-apis/im/v1/messages';
    
    const response = await fetch(`${url}?receive_id_type=chat_id`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.accessToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        receive_id: chatId,
        msg_type: 'text',
        content: JSON.stringify({ text }),
      }),
    });

    const data = await response.json();
    
    if (data.code !== 0) {
      throw new Error(`Failed to send message: ${data.msg}`);
    }

    return data;
  }

  /**
   * 主动发送消息 (供外部调用)
   */
  async send(chatId, text) {
    if (!this.accessToken) {
      throw new Error('[Feishu] Not connected');
    }
    return this.sendMessage(chatId, text);
  }
}

export default FeishuService;
