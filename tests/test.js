/**
 * SmartHomeClaw 测试脚本
 * 测试核心功能
 */

import QwenAgent from '../src/services/qwen-agent.js';
import MemoryService from '../src/services/memory.js';

async function testQwenAgent() {
  console.log('\n=== Testing QwenAgent ===');
  
  const agent = new QwenAgent({
    outputFormat: 'json',
    yolo: true,
  });

  try {
    console.log('Testing basic decision...');
    const result = await agent.decide('现在是什么时间？请以 JSON 格式返回');
    console.log('Result:', result);
    console.log('✅ QwenAgent test passed');
  } catch (error) {
    console.error('❌ QwenAgent test failed:', error.message);
  }
}

async function testMemoryService() {
  console.log('\n=== Testing MemoryService ===');
  
  const memory = new MemoryService({
    directory: './memory',
  });

  try {
    await memory.init();
    console.log('Memory initialized');

    const profile = await memory.loadUserProfile();
    console.log('User Profile loaded');

    const habits = await memory.loadHabits();
    console.log('Habits loaded');

    const facts = await memory.loadFacts();
    console.log('Facts loaded');

    const all = await memory.getAll();
    console.log('All memory loaded:', Object.keys(all));
    
    console.log('✅ MemoryService test passed');
  } catch (error) {
    console.error('❌ MemoryService test failed:', error.message);
  }
}

// 运行所有测试
async function runTests() {
  console.log('Starting SmartHomeClaw tests...');
  
  await testMemoryService();
  // 注意：QwenAgent 测试需要实际安装 qwen CLI
  // await testQwenAgent();
  
  console.log('\n✅ All tests completed');
}

runTests().catch(console.error);
