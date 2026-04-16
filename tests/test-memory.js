/**
 * 记忆系统自主进化功能测试
 * 测试 MemoryService 读写 + CoreAgent 工具调用记忆 + 上下文注入
 */

import fs from 'fs/promises';
import path from 'path';
import MemoryService from '../src/services/memory.js';
import CoreAgent from '../src/services/coreagent.js';
import Scheduler from '../src/services/scheduler.js';

// ─── 测试用临时目录 ───
const TEST_DIR = './tests/_tmp_memory';

async function cleanUp() {
  await fs.rm(TEST_DIR, { recursive: true, force: true }).catch(() => {});
}

// ────────────────────────────────────────────
// 1. MemoryService 基础读写
// ────────────────────────────────────────────
async function testMemoryReadWrite() {
  console.log('\n=== 1. MemoryService 读写测试 ===');

  const memory = new MemoryService({
    directory: TEST_DIR,
    userProfile: 'USER_PROFILE.md',
    habits: 'HABITS.md',
    facts: 'FACTS.md',
  });

  await memory.init();

  // 写入
  await memory.updateUserProfile('# 用户偏好\n- 姓名: 张三\n- 温度偏好: 26°C');
  await memory.updateHabits('# 习惯\n- 每晚10点关灯');
  await memory.updateFacts('# 家居\n- 户型: 两室一厅');

  // 读取
  const profile = await memory.loadUserProfile();
  const habits = await memory.loadHabits();
  const facts = await memory.loadFacts();

  assert(profile.includes('张三'), 'profile 应包含 "张三"');
  assert(habits.includes('10点关灯'), 'habits 应包含 "10点关灯"');
  assert(facts.includes('两室一厅'), 'facts 应包含 "两室一厅"');

  console.log('✅ MemoryService 读写测试通过');
}

// ────────────────────────────────────────────
// 2. MemoryService.getAll()
// ────────────────────────────────────────────
async function testMemoryGetAll() {
  console.log('\n=== 2. MemoryService.getAll() 测试 ===');

  const memory = new MemoryService({ directory: TEST_DIR });
  const all = await memory.getAll();

  assert(typeof all === 'object', 'getAll 应返回对象');
  assert('userProfile' in all, '应包含 userProfile 键');
  assert('habits' in all, '应包含 habits 键');
  assert('facts' in all, '应包含 facts 键');
  assert(all.userProfile.includes('张三'), 'all.userProfile 应包含 "张三"');

  console.log('✅ getAll() 测试通过');
}

// ────────────────────────────────────────────
// 3. MemoryService 覆盖更新（模拟自主进化）
// ────────────────────────────────────────────
async function testMemoryEvolution() {
  console.log('\n=== 3. 记忆自主进化测试 ===');

  const memory = new MemoryService({ directory: TEST_DIR });
  await memory.init();

  // 第一轮：AI 发现用户偏好
  await memory.updateUserProfile('# 用户偏好\n- 姓名: 张三\n- 温度偏好: 26°C\n- 喜欢柔和灯光');

  // 第二轮：AI 发现新习惯，追加更新
  await memory.updateHabits('# 习惯\n- 每晚10点关灯\n- 早上7点开客厅灯\n- 周末喜欢睡懒觉');

  // 第三轮：AI 学习到新事实
  await memory.updateFacts('# 家居\n- 户型: 两室一厅\n- 客厅空调: 格力\n- 卧室灯: 小米智能灯');

  // 验证进化后的内容
  const all = await memory.getAll();
  assert(all.userProfile.includes('柔和灯光'), '进化后 profile 应包含 "柔和灯光"');
  assert(all.habits.includes('睡懒觉'), '进化后 habits 应包含 "睡懒觉"');
  assert(all.facts.includes('小米智能灯'), '进化后 facts 应包含 "小米智能灯"');

  console.log('✅ 记忆自主进化测试通过');
}

// ────────────────────────────────────────────
// 4. CoreAgent 记忆工具调用（异步）
// ────────────────────────────────────────────
async function testCoreAgentMemoryTools() {
  console.log('\n=== 4. CoreAgent 记忆工具调用测试 ===');

  const memory = new MemoryService({ directory: TEST_DIR });
  await memory.init();

  // 构造一个 mock CoreAgent（不需要真实 API 调用）
  const agent = new CoreAgent({
    name: 'TestAgent',
    baseUrl: 'https://mock.test/v1',
    apiKey: 'mock-key',
    model: 'mock-model',
    sessionDir: './tests/_tmp_sessions',
  });
  agent.setMemory(memory);
  await agent.init();

  // 测试 _handleMemoryTool 异步调用
  const profileResult = await agent._handleMemoryTool('memory_get_user_profile');
  assert(profileResult.includes('张三'), 'memory_get_user_profile 应返回包含 "张三" 的内容');

  const habitsResult = await agent._handleMemoryTool('memory_get_habits');
  assert(habitsResult.includes('睡懒觉'), 'memory_get_habits 应返回包含 "睡懒觉" 的内容');

  const factsResult = await agent._handleMemoryTool('memory_get_facts');
  assert(factsResult.includes('小米智能灯'), 'memory_get_facts 应返回包含 "小米智能灯" 的内容');

  // 测试更新
  await agent._handleMemoryTool('memory_update_user_profile', { content: '# 进化后偏好\n- 姓名: 张三\n- 新偏好: 不喜欢太冷' });
  const updated = await memory.loadUserProfile();
  assert(updated.includes('不喜欢太冷'), '更新后 profile 应包含 "不喜欢太冷"');

  // 测试未知工具
  const unknownResult = await agent._handleMemoryTool('memory_unknown_tool');
  assert(unknownResult.includes('未知记忆工具'), '未知工具应返回 "未知记忆工具"');

  console.log('✅ CoreAgent 记忆工具调用测试通过');
}

// ────────────────────────────────────────────
// 5. CoreAgent._loadMemoryContext 上下文注入
// ────────────────────────────────────────────
async function testMemoryContextInjection() {
  console.log('\n=== 5. 记忆上下文注入测试 ===');

  const memory = new MemoryService({ directory: TEST_DIR });
  await memory.init();

  const agent = new CoreAgent({
    name: 'TestAgent',
    baseUrl: 'https://mock.test/v1',
    apiKey: 'mock-key',
    model: 'mock-model',
    sessionDir: './tests/_tmp_sessions',
  });
  agent.setMemory(memory);
  await agent.init();

  const ctx = await agent._loadMemoryContext();
  assert(ctx.includes('用户偏好'), '上下文应包含 "用户偏好"');
  assert(ctx.includes('张三'), '上下文应包含 "张三"');
  assert(ctx.includes('习惯记录'), '上下文应包含 "习惯记录"');
  assert(ctx.includes('家居事实'), '上下文应包含 "家居事实"');

  // 无记忆服务时应返回空
  const agentNoMemory = new CoreAgent({
    baseUrl: 'https://mock.test/v1',
    apiKey: 'mock-key',
    model: 'mock-model',
    sessionDir: './tests/_tmp_sessions',
  });
  const emptyCtx = await agentNoMemory._loadMemoryContext();
  assert(emptyCtx === '', '无记忆服务时应返回空字符串');

  console.log('✅ 记忆上下文注入测试通过');
}

// ────────────────────────────────────────────
// 6. 初始化时文件不存在的情况
// ────────────────────────────────────────────
async function testMemoryInitWithMissingFiles() {
  console.log('\n=== 6. 记忆文件不存在时的初始化测试 ===');

  const dir = './tests/_tmp_memory_empty';
  await fs.rm(dir, { recursive: true, force: true }).catch(() => {});

  const memory = new MemoryService({ directory: dir });
  await memory.init();

  // 初始化后文件应被创建
  const profile = await memory.loadUserProfile();
  assert(profile !== undefined, '初始化后 loadUserProfile 不应抛错');

  // getAll 也应正常工作
  const all = await memory.getAll();
  assert(typeof all === 'object', 'getAll 应返回对象');

  await fs.rm(dir, { recursive: true, force: true }).catch(() => {});
  console.log('✅ 记忆文件不存在时初始化测试通过');
}

// ────────────────────────────────────────────
// Helper
// ────────────────────────────────────────────
function assert(condition, msg) {
  if (!condition) {
    throw new Error(`❌ 断言失败: ${msg}`);
  }
}

// ────────────────────────────────────────────
// 运行所有测试
// ────────────────────────────────────────────
async function runTests() {
  console.log('🧪 记忆系统自主进化功能测试');
  console.log('━'.repeat(40));

  await cleanUp();

  try {
    await testMemoryReadWrite();
    await testMemoryGetAll();
    await testMemoryEvolution();
    await testCoreAgentMemoryTools();
    await testMemoryContextInjection();
    await testMemoryInitWithMissingFiles();

    console.log('\n' + '━'.repeat(40));
    console.log('✅ 全部测试通过！');
  } catch (error) {
    console.error('\n❌ 测试失败:', error.message);
    process.exit(1);
  } finally {
    await cleanUp();
    await fs.rm('./tests/_tmp_sessions', { recursive: true, force: true }).catch(() => {});
  }
}

runTests();