"""Researcher task manager — tracks running sessions, handles start/stop/resume."""
import asyncio

from server.db import get_async_db
from server.researcher.session import run_research_session

_tasks: dict[int, asyncio.Task] = {}


def is_running(job_id: int) -> bool:
    task = _tasks.get(job_id)
    return task is not None and not task.done()


async def start(job_id: int) -> bool:
    if is_running(job_id):
        return False
    async with get_async_db() as conn:
        await conn.execute(
            "UPDATE research_jobs SET status='active', current_iteration=0, iterations_since_checkpoint=0 WHERE id=$1",
            job_id,
        )
    task = asyncio.create_task(_run_with_cleanup(job_id))
    _tasks[job_id] = task
    return True


async def resume(job_id: int) -> bool:
    if is_running(job_id):
        return False
    async with get_async_db() as conn:
        await conn.execute("UPDATE research_jobs SET status='active' WHERE id=$1", job_id)
    task = asyncio.create_task(_run_with_cleanup(job_id))
    _tasks[job_id] = task
    return True


async def pause(job_id: int) -> bool:
    async with get_async_db() as conn:
        await conn.execute("UPDATE research_jobs SET status='paused' WHERE id=$1", job_id)
    return True


async def stop(job_id: int) -> None:
    task = _tasks.pop(job_id, None)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def recover_active_jobs() -> int:
    """Called on server startup — respawn tasks for any jobs left as 'active'."""
    async with get_async_db() as conn:
        rows = await conn.fetch("SELECT id FROM research_jobs WHERE status='active'")
    count = 0
    for row in rows:
        if not is_running(row["id"]):
            task = asyncio.create_task(_run_with_cleanup(row["id"]))
            _tasks[row["id"]] = task
            count += 1
    return count


async def _run_with_cleanup(job_id: int) -> None:
    try:
        await run_research_session(job_id)
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        async with get_async_db() as conn:
            await conn.execute(
                "INSERT INTO research_logs (research_job_id, role, content) VALUES ($1,'system',$2)",
                job_id, f"Session crashed: {exc}",
            )
            await conn.execute("UPDATE research_jobs SET status='paused' WHERE id=$1", job_id)
    finally:
        _tasks.pop(job_id, None)
