/**
 * 测试 mcporter 能否读取 config/mcporter.json 并发现 MCP server
 */
import { createRuntime } from 'mcporter';
import path from 'path';

async function main() {
  const configPath = path.resolve(process.cwd(), './config/mcporter.json');
  console.log(`Config path: ${configPath}`);

  try {
    const runtime = await createRuntime({
      configPath,
      rootDir: process.cwd(),
    });

    const servers = runtime.listServers();
    console.log(`Discovered ${servers.length} server(s):`, servers);

    for (const name of servers) {
      const def = runtime.getDefinition(name);
      console.log(`\n--- ${name} ---`);
      console.log('Command:', def.command);

      try {
        const tools = await runtime.listTools(name);
        console.log(`Tools (${tools.length}):`);
        for (const t of tools) {
          console.log(`  - ${t.name}: ${t.description || 'no description'}`);
        }
      } catch (e) {
        console.log(`Failed to list tools: ${e.message}`);
      }
    }

    await runtime.close();
  } catch (error) {
    console.error('createRuntime failed:', error.message);
  }
}

main();