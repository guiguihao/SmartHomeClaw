# SmartHomeAgent - OpenCode Guidance

## Key Commands
- Setup: `npm run setup` (installs dependencies & initializes MCP)
- Start agent: `npm start`
- Run tests: `npm test`
- Run in watch mode: `npm run dev`

## Configuration Files (all in `config/`)
- `agent.yaml`: Core agent settings
- `heartbeat.yaml`: Health check config
- `cron.yaml`: Scheduled tasks
- `plugin.yaml`: Third-party integrations

## Critical Directories
- `mcp/`: MCP server implementation (auto-registered by `npm run setup-mcp`)
- `memory/`: Persistent storage (USER_PROFILE.md, HABITS.md, FACTS.md)
- `plugin/`: Custom plugin implementations

## Operational Notes
1. Always configure `.env` from `.env.example` before first run
2. MCP servers must be placed in `mcp/` directory
3. AI brain uses: `qwen --continue -p "现在做什么？" --output-format json`
4. Requires Node.js ≥18