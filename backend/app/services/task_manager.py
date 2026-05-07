from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum


class TaskStatus(str, Enum):
    IDLE = "idle"
    GENERATING = "generating"
    OPTIMIZING = "optimizing"
    PLANNING = "planning"
    ERROR = "error"


@dataclass
class TaskInfo:
    session_id: str
    status: TaskStatus
    progress: int = 0
    total: int = 0
    message: str = ""


class TaskManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._tasks: dict[str, TaskInfo] = {}
        self._queues: dict[str, asyncio.Queue] = {}
        self._queue_counter = 0
        self._semaphore = asyncio.Semaphore(5)

    async def acquire(self):
        await self._semaphore.acquire()

    def release(self):
        self._semaphore.release()

    def update_task(self, session_id: str, status: TaskStatus, progress: int = 0, total: int = 0, message: str = ""):
        if status == TaskStatus.IDLE:
            self._tasks.pop(session_id, None)
        else:
            self._tasks[session_id] = TaskInfo(
                session_id=session_id,
                status=status,
                progress=progress,
                total=total,
                message=message,
            )
        self._broadcast({
            "type": "task_update",
            "data": {
                "session_id": session_id,
                "status": str(status),
                "progress": progress,
                "total": total,
                "message": message,
            },
        })

    def get_task(self, session_id: str) -> TaskInfo | None:
        return self._tasks.get(session_id)

    def get_all_tasks(self) -> dict[str, dict]:
        return {
            sid: {
                "status": str(t.status),
                "progress": t.progress,
                "total": t.total,
                "message": t.message,
            }
            for sid, t in self._tasks.items()
        }

    async def subscribe(self) -> tuple[str, asyncio.Queue]:
        self._queue_counter += 1
        queue_id = f"q_{self._queue_counter}"
        queue = asyncio.Queue()
        self._queues[queue_id] = queue
        return queue_id, queue

    def unsubscribe(self, queue_id: str):
        self._queues.pop(queue_id, None)

    def _broadcast(self, event: dict):
        for queue in self._queues.values():
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass
