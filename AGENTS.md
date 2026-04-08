# AGENTS.md

## Setup
- `cp .env.example .env && edit` to add required API keys (`OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, `ANTHROPIC_API_KEY`, `VOLCENGINE_API_KEY`, `FEISHU_APP_ID`, `FEISHU_APP_SECRET`, etc.).
- Install dependencies: `pip install -r requirements.txt`.
- Activate virtual environment before any command: `source .venv/bin/activate`.

## Core commands (run from repository root)
- `python main.py` – show help/available CLI commands.
- `python main.py chat` – start interactive chat mode.
- `python main.py serve` – start backend services only (Feishu listener, heartbeat, cron). Use `nohup .venv/bin/python main.py serve &` for persistent background run.

## Testing
- Run a single test: `python -m pytest tests/test_feishu_direct.py -v`.

## Configuration
- Main config file: `config/agent.yaml`. Default model set under `model.default`; model list under `model.providers`.
- Log file path: `logs/agent.log`. Log level can be overridden via `LOG_LEVEL` in `.env`.
- Heartbeat task description: `config/HEARTBEAT.md`.
- Cron schedule file: `config/crons.yaml` (also manageable via `/cron` slash commands).
- Memory files (auto‑saved): `memory/USER_PROFILE.md`, `memory/HABITS.md`, `memory/FACTS.md`.

## Skills
- Each skill lives in `skills/<name>/` and must contain `skill.py` (implementation) and `SKILL.md` (doc).
- Feishu skill requires env vars `FEISHU_APP_ID` and `FEISHU_APP_SECRET`; enable listener with `skills.feishu.enable_listener: true` in `config/agent.yaml`.

## MCP servers
- Defined in `config/agent.yaml` under `mcp_servers`. Each entry supplies a `command` (absolute path) to launch the MCP server process.

## Runtime notes
- CLI code changes working directory to the repo root (`os.chdir(ROOT)`). Run commands from the repository root or they will fail to locate config files.
- The `python` executable used after activating the venv points to the venv’s interpreter; avoid using system Python.