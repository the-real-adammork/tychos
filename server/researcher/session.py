"""Research session runner -- the core SDK conversation loop.

Drives a Claude Agent SDK conversation for a research job. Between turns:
checks budget, reads user-injected messages, logs all events.
"""
import json
import os
import time

import anthropic

from server.db import get_async_db
from server.researcher.tools import TOOL_SCHEMAS
import server.researcher.tools as _tools


async def _sdk_turn(messages: list[dict], *, model: str, system: str, tools: list[dict]) -> "anthropic.types.Message":
    """One SDK round-trip. Separated for easy mocking in tests."""
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    with client.messages.stream(
        model=model,
        max_tokens=4096,
        system=system,
        tools=tools,
        messages=messages,
    ) as stream:
        return stream.get_final_message()


async def _log(conn, job_id: int, role: str, content: str | None, tool_name: str | None = None, token_count: int | None = None, iteration_id: int | None = None):
    await conn.execute(
        "INSERT INTO research_logs (research_job_id, research_iteration_id, role, content, tool_name, token_count) "
        "VALUES ($1,$2,$3,$4,$5,$6)",
        job_id, iteration_id, role, content, tool_name, token_count,
    )


async def _build_initial_context(job_id: int) -> tuple[str, list[dict]]:
    """Build system prompt + initial messages for a fresh session."""
    async with get_async_db() as conn:
        job = await conn.fetchrow("SELECT * FROM research_jobs WHERE id=$1", job_id)
        system = job["instructions"] or ""

        baseline = await conn.fetchrow(
            "SELECT params_json FROM param_versions WHERE param_set_id=$1 AND is_checkpoint=TRUE ORDER BY version_number DESC LIMIT 1",
            job["param_set_id"],
        )
        if baseline is None:
            baseline = await conn.fetchrow(
                "SELECT params_json FROM param_versions WHERE param_set_id=$1 ORDER BY version_number ASC LIMIT 1",
                job["param_set_id"],
            )

        iterations = await conn.fetch(
            "SELECT kind, objective, created_at FROM research_iterations WHERE research_job_id=$1 ORDER BY created_at DESC LIMIT 10",
            job_id,
        )

    history_lines = []
    for it in reversed(list(iterations)):
        history_lines.append(f"  {it['kind']}: objective={it['objective']}")

    snapshot = f"Current checkpoint params:\n```json\n{baseline['params_json']}\n```\n"
    if history_lines:
        snapshot += "\nRecent iteration history:\n" + "\n".join(history_lines) + "\n"
    snapshot += "\nBegin optimizing. Use propose_params to test changes, checkpoint when improved, search for coupled parameters."

    return system, [{"role": "user", "content": snapshot}]


async def _rebuild_conversation(job_id: int) -> tuple[str, list[dict]]:
    """Rebuild conversation from research_logs for resume."""
    async with get_async_db() as conn:
        job = await conn.fetchrow("SELECT * FROM research_jobs WHERE id=$1", job_id)
        system = job["instructions"] or ""
        logs = await conn.fetch(
            "SELECT role, content, tool_name FROM research_logs WHERE research_job_id=$1 ORDER BY created_at ASC, id ASC",
            job_id,
        )

    if not logs:
        return await _build_initial_context(job_id)

    messages: list[dict] = []
    for log in logs:
        if log["role"] == "user_inject":
            messages.append({"role": "user", "content": log["content"]})
        elif log["role"] == "assistant":
            messages.append({"role": "assistant", "content": log["content"]})
        elif log["role"] == "tool_call":
            content = json.loads(log["content"]) if log["content"] else {}
            if not messages or messages[-1]["role"] != "assistant":
                messages.append({"role": "assistant", "content": []})
            if isinstance(messages[-1]["content"], str):
                messages[-1]["content"] = [{"type": "text", "text": messages[-1]["content"]}]
            messages[-1]["content"].append({
                "type": "tool_use",
                "id": content.get("tool_use_id", "unknown"),
                "name": log["tool_name"],
                "input": content.get("input", {}),
            })
        elif log["role"] == "tool_result":
            if not messages or messages[-1]["role"] != "user":
                messages.append({"role": "user", "content": []})
            if isinstance(messages[-1]["content"], str):
                messages[-1]["content"] = [{"type": "text", "text": messages[-1]["content"]}]
            content = json.loads(log["content"]) if log["content"] else {}
            messages[-1]["content"].append({
                "type": "tool_result",
                "tool_use_id": content.get("tool_use_id", "unknown"),
                "content": content.get("result", ""),
            })
        elif log["role"] == "system":
            messages.append({"role": "user", "content": log["content"]})

    if not messages:
        return await _build_initial_context(job_id)

    return system, messages


async def run_research_session(job_id: int) -> None:
    """Main session loop. Runs until budget hit, user pause, or Claude end_turn."""
    async with get_async_db() as conn:
        job = await conn.fetchrow("SELECT * FROM research_jobs WHERE id=$1", job_id)
        if not job:
            return

    has_logs = False
    async with get_async_db() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM research_logs WHERE research_job_id=$1", job_id)
        has_logs = count > 0

    if has_logs:
        system, messages = await _rebuild_conversation(job_id)
    else:
        system, messages = await _build_initial_context(job_id)

    session_start = time.time()
    async with get_async_db() as conn:
        await conn.execute(
            "UPDATE research_jobs SET session_started_at=to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS') WHERE id=$1",
            job_id,
        )

    model = job["model"] or "claude-sonnet-4-6"
    max_iter = job["max_iterations"]
    max_wall = job["max_wall_clock_seconds"]
    max_plateau = job["no_improvement_plateau"]

    retries = 0

    while True:
        # Budget checks
        async with get_async_db() as conn:
            job = await conn.fetchrow("SELECT * FROM research_jobs WHERE id=$1", job_id)

        if job["status"] != "active":
            return

        if job["current_iteration"] >= max_iter:
            async with get_async_db() as conn:
                await _log(conn, job_id, "system", f"Budget exhausted: {max_iter} iterations reached")
                await conn.execute("UPDATE research_jobs SET status='paused' WHERE id=$1", job_id)
            return

        if time.time() - session_start > max_wall:
            async with get_async_db() as conn:
                await _log(conn, job_id, "system", f"Budget exhausted: {max_wall}s wall-clock reached")
                await conn.execute("UPDATE research_jobs SET status='paused' WHERE id=$1", job_id)
            return

        if job["iterations_since_checkpoint"] >= max_plateau:
            async with get_async_db() as conn:
                await _log(conn, job_id, "system", f"Budget exhausted: {max_plateau} iterations without improvement")
                await conn.execute("UPDATE research_jobs SET status='paused' WHERE id=$1", job_id)
            return

        # Check for user injections
        async with get_async_db() as conn:
            pending = await conn.fetch(
                "SELECT id, content FROM research_messages WHERE research_job_id=$1 AND consumed=FALSE ORDER BY created_at ASC",
                job_id,
            )
            for msg in pending:
                messages.append({"role": "user", "content": msg["content"]})
                await _log(conn, job_id, "user_inject", msg["content"])
                await conn.execute("UPDATE research_messages SET consumed=TRUE WHERE id=$1", msg["id"])

        # SDK turn
        try:
            response = await _sdk_turn(messages, model=model, system=system, tools=TOOL_SCHEMAS)
            retries = 0
        except Exception as exc:
            retries += 1
            if retries >= 3:
                async with get_async_db() as conn:
                    await _log(conn, job_id, "system", f"SDK error after 3 retries: {exc}")
                    await conn.execute("UPDATE research_jobs SET status='paused' WHERE id=$1", job_id)
                return
            import asyncio as _aio
            await _aio.sleep(30)
            continue

        # Log assistant response
        async with get_async_db() as conn:
            for block in response.content:
                if block.type == "text":
                    await _log(conn, job_id, "assistant", block.text, token_count=response.usage.output_tokens)
                elif block.type == "tool_use":
                    await _log(conn, job_id, "tool_call",
                        json.dumps({"tool_use_id": block.id, "input": block.input}),
                        tool_name=block.name)

        # Append assistant message to conversation
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            async with get_async_db() as conn:
                await _log(conn, job_id, "system", f"Claude ended turn: {response.stop_reason}")
                await conn.execute("UPDATE research_jobs SET status='completed' WHERE id=$1", job_id)
            return

        # Execute tool calls
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result_str = await _tools.execute_tool(block.name, block.input, job_id)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_str,
                })
                async with get_async_db() as conn:
                    await _log(conn, job_id, "tool_result",
                        json.dumps({"tool_use_id": block.id, "result": result_str}),
                        tool_name=block.name)

                # Update iteration counters for propose_params and search
                if block.name in ("propose_params", "search"):
                    is_checkpoint = False
                    if block.name == "search":
                        try:
                            sr = json.loads(result_str)
                            is_checkpoint = sr.get("improved", False)
                        except Exception:
                            pass

                    async with get_async_db() as conn:
                        if is_checkpoint:
                            await conn.execute(
                                "UPDATE research_jobs SET current_iteration=current_iteration+1, iterations_since_checkpoint=0 WHERE id=$1",
                                job_id,
                            )
                        else:
                            await conn.execute(
                                "UPDATE research_jobs SET current_iteration=current_iteration+1, iterations_since_checkpoint=iterations_since_checkpoint+1 WHERE id=$1",
                                job_id,
                            )

                elif block.name == "checkpoint":
                    async with get_async_db() as conn:
                        await conn.execute(
                            "UPDATE research_jobs SET iterations_since_checkpoint=0 WHERE id=$1",
                            job_id,
                        )

        messages.append({"role": "user", "content": tool_results})
