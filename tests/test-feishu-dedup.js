/**
 * 测试飞书消息去重功能
 */
class MockFeishuService {
  constructor() {
    this._processedMessageSet = new Set();
  }

  _simpleHash(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      const chr = str.charCodeAt(i);
      hash = ((hash << 5) - hash) + chr;
      hash |= 0;
    }
    return Math.abs(hash).toString(16);
  }

  _isDuplicateMessage(chatId, msgData, content) {
    const messageId = msgData.message_id || msgData.msg_id;
    let key = `${chatId}_${messageId}`;
    if (!messageId) {
      const hash = this._simpleHash(content);
      key = `${chatId}_${hash}`;
    }
    if (this._processedMessageSet.has(key)) {
      return true;
    }
    this._processedMessageSet.add(key);
    return false;
  }
}

const feishu = new MockFeishuService();

// 模拟重复消息场景
const chatId = 'oc_123456';
const msg1 = { message_id: 'msg001', create_time: '2025-01-01T00:00:00Z' };
const msg2 = { message_id: 'msg002', create_time: '2025-01-01T00:00:01Z' };
const content = '亮度20%';

console.log('Test 1: 不同 message_id 的消息 → 通过');
console.log('  First call:', feishu._isDuplicateMessage(chatId, msg1, content) ? '❌ 重复' : '✅ 新消息');
console.log('  Second call (different id):', feishu._isDuplicateMessage(chatId, msg2, content) ? '❌ 重复' : '✅ 新消息');

console.log('\nTest 2: 相同 message_id 的消息 → 被去重');
console.log('  Third call (same as first):', feishu._isDuplicateMessage(chatId, msg1, content) ? '✅ 重复（应跳过）' : '❌ 错误');

// 模拟无 message_id 的场景（使用内容哈希）
const chatId2 = 'oc_789012';
const msgNoId = {};
const sameContent = '亮度50%';
console.log('\nTest 3: 无 message_id，相同内容 → 被去重');
console.log('  First call (no id):', feishu._isDuplicateMessage(chatId2, msgNoId, sameContent) ? '❌ 重复' : '✅ 新消息');
console.log('  Second call (no id, same content):', feishu._isDuplicateMessage(chatId2, msgNoId, sameContent) ? '✅ 重复（应跳过）' : '❌ 错误');

// 模拟不同聊天室的相同消息（不应去重）
const chatId3 = 'oc_other';
console.log('\nTest 4: 不同聊天室相同内容 → 各自独立');
console.log('  Chat A first:', feishu._isDuplicateMessage(chatId, { message_id: 'msgA' }, 'hello') ? '❌' : '✅ 新消息');
console.log('  Chat B first:', feishu._isDuplicateMessage(chatId3, { message_id: 'msgB' }, 'hello') ? '❌' : '✅ 新消息');

// 缓存清理模拟
console.log(`\nSet size after all tests: ${feishu._processedMessageSet.size}`);
feishu._processedMessageSet.clear();
console.log('After clear:', feishu._processedMessageSet.size);