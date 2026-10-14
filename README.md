# Agent SDK starter for Python

A small Python starting point for programmable Claude sessions.
`agent.py` exports `run_agent(prompt, options)` and runs a greeting when launched directly.
It starts with no tools or personal Claude settings. Pass SDK options to add your own tools and task.

## Run

Use Python 3.11 or newer with [uv](https://docs.astral.sh/uv/getting-started/installation/),
or Docker. Copy `.env.example` to `.env` and fill **one** credential:
`ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN`.

For a subscription token, run `claude setup-token`. If Claude Code is missing,
use the [official PowerShell installer](https://code.claude.com/docs/en/setup#install-claude-code),
then open a new terminal:

```powershell
irm https://claude.ai/install.ps1 | iex
```

Locally:

```sh
uv sync
uv run --env-file .env agent.py
```

Or in Docker:

```sh
docker build -t agent-sdk-starter-python .
docker run --rm --env-file .env agent-sdk-starter-python
```

Expect `Hello from the Agent SDK.`. This makes a model request using your
subscription allowance or API credits. Keep `.env` private.

To build a workflow, import `run_agent` in your own Python file and supply
the prompt and a dictionary of `ClaudeAgentOptions` fields, such as MCP tools
and a structured-output schema. Each call starts a new session with a five-minute
timeout, a 12-turn limit, and a $2 API budget.

Sessions log UTC timestamps, start and stop, streamed assistant text, tool
activity, retries, and errors. Import `log(scope, text)` for your workflow's progress.
An optional `on_result` callback receives the final SDK result, including
`total_cost_usd`, before success or error handling. This is an estimate, not an invoice.
Pass an `asyncio.Event` as `stop` to interrupt the session when your worker shuts down.

Prefer TypeScript? Use [agent-sdk-starter-typescript](https://github.com/svnscha/agent-sdk-starter-typescript).
