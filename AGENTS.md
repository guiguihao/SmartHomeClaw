# AGENTS.md

## Setup & Environment
- **Root Path:** Always run commands from the repository root `/Volumes/sandiskSSD/Project/xuexi/ureal_agent`.
- **Venv:** Use `source .venv/bin/activate`. Avoid system Python.
- **Deps:** `pip install -r requirements.txt`.
- **Secrets:** `cp .env.example .env`. Required keys: `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, `ANTHROPIC_API_KEY`, `VOLCENGINE_API_KEY`, `FEISHU_APP_ID`, `FEISHU_APP_SECRET`.

## Core Commands
- `python main.py chat` – Interactive CLI mode (includes background heartbeat/cron).
- `python launcher.py` – Starts all background microservices (Agent API, Feishu Gateway) driven by `config/services.yaml`. Use `nohup` for persistence.
- `pytest tests/test_feishu_direct.py -v` – Run specific test.

## Microservices Architecture
- The system is decoupled. `src/server/main.py` is a FastAPI server (`http://127.0.0.1:8000/v1/chat`).
- Feishu WebSocket listener is an independent gateway (`services/feishu/main.py`) that proxies messages to the API.
- Use `python launcher.py` to orchestrate booting them up.

## Key Configurations
- **Main Config:** `config/agent.yaml`. Defines model defaults, MCP servers, and skill settings.
- **Services Config:** `config/services.yaml`. Toggles which gateways/servers run via `launcher.py`.
- **Model Switching:** Use `/model <name>` in chat. Providers are listed in `config/agent.yaml`.
- **Cron:** Managed via `/cron` commands; saved to `config/crons.yaml`.
- **Heartbeat:** Runs every 5 min (configurable) using instructions in `config/HEARTBEAT.md`.
- **Memory:** Auto-saved to `memory/` (`USER_PROFILE.md`, `HABITS.md`, `FACTS.md`).

## Skill System
- **Path:** `skills/<name>/`. Must contain `skill.py` (BaseSkill subclass) and `SKILL.md`.
- **Feishu Bot:** Supports multiple bots under `skills.feishu.apps` in `agent.yaml`.
  - Use `app_id_env` for env var names or `app_id` for direct values.
  - Listener runs in an isolated process via `multiprocessing`.
  - Tool `send_text_message` accepts optional `app_name` to select bot.

## MCP Servers
- Configured in `agent.yaml` under `mcp_servers` using `stdio` transport.
- Requires absolute paths for the `command` field.

## Critical Quirks
- **Working Directory:** The CLI explicitly calls `os.chdir(ROOT)`. Relative paths in config files are relative to the repo root.
- **Logging:** Logs rotate daily at `logs/agent.log`. Console shows `WARNING`+ unless `LOG_LEVEL=DEBUG`.
- **Session Isolation:** Feishu conversations are isolated by `app_name:receive_id` in `FeishuSkill._handle_ai_reply`.
