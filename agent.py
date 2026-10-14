import asyncio
import json
import os
from datetime import UTC, datetime
from tempfile import TemporaryDirectory
from time import monotonic

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)
from claude_agent_sdk.types import StreamEvent


def log(scope: str, text: str) -> None:
    for line in str(text).rstrip().split("\n"):
        timestamp = datetime.now(UTC).isoformat(timespec="milliseconds")
        print(f"[{timestamp.replace('+00:00', 'Z')}] [{scope}] {line}", flush=True)


async def run_agent(prompt: str, options=None, on_result=None, *, stop=None):
    token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "").strip()
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if bool(token) == bool(key):
        raise ValueError("Set exactly one Claude credential in .env.")

    started = monotonic()
    output = ""

    def flush(complete=True):
        nonlocal output
        end = (
            len(output) if complete else max(output.rfind(" "), output.rfind("\n")) + 1
        )
        if end:
            log("agent.text", output[:end])
            output = output[end:]

    async def stream_text():
        while True:
            await asyncio.sleep(1)
            flush(False)

    # Keep workspace, configuration, and inherited settings separate from personal use.
    with TemporaryDirectory(prefix="agent-sdk-") as workspace:
        # The Python SDK merges env with the parent, so clear inherited values first.
        env = dict.fromkeys(os.environ, "")
        env.update(
            {
                name: os.environ[name]
                for name in ("PATH", "SYSTEMROOT")
                if name in os.environ
            }
        )
        env.update(
            {
                name: workspace
                for name in (
                    "HOME",
                    "USERPROFILE",
                    "TEMP",
                    "TMP",
                    "TMPDIR",
                    "CLAUDE_CONFIG_DIR",
                )
            }
        )
        env.update(
            {
                "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
                "CLAUDE_CODE_OAUTH_TOKEN": token,
                "ANTHROPIC_API_KEY": key,
            }
        )
        settings = {
            "model": os.environ.get("CLAUDE_MODEL", "sonnet"),
            "cwd": workspace,
            "tools": [],
            "mcp_servers": {},
            "strict_mcp_config": True,
            "permission_mode": "dontAsk",
            "setting_sources": [],
            "skills": [],
            "plugins": [],
            "extra_args": {"no-session-persistence": None},
            "include_partial_messages": True,
            "stderr": lambda text: log("agent.stderr", text),
            "max_turns": 12,
            "max_budget_usd": 2,
            "env": env,
            **(options or {}),
        }
        settings["env"] = {**env, **(options or {}).get("env", {})}
        log("agent.start", f"model={settings['model']}")
        stream_task = asyncio.create_task(stream_text())
        try:
            async with asyncio.timeout(300):
                async with ClaudeSDKClient(
                    options=ClaudeAgentOptions(**settings)
                ) as client:

                    async def interrupt_on_stop():
                        await stop.wait()
                        await client.interrupt()

                    stop_task = (
                        asyncio.create_task(interrupt_on_stop()) if stop else None
                    )
                    try:
                        await client.query(prompt)
                        async for message in client.receive_response():
                            if isinstance(message, SystemMessage):
                                if message.subtype == "init":
                                    log(
                                        "agent.ready",
                                        f"session={message.data['session_id']} model={message.data['model']}",
                                    )
                                elif message.subtype == "api_retry":
                                    log("agent.retry", json.dumps(message.data))
                            elif isinstance(message, StreamEvent):
                                event = message.event
                                if (
                                    event["type"] == "content_block_delta"
                                    and event["delta"]["type"] == "text_delta"
                                ):
                                    output += event["delta"]["text"]
                                elif event["type"] == "content_block_stop":
                                    flush()
                            elif isinstance(message, AssistantMessage):
                                flush()
                                for block in message.content:
                                    if isinstance(block, ToolUseBlock):
                                        log(
                                            "tool.start",
                                            f"{block.name} id={block.id} {json.dumps(block.input)[:500]}",
                                        )
                                    elif (
                                        isinstance(block, TextBlock)
                                        and not settings["include_partial_messages"]
                                    ):
                                        log("agent.text", block.text)
                            elif isinstance(message, UserMessage) and isinstance(
                                message.content, list
                            ):
                                for block in message.content:
                                    if isinstance(block, ToolResultBlock):
                                        detail = (
                                            f" detail={str(block.content)[:500]}"
                                            if block.is_error
                                            else ""
                                        )
                                        log(
                                            "tool.stop",
                                            f"id={block.tool_use_id} status={'error' if block.is_error else 'success'}{detail}",
                                        )
                            elif isinstance(message, ResultMessage):
                                flush()
                                log(
                                    "agent.result",
                                    f"status={message.subtype} isError={message.is_error} turns={message.num_turns} durationMs={message.duration_ms}",
                                )
                                # Failed sessions can still incur cost.
                                if on_result:
                                    on_result(message)
                                if stop and stop.is_set():
                                    raise RuntimeError("Agent session stopped.")
                                if message.subtype != "success" or message.is_error:
                                    raise RuntimeError(
                                        message.result
                                        or "; ".join(
                                            message.errors or [message.subtype]
                                        )
                                    )
                                return (
                                    message.structured_output
                                    if message.structured_output is not None
                                    else message.result
                                )
                        raise RuntimeError("The agent returned no result.")
                    finally:
                        if stop_task:
                            stop_task.cancel()
                            await asyncio.gather(stop_task, return_exceptions=True)
        except TimeoutError:
            log("agent.timeout", "Session exceeded five minutes; stopping.")
            raise
        except Exception as error:
            log("agent.error", str(error))
            raise
        finally:
            stream_task.cancel()
            await asyncio.gather(stream_task, return_exceptions=True)
            flush()
            log("agent.stop", f"elapsedMs={int((monotonic() - started) * 1000)}")


if __name__ == "__main__":
    log("result", asyncio.run(run_agent("Reply with: Hello from the Agent SDK.")))
