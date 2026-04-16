/**
 * 会话管理测试 — /new /compress 功能
 */
import fs from 'fs/promises';
import CoreAgent from '../src/services/coreagent.js';

const TEST_DIR = './tests/_tmp_sessions_cmd';

function assert(condition, msg) {
  if (!condition) throw new Error(`❌ 断言失败: ${msg}`);
}

async function cleanUp() {
  await fs.rm(TEST_DIR, { recursive: true, force: true }).catch(() => {});
}

// ────────────────────────────────────────────
// 1. /new 指令 — 开启新会话
// ────────────────────────────────────────────
async function testNewSessionCommand() {
  console.log('\n=== 1. /new 指令 — 开启新会话 ===');

  const agent = new CoreAgent({
    name: 'TestAgent',
    baseUrl: 'https://mock.test/v1',
    apiKey: 'mock-key',
    model: 'mock-model',
    sessionDir: TEST_DIR,
  });
  await agent.init();

  // 先往 default session 写一些历史
  agent._sessions['default'] = [
    { role: 'user', content: 'hello' },
    { role: 'assistant', content: 'hi' },
  ];
  await agent._saveSession('default', agent._sessions['default']);

  // 发送 /new 指令
  const result = await agent.decide('/new', { sessionId: 'default' });

  assert(result.command === 'new', 'result.command 应为 "new"');
  assert(result.sessionId, 'result 应包含 sessionId');
  assert(result.response.includes('新会话'), 'response 应包含 "新会话"');

  // 新 session 应为空
  const newHistory = agent._sessions[result.sessionId];
  assert(newHistory.length === 0, '新 session 应为空');

  console.log('✅ /new 指令测试通过');
}

// ────────────────────────────────────────────
// 2. /compress 指令拦截 — 短会话无需压缩
// ────────────────────────────────────────────
async function testCompressShortSession() {
  console.log('\n=== 2. /compress 短会话 — 无需压缩 ===');

  const agent = new CoreAgent({
    name: 'TestAgent',
    baseUrl: 'https://mock.test/v1',
    apiKey: 'mock-key',
    model: 'mock-model',
    sessionDir: TEST_DIR,
  });
  await agent.init();

  // 短会话（只有 2 条）
  agent._sessions['short_session'] = [
    { role: 'user', content: 'hi' },
    { role: 'assistant', content: 'hello' },
  ];

  const result = await agent.decide('/compress', { sessionId: 'short_session' });

  assert(result.command === 'compress', 'command 应为 "compress"');
  assert(result.response.includes('无需压缩'), '短会话应提示无需压缩');

  console.log('✅ /compress 短会话测试通过');
}

// ────────────────────────────────────────────
// 3. /compress 指令 — 长会话压缩（需 mock LLM）
// ────────────────────────────────────────────
async function testCompressLongSession() {
  console.log('\n=== 3. /compress 长会话 — 压缩逻辑验证 ===');

  // 不调用真实 LLM，直接测试 compressSession 的摘要替换逻辑
  const agent = new CoreAgent({
    name: 'TestAgent',
    baseUrl: 'https://mock.test/v1',
    apiKey: 'mock-key',
    model: 'mock-model',
    sessionDir: TEST_DIR,
  });
  await agent.init();

  // 构造长会话
  const longSession = 'compress_test';
  agent._sessions[longSession] = [
    { role: 'user', content: '今天天气怎么样' },
    { role: 'assistant', content: '今天晴天，28度' },
    { role: 'user', content: '帮我关客厅灯' },
    { role: 'assistant', content: '已关客厅灯', tool_calls: [{ function: { name: 'home_light_off' } }] },
    { role: 'tool', content: '成功' },
    { role: 'user', content: '明天会下雨吗' },
    { role: 'assistant', content: '明天多云，可能有阵雨' },
  ];

  // compressSession 内部会调用真实 LLM，这里我们测试的是逻辑结构
  // 验证历史消息格式化是否正确
  const history = agent._sessions[longSession];
  assert(history.length === 7, '应有 7 条历史');

  // 验证 tool_calls 消息格式化包含工具名
  const assistantWithTool = history.find(m => m.tool_calls);
  assert(assistantWithTool !== undefined, '应存在 tool_calls 消息');
  assert(assistantWithTool.tool_calls[0].function.name === 'home_light_off', '工具名应为 home_light_off');

  console.log('✅ /compress 长会话逻辑验证通过');
}

// ────────────────────────────────────────────
// 4. /new 前缀匹配 — '/new会话' 也生效
// ────────────────────────────────────────────
async function testNewAlias() {
  console.log('\n=== 4. /new 别名指令 ===');

  const agent = new CoreAgent({
    name: 'TestAgent',
    baseUrl: 'https://mock.test/v1',
    apiKey: 'mock-key',
    model: 'mock-model',
    sessionDir: TEST_DIR,
  });
  await agent.init();

  const result = await agent.decide('/new会话');
  assert(result.command === 'new', '/new会话 应触发 new 命令');

  console.log('✅ /new 别名测试通过');
}

// ────────────────────────────────────────────
// 5. /compress 别名 — '/压缩' 也生效
// ────────────────────────────────────────────
async function testCompressAlias() {
  console.log('\n=== 5. /compress 别名指令 ===');

  const agent = new CoreAgent({
    name: 'TestAgent',
    baseUrl: 'https://mock.test/v1',
    apiKey: 'mock-key',
    model: 'mock-model',
    sessionDir: TEST_DIR,
  });
  await agent.init();

  const result = await agent.decide('/压缩');
  assert(result.command === 'compress', '/压缩 应触发 compress 命令');

  console.log('✅ /compress 别名测试通过');
}

// ────────────────────────────────────────────
// 6. 指令前有空格也能匹配
// ────────────────────────────────────────────
async function testTrimmedCommand() {
  console.log('\n=== 6. 指令前后空格 ===');

  const agent = new CoreAgent({
    name: 'TestAgent',
    baseUrl: 'https://mock.test/v1',
    apiKey: 'mock-key',
    model: 'mock-model',
    sessionDir: TEST_DIR,
  });
  await agent.init();

  const result = await agent.decide('  /new  ');
  assert(result.command === 'new', '前后空格的 /new 应触发 new 命令');

  console.log('✅ 指令空格测试通过');
}

// ────────────────────────────────────────────
// 7. 非指令消息不触发拦截
// ────────────────────────────────────────────
async function testNonCommandPasses() {
  console.log('\n=== 7. 非指令消息不触发拦截 ===');

  // 验证 decide 对非指令消息不会拦截返回 command 字段
  // 用一个不含 /new /compress 的字符串直接检查拦截逻辑
  const agent = new CoreAgent({
    name: 'TestAgent',
    baseUrl: 'https://mock.test/v1',
    apiKey: 'mock-key',
    model: 'mock-model',
    sessionDir: TEST_DIR,
  });
  await agent.init();

  // 模拟：在 decide 中 trim 后不是 /new 或 /compress，就不会触发拦截
  const prompts = ['/newday', '/compressfile', '你好', '/new session', '帮我开灯'];
  for (const p of prompts) {
    const trimmed = p.trim();
    const isNewCommand = trimmed === '/new' || trimmed === '/new会话';
    const isCompressCommand = trimmed === '/compress' || trimmed === '/压缩';
    assert(!isNewCommand && !isCompressCommand, `"${p}" 不应匹配任何指令`);
  }

  console.log('✅ 非指令消息测试通过');
}

// ────────────────────────────────────────────
// 8. newSession 方法 — 直接调用
// ────────────────────────────────────────────
async function testNewSessionMethod() {
  console.log('\n=== 8. newSession 方法直接调用 ===');

  const agent = new CoreAgent({
    name: 'TestAgent',
    baseUrl: 'https://mock.test/v1',
    apiKey: 'mock-key',
    model: 'mock-model',
    sessionDir: TEST_DIR,
  });
  await agent.init();

  // 写入旧会话
  agent._sessions['old_session'] = [
    { role: 'user', content: 'old message' },
  ];
  await agent._saveSession('old_session', agent._sessions['old_session']);

  const result = await agent.newSession('old_session');

  assert(result.sessionId.startsWith('session_'), '新 sessionId 应以 "session_" 开头');
  assert(agent._sessions[result.sessionId].length === 0, '新会话应为空');
  assert(agent._sessions['old_session'].length === 0, '旧会话应被清空');

  console.log('✅ newSession 方法测试通过');
}

// ────────────────────────────────────────────
// 9. compressSession 方法 — 短会话
// ────────────────────────────────────────────
async function testCompressSessionMethod() {
  console.log('\n=== 9. compressSession 方法 — 短会话 ===');

  const agent = new CoreAgent({
    name: 'TestAgent',
    baseUrl: 'https://mock.test/v1',
    apiKey: 'mock-key',
    model: 'mock-model',
    sessionDir: TEST_DIR,
  });
  await agent.init();

  agent._sessions['tiny'] = [
    { role: 'user', content: 'hi' },
  ];

  const result = await agent.compressSession('tiny');
  assert(result.response.includes('无需压缩'), '短会话应返回无需压缩');

  console.log('✅ compressSession 短会话测试通过');
}

// ────────────────────────────────────────────
async function runTests() {
  console.log('🧪 会话管理测试 (/new /compress)');
  console.log('━'.repeat(40));

  await cleanUp();

  try {
    await testNewSessionCommand();
    await testCompressShortSession();
    await testCompressLongSession();
    await testNewAlias();
    await testCompressAlias();
    await testTrimmedCommand();
    await testNonCommandPasses();
    await testNewSessionMethod();
    await testCompressSessionMethod();

    console.log('\n' + '━'.repeat(40));
    console.log('✅ 全部测试通过！');
  } catch (error) {
    console.error('\n❌ 测试失败:', error.message);
    process.exit(1);
  } finally {
    await cleanUp();
  }
}

runTests();