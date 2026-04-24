import cron from 'node-cron';

/**
 * 心跳机制
 * 定期执行系统自检和环境优化检查
 */
class Heartbeat {
  constructor(agent, config = {}) {
    this.agent = agent;
    this.enabled = config.enabled !== false;
    this.interval = config.interval || '*/5 * * * *';
    this.checks = config.checks || [];
    this.task = null;
    this.taskContent = '';
    this.onWarning = null; // 警告回调: (message, result) => {}
  }

  /**
   * 设置警告回调
   */
  setOnWarning(handler) {
    this.onWarning = handler;
  }

  /**
   * 启动心跳
   */
  start() {
    if (!this.enabled) {
      console.log('[Heartbeat] Disabled, skipping...');
      return;
    }

    console.log(`[Heartbeat] Starting (interval: ${this.interval})`);
    
    this.task = cron.schedule(this.interval, async () => {
      await this.beat();
    }, {
      timezone: 'Asia/Shanghai',
    });

    console.log('[Heartbeat] Started');
  }

  /**
   * 停止心跳
   */
  stop() {
    if (this.task) {
      this.task.stop();
      console.log('[Heartbeat] Stopped');
    }
  }

  /**
   * 执行一次心跳检查
   */
  async beat() {
    console.log('[Heartbeat] Beat...');

    for (const check of this.checks) {
      try {
        console.log(`[Heartbeat] Check: ${check.name}`);

        if (this.agent && typeof this.agent.decide === 'function') {
          const result = await this.agent.decide(check.prompt, {
            appendSystemPrompt: `当前检查项: ${check.name}\n如果发现异常，请在返回的 JSON 中设置 "is_warning": true 并提供 "reply" 说明情况。`,
          });
          console.log(`[Heartbeat] ${check.name} result:`, result);

          // 警告检测
          if (result && (result.is_warning === true || result.alert === true || result.level === 'error' || result.level === 'warning')) {
            const warningMsg = result.reply || result.response || result.content || `检测到异常: ${check.name}`;
            console.warn(`[Heartbeat] ⚠️ Major warning detected in ${check.name}: ${warningMsg}`);
            
            if (this.onWarning) {
              await this.onWarning(warningMsg, result);
            }
          }
        } else if (this.agent && typeof this.agent.runBackgroundTask === 'function') {
          const result = await this.agent.runBackgroundTask(check.prompt);
          console.log(`[Heartbeat] ${check.name} result:`, result);
        }
      } catch (error) {
        console.error(`[Heartbeat] Check failed (${check.name}):`, error.message);
      }
    }
  }

  getTaskContent() {
    return this.taskContent;
  }

  setTaskContent(content) {
    this.taskContent = content;
  }

  /**
   * 手动触发心跳
   */
  async trigger() {
    console.log('[Heartbeat] Manual trigger');
    await this.beat();
  }

  /**
   * 更新配置
   * @param {object} config - 新配置
   */
  updateConfig(config) {
    const needRestart = config.interval && config.interval !== this.interval;
    
    if (config.enabled !== undefined) {
      this.enabled = config.enabled;
    }
    if (config.interval) {
      this.interval = config.interval;
    }
    if (config.checks) {
      this.checks = config.checks;
    }

    if (needRestart && this.task) {
      this.stop();
      this.start();
    }
  }
}

export default Heartbeat;
