"""Process-wide runtime objects shared by the server and its routers."""
import asyncio

from jarvis.core.brain import JarvisBrain

brain = JarvisBrain()

# Strong references to fire-and-forget background tasks. Without this, asyncio
# only holds a weak reference, so a running job can be garbage-collected mid-flight
# and silently cancelled (leaving its status stuck at "running").
_background_tasks: set[asyncio.Task] = set()


def spawn_background(coro, *, name: str | None = None) -> asyncio.Task:
    """Schedule a background task and keep a strong reference until it finishes."""
    task = asyncio.create_task(coro, name=name)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task
