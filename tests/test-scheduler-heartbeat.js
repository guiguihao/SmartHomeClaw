/**
 * Scheduler + Heartbeat 功能测试
 * 测试定时任务调度、enable/disable、心跳巡检、触发、配置更新等
 */

import fs from 'fs/promises';
import yaml from 'yaml';
import Scheduler from '../src/services/scheduler.js';
import Heartbeat from '../src/services/heartbeat.js';
import CoreAgent from '../src/services/coreagent.js';

// ─── Helpers ───
function assert(condition, msg) {
  if (!condition) throw new Error(`❌ 断言失败: ${msg}`);
}

// Mock CoreAgent：不调用真实 LLM，只记录调用
function createMockAgent() {
  const calls = [];
  return {
    calls,
    async decide(prompt, options = {}) {
      calls.push({ prompt, options });
      return { response: `mock response for: ${prompt.substring(0, 30)}` };
    },
    async runBackgroundTask(prompt) {
      calls.push({ prompt, options: {} });
      return { response: `mock bg for: ${prompt.substring(0, 30)}` };
    },
  };
}

// ────────────────────────────────────────────
// 1. Scheduler 基础注册 & listTasks
// ────────────────────────────────────────────
async function testSchedulerRegister() {
  console.log('\n=== 1. Scheduler 注册 & listTasks ===');

  const scheduler = new Scheduler();
  const executed = [];

  scheduler.register('task_a', '*/1 * * * *', async () => {
    executed.push('task_a');
  }, { name: '任务A' });

  scheduler.register('task_b', '*/2 * * * *', async () => {
    executed.push('task_b');
  }, { name: '任务B' });

  const tasks = scheduler.listTasks();
  assert(tasks.length === 2, '应有 2 个任务');
  assert(tasks.find(t => t.id === 'task_a'), '应包含 task_a');
  assert(tasks.find(t => t.id === 'task_b'), '应包含 task_b');
  assert(tasks.find(t => t.id === 'task_a').name === '任务A', 'task_a name 应为 "任务A"');

  // 停止所有，避免后续干扰
  scheduler.stopAll();

  console.log('✅ Scheduler 注册 & listTasks 测试通过');
}

// ────────────────────────────────────────────
// 2. Scheduler unregister
// ────────────────────────────────────────────
async function testSchedulerUnregister() {
  console.log('\n=== 2. Scheduler unregister ===');

  const scheduler = new Scheduler();

  scheduler.register('task_x', '*/1 * * * *', async () => {}, { name: '任务X' });
  assert(scheduler.listTasks().length === 1, '注册后应有 1 个任务');

  scheduler.unregister('task_x');
  assert(scheduler.listTasks().length === 0, '注销后应为 0 个任务');

  // 注销不存在的不应报错
  scheduler.unregister('nonexistent');

  scheduler.stopAll();
  console.log('✅ Scheduler unregister 测试通过');
}

// ────────────────────────────────────────────
// 3. Scheduler enable / disable
// ────────────────────────────────────────────
async function testSchedulerEnableDisable() {
  console.log('\n=== 3. Scheduler enable/disable ===');

  const scheduler = new Scheduler();
  scheduler.register('task_y', '*/1 * * * *', async () => {}, { name: '任务Y' });

  // disable：暂停调度，保留注册
  const disableOk = scheduler.disable('task_y');
  assert(disableOk === true, 'disable 应返回 true');
  assert(scheduler.listTasks().length === 1, 'disable 后任务仍存在于列表');
  const taskY = scheduler.listTasks().find(t => t.id === 'task_y');
  assert(taskY.running === false, 'disable 后 running 应为 false');

  // enable：恢复调度
  const enableOk = scheduler.enable('task_y');
  assert(enableOk === true, 'enable 应返回 true');
  const taskYEnabled = scheduler.listTasks().find(t => t.id === 'task_y');
  assert(taskYEnabled.running === true, 'enable 后 running 应为 true');

  // 对不存在任务 enable/disable 应返回 false
  assert(scheduler.enable('ghost') === false, '不存在任务 enable 应返回 false');
  assert(scheduler.disable('ghost') === false, '不存在任务 disable 应返回 false');

  scheduler.stopAll();
  console.log('✅ Scheduler enable/disable 测试通过');
}

// ────────────────────────────────────────────
// 4. Scheduler registerTasks — 从 cron.yaml 配置批量注册
// ────────────────────────────────────────────
async function testSchedulerRegisterTasksFromConfig() {
  console.log('\n=== 4. Scheduler registerTasks (cron.yaml 配置) ===');

  // 加载真实 cron.yaml
  const content = await fs.readFile('./config/cron.yaml', 'utf-8');
  const config = yaml.parse(content);
  const tasksConfig = config.cron.tasks;

  const scheduler = new Scheduler();
  const executed = [];

  scheduler.registerTasks(tasksConfig, async (prompt, taskConfig) => {
    executed.push({ id: taskConfig.id, prompt });
  });

  // security_check enabled=false 应被跳过
  const registeredIds = scheduler.listTasks().map(t => t.id);
  assert(!registeredIds.includes('security_check'), 'disabled 任务不应被注册');
  assert(registeredIds.includes('morning_routine'), 'morning_routine 应被注册');
  assert(registeredIds.includes('night_routine'), 'night_routine 应被注册');
  assert(registeredIds.includes('temp_check'), 'temp_check 应被注册');
  assert(registeredIds.length === 3, '应有 3 个注册任务（security_check 被跳过）');

  scheduler.stopAll();
  console.log('✅ registerTasks (cron.yaml) 测试通过');
}

// ────────────────────────────────────────────
// 5. Scheduler 动态添加/删除/切换（模拟 AI 管理操作）
// ────────────────────────────────────────────
async function testSchedulerDynamicManagement() {
  console.log('\n=== 5. Scheduler 动态管理（模拟 AI 工具调用） ===');

  const scheduler = new Scheduler();
  const executed = [];

  // 初始注册一个任务
  scheduler.register('daily_report', '0 9 * * *', async () => {
    executed.push('daily_report');
  }, { name: '每日报告' });

  // disable（模拟 mgmt_cron_toggle enabled=false）
  scheduler.disable('daily_report');
  assert(scheduler.listTasks().find(t => t.id === 'daily_report').running === false, '禁用后 running=false');

  // enable（模拟 mgmt_cron_toggle enabled=true）
  scheduler.enable('daily_report');
  assert(scheduler.listTasks().find(t => t.id === 'daily_report').running === true, '启用后 running=true');

  // 删除（模拟 mgmt_cron_remove）
  scheduler.unregister('daily_report');
  assert(scheduler.listTasks().length === 0, '删除后应为空');

  // 添加新任务（模拟 mgmt_cron_add）
  scheduler.register('weekly_summary', '0 9 * * 1', async () => {
    executed.push('weekly_summary');
  }, { name: '每周总结' });
  assert(scheduler.listTasks().length === 1, '添加后应为 1');
  assert(scheduler.listTasks()[0].id === 'weekly_summary', '应为 weekly_summary');

  scheduler.stopAll();
  console.log('✅ 动态管理测试通过');
}

// ────────────────────────────────────────────
// 6. Scheduler 替换已存在的任务
// ────────────────────────────────────────────
async function testSchedulerReplaceExisting() {
  console.log('\n=== 6. Scheduler 替换已存在任务 ===');

  const scheduler = new Scheduler();

  scheduler.register('dup', '*/1 * * * *', async () => {}, { name: '旧任务' });
  assert(scheduler.listTasks()[0].name === '旧任务', '初始 name 应为 "旧任务"');

  // 注册相同 id 应替换
  scheduler.register('dup', '*/2 * * * *', async () => {}, { name: '新任务' });
  assert(scheduler.listTasks().length === 1, '替换后数量仍为 1');
  assert(scheduler.listTasks()[0].name === '新任务', 'name 应更新为 "新任务"');

  scheduler.stopAll();
  console.log('✅ 替换已存在任务测试通过');
}

// ────────────────────────────────────────────
// 7. Heartbeat 基础 — start / stop
// ────────────────────────────────────────────
async function testHeartbeatStartStop() {
  console.log('\n=== 7. Heartbeat start/stop ===');

  const mockAgent = createMockAgent();
  const heartbeat = new Heartbeat(mockAgent, {
    enabled: true,
    interval: '*/1 * * * *',
    checks: [
      { name: '系统健康', prompt: '系统自检' },
    ],
  });

  heartbeat.start();
  // start 后内部 task 应存在
  assert(heartbeat.task !== null, 'start 后 task 应不为 null');

  heartbeat.stop();
  console.log('✅ Heartbeat start/stop 测试通过');
}

// ────────────────────────────────────────────
// 8. Heartbeat disabled — 不启动
// ────────────────────────────────────────────
async function testHeartbeatDisabled() {
  console.log('\n=== 8. Heartbeat disabled ===');

  const mockAgent = createMockAgent();
  const heartbeat = new Heartbeat(mockAgent, {
    enabled: false,
    interval: '*/1 * * * *',
    checks: [],
  });

  heartbeat.start();
  assert(heartbeat.task === null, 'disabled 时 task 应为 null');

  console.log('✅ Heartbeat disabled 测试通过');
}

// ────────────────────────────────────────────
// 9. Heartbeat beat — 手动触发检查（不依赖 cron）
// ────────────────────────────────────────────
async function testHeartbeatBeat() {
  console.log('\n=== 9. Heartbeat beat (手动触发检查) ===');

  const mockAgent = createMockAgent();
  const heartbeat = new Heartbeat(mockAgent, {
    enabled: true,
    interval: '*/5 * * * *',
    checks: [
      { name: '系统健康', prompt: '系统自检：所有设备和服务是否正常？' },
      { name: '环境优化', prompt: '根据当前时间和环境数据，是否需要调节设备？' },
      { name: '安全巡检', prompt: '安全检查：门窗、烟雾、燃气等是否正常？' },
    ],
  });

  // 手动触发一次 beat
  await heartbeat.beat();

  assert(mockAgent.calls.length === 3, '应调用 3 次 decide');
  assert(mockAgent.calls[0].prompt.includes('系统自检'), '第一次应为系统自检');
  assert(mockAgent.calls[1].prompt.includes('环境数据'), '第二次应为环境优化');
  assert(mockAgent.calls[2].prompt.includes('安全检查'), '第三次应为安全巡检');
  assert(mockAgent.calls[0].options.appendSystemPrompt.includes('系统健康'), 'appendSystemPrompt 应含检查项名');

  console.log('✅ Heartbeat beat 测试通过');
}

// ────────────────────────────────────────────
// 10. Heartbeat trigger — 外部手动触发
// ────────────────────────────────────────────
async function testHeartbeatTrigger() {
  console.log('\n=== 10. Heartbeat trigger (外部触发) ===');

  const mockAgent = createMockAgent();
  const heartbeat = new Heartbeat(mockAgent, {
    enabled: true,
    interval: '*/5 * * * *',
    checks: [
      { name: '系统健康', prompt: '触发测试' },
    ],
  });

  await heartbeat.trigger();
  assert(mockAgent.calls.length === 1, 'trigger 应触发 1 次检查');

  console.log('✅ Heartbeat trigger 测试通过');
}

// ────────────────────────────────────────────
// 11. Heartbeat getTaskContent / setTaskContent
// ────────────────────────────────────────────
async function testHeartbeatTaskContent() {
  console.log('\n=== 11. Heartbeat getTaskContent / setTaskContent ===');

  const mockAgent = createMockAgent();
  const heartbeat = new Heartbeat(mockAgent, {
    enabled: true,
    interval: '*/5 * * * *',
    checks: [],
  });

  assert(heartbeat.getTaskContent() === '', '初始应为空');

  heartbeat.setTaskContent('执行安全巡检，检查门窗');
  assert(heartbeat.getTaskContent() === '执行安全巡检，检查门窗', '设置后应能读取');

  console.log('✅ getTaskContent / setTaskContent 测试通过');
}

// ────────────────────────────────────────────
// 12. Heartbeat 从 heartbeat.yaml 配置加载
// ────────────────────────────────────────────
async function testHeartbeatFromConfig() {
  console.log('\n=== 12. Heartbeat 从 heartbeat.yaml 配置加载 ===');

  const content = await fs.readFile('./config/heartbeat.yaml', 'utf-8');
  const config = yaml.parse(content);
  const hbConfig = config.heartbeat;

  const mockAgent = createMockAgent();
  const heartbeat = new Heartbeat(mockAgent, hbConfig);

  assert(heartbeat.enabled === true, 'enabled 应为 true');
  assert(heartbeat.interval === '*/5 * * * *', 'interval 应为 */5 * * * *');
  assert(heartbeat.checks.length === 3, '应有 3 个检查项');
  assert(heartbeat.checks[0].name === '系统健康', '第一个检查项应为 "系统健康"');
  assert(heartbeat.checks[2].name === '安全巡检', '第三个检查项应为 "安全巡检"');

  // 手动 beat 验证配置可执行
  await heartbeat.beat();
  assert(mockAgent.calls.length === 3, '3 个检查项应触发 3 次 decide');

  console.log('✅ Heartbeat 配置加载测试通过');
}

// ────────────────────────────────────────────
// 13. Heartbeat updateConfig
// ────────────────────────────────────────────
async function testHeartbeatUpdateConfig() {
  console.log('\n=== 13. Heartbeat updateConfig ===');

  const mockAgent = createMockAgent();
  const heartbeat = new Heartbeat(mockAgent, {
    enabled: true,
    interval: '*/5 * * * *',
    checks: [{ name: '检查1', prompt: 'p1' }],
  });

  heartbeat.start();
  assert(heartbeat.task !== null, 'start 后 task 应存在');

  // 更新 checks（不改 interval，不需要 restart）
  heartbeat.updateConfig({
    checks: [{ name: '新检查', prompt: '新内容' }],
  });
  assert(heartbeat.checks.length === 1, 'checks 应更新为 1');
  assert(heartbeat.checks[0].name === '新检查', 'checks 应更新为新检查');

  // 更新 interval → 应自动 restart
  heartbeat.updateConfig({
    interval: '*/10 * * * *',
  });
  assert(heartbeat.interval === '*/10 * * * *', 'interval 应更新');

  // disabled
  heartbeat.updateConfig({ enabled: false });
  assert(heartbeat.enabled === false, 'enabled 应为 false');

  heartbeat.stop();
  console.log('✅ Heartbeat updateConfig 测试通过');
}

// ────────────────────────────────────────────
// 14. CoreAgent 管理工具调用 — mgmt_cron_* / mgmt_heartbeat_*
// ────────────────────────────────────────────
async function testCoreAgentManagementTools() {
  console.log('\n=== 14. CoreAgent 管理工具调用 ===');

  const scheduler = new Scheduler();
  const mockAgent = createMockAgent();
  const heartbeat = new Heartbeat(mockAgent, {
    enabled: true,
    interval: '*/5 * * * *',
    checks: [{ name: '测试', prompt: 'test' }],
  });

  const coreAgent = new CoreAgent({
    name: 'TestAgent',
    baseUrl: 'https://mock.test/v1',
    apiKey: 'mock-key',
    model: 'mock-model',
    sessionDir: './tests/_tmp_sessions_mgmt',
  });
  coreAgent.setScheduler(scheduler);
  coreAgent.setHeartbeat(heartbeat);
  coreAgent.setOnCronTaskExecute(async (prompt, taskConfig) => {
    mockAgent.calls.push({ prompt, manual: true });
  });
  await coreAgent.init();

  // mgmt_cron_list — 空列表
  const listEmpty = coreAgent._handleManagementTool('mgmt_cron_list');
  assert(listEmpty === '无定时任务', '空列表应返回 "无定时任务"');

  // mgmt_cron_add
  const addResult = coreAgent._handleManagementTool('mgmt_cron_add', {
    task_id: 'test_task',
    name: '测试任务',
    cron: '*/1 * * * *',
    description: '执行测试',
  });
  assert(addResult.includes('test_task'), '添加结果应包含 task_id');

  // mgmt_cron_list — 有内容了
  const listAfterAdd = coreAgent._handleManagementTool('mgmt_cron_list');
  assert(listAfterAdd.includes('test_task'), '列表应包含 test_task');

  // mgmt_cron_toggle disable
  const toggleOff = coreAgent._handleManagementTool('mgmt_cron_toggle', {
    task_id: 'test_task',
    enabled: false,
  });
  assert(toggleOff.includes('已禁用'), 'disable 应返回已禁用');

  // mgmt_cron_toggle enable
  const toggleOn = coreAgent._handleManagementTool('mgmt_cron_toggle', {
    task_id: 'test_task',
    enabled: true,
  });
  assert(toggleOn.includes('已启用'), 'enable 应返回已启用');

  // mgmt_cron_remove
  const removeResult = coreAgent._handleManagementTool('mgmt_cron_remove', {
    task_id: 'test_task',
  });
  assert(removeResult.includes('已删除'), '删除应返回已删除');
  assert(coreAgent._handleManagementTool('mgmt_cron_list') === '无定时任务', '删除后应为空');

  // mgmt_heartbeat_get
  const hbGet = coreAgent._handleManagementTool('mgmt_heartbeat_get');
  assert(hbGet === '', '初始应为空');

  // mgmt_heartbeat_set
  const hbSet = coreAgent._handleManagementTool('mgmt_heartbeat_set', {
    content: '新心跳指令',
  });
  assert(hbSet === '已更新心跳任务', 'set 应返回已更新');
  assert(heartbeat.getTaskContent() === '新心跳指令', 'heartbeat content 应更新');

  // 未知工具
  const unknown = coreAgent._handleManagementTool('mgmt_unknown');
  assert(unknown.includes('未知管理工具'), '未知工具应返回提示');

  // 切换不存在任务
  const toggleGhost = coreAgent._handleManagementTool('mgmt_cron_toggle', {
    task_id: 'ghost',
    enabled: true,
  });
  assert(toggleGhost.includes('不存在'), '不存在任务应提示');

  scheduler.stopAll();
  await fs.rm('./tests/_tmp_sessions_mgmt', { recursive: true, force: true }).catch(() => {});
  console.log('✅ CoreAgent 管理工具调用测试通过');
}

// ────────────────────────────────────────────
// 运行所有测试
// ────────────────────────────────────────────
async function runTests() {
  console.log('🧪 Scheduler + Heartbeat 功能测试');
  console.log('━'.repeat(40));

  try {
    await testSchedulerRegister();
    await testSchedulerUnregister();
    await testSchedulerEnableDisable();
    await testSchedulerRegisterTasksFromConfig();
    await testSchedulerDynamicManagement();
    await testSchedulerReplaceExisting();
    await testHeartbeatStartStop();
    await testHeartbeatDisabled();
    await testHeartbeatBeat();
    await testHeartbeatTrigger();
    await testHeartbeatTaskContent();
    await testHeartbeatFromConfig();
    await testHeartbeatUpdateConfig();
    await testCoreAgentManagementTools();

    console.log('\n' + '━'.repeat(40));
    console.log('✅ 全部测试通过！');
  } catch (error) {
    console.error('\n❌ 测试失败:', error.message);
    process.exit(1);
  }
}

runTests();