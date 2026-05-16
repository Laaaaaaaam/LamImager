from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from enum import Enum

from app.core.events import EventLog, LamEvent

logger = logging.getLogger(__name__)


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
    task_type: str = ""
    strategy: str = ""


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
        self._queue_registry: dict[str, tuple[asyncio.Queue, str | None]] = {}
        self._session_queues: dict[str, list[str]] = {}
        self._queue_counter = 0
        self._semaphore = asyncio.Semaphore(5)
        self._cancel_events: dict[str, asyncio.Event] = {}
        self._checkpoint_states: dict[str, dict] = {}
        self._event_log = EventLog(max_size=2000)

    async def acquire(self):
        await self._semaphore.acquire()

    def release(self):
        self._semaphore.release()

    def update_task(self, session_id: str, status: TaskStatus, progress: int = 0, total: int = 0, message: str = "", task_type: str = "", strategy: str = ""):
        if status == TaskStatus.IDLE:
            self._tasks.pop(session_id, None)
            self._cancel_events.pop(session_id, None)
        else:
            self._tasks[session_id] = TaskInfo(
                session_id=session_id,
                status=status,
                progress=progress,
                total=total,
                message=message,
                task_type=task_type,
                strategy=strategy,
            )
        event = LamEvent(
            event_type="task_progress",
            correlation_id=session_id,
            payload={
                "type": "task_progress",
                "session_id": session_id,
                "status": str(status),
                "progress": progress,
                "total": total,
                "message": message,
                "task_type": task_type,
                "strategy": strategy,
            },
        )
        sse_id = self._event_log.append(event)
        sse_line = self._serialize_sse(event, sse_id)
        if session_id:
            self._put_to_session_queues(session_id, sse_line)
        for q_id, (q, q_sid) in self._queue_registry.items():
            try:
                q.put_nowait(sse_line)
            except asyncio.QueueFull:
                pass

    def get_task(self, session_id: str) -> TaskInfo | None:
        return self._tasks.get(session_id)

    def get_all_tasks(self) -> dict[str, dict]:
        return {
            sid: {
                "status": str(t.status),
                "progress": t.progress,
                "total": t.total,
                "message": t.message,
                "task_type": t.task_type,
                "strategy": t.strategy,
            }
            for sid, t in self._tasks.items()
        }

    def _serialize_sse(self, event: LamEvent, sse_id: str) -> str:
        data = json.dumps({
            "event_id": event.event_id,
            "timestamp": event.timestamp,
            "source_product": event.source_product,
            "target_product": event.target_product,
            "event_type": event.event_type,
            "correlation_id": event.correlation_id,
            "payload": event.payload,
        }, ensure_ascii=False, default=str)
        return f"event: {event.event_type}\nid: {sse_id}\ndata: {data}\n\n"

    def _put_to_session_queues(self, session_id: str, sse_line: str):
        for qid in self._session_queues.get(session_id, []):
            q_info = self._queue_registry.get(qid)
            if q_info:
                try:
                    q_info[0].put_nowait(sse_line)
                except asyncio.QueueFull:
                    pass

    async def publish(self, event: LamEvent) -> str:
        sse_id = self._event_log.append(event)
        sse_line = self._serialize_sse(event, sse_id)
        session_id = event.payload.get("session_id", "")
        delivered = 0
        is_checkpoint = event.event_type == "checkpoint_required"
        if session_id:
            self._put_to_session_queues(session_id, sse_line)
        for q_id, (q, q_sid) in self._queue_registry.items():
            if q_sid is not None and not is_checkpoint:
                continue
            if q_sid == session_id:
                continue
            try:
                q.put_nowait(sse_line)
                delivered += 1
            except asyncio.QueueFull:
                pass
        logger.info(f"publish: type={event.event_type} session={session_id} queues={len(self._queue_registry)} delivered={delivered}")
        if delivered == 0 and event.event_type in ("checkpoint_required", "task_started"):
            logger.warning(f"publish: critical event {event.event_type} has no SSE subscribers (queues={len(self._queue_registry)})")
        return sse_id

    async def subscribe(self, session_id: str | None = None, last_event_id: str | None = None) -> tuple[str, asyncio.Queue]:
        self._queue_counter += 1
        queue_id = f"q_{self._queue_counter}"
        queue = asyncio.Queue(maxsize=256)
        self._queue_registry[queue_id] = (queue, session_id)
        if session_id:
            if session_id not in self._session_queues:
                self._session_queues[session_id] = []
            self._session_queues[session_id].append(queue_id)
        tail = 0 if last_event_id else 50
        _replay_skip_types = {"checkpoint_required"}
        for sse_id, event in self._event_log.replay_since(last_event_id, tail=tail):
            if session_id and event.payload.get("session_id") != session_id:
                continue
            if event.event_type in _replay_skip_types:
                continue
            try:
                queue.put_nowait(self._serialize_sse(event, sse_id))
            except asyncio.QueueFull:
                pass
        return queue_id, queue

    def unsubscribe(self, queue_id: str):
        q_info = self._queue_registry.pop(queue_id, None)
        if q_info and q_info[1]:
            sid = q_info[1]
            if sid in self._session_queues:
                self._session_queues[sid] = [q for q in self._session_queues[sid] if q != queue_id]
                if not self._session_queues[sid]:
                    del self._session_queues[sid]

    def get_cancel_event(self, session_id: str) -> asyncio.Event:
        if session_id not in self._cancel_events:
            self._cancel_events[session_id] = asyncio.Event()
        return self._cancel_events[session_id]

    def cancel_task(self, session_id: str):
        event = self._cancel_events.get(session_id)
        if event:
            event.set()
        if session_id in self._checkpoint_states:
            cp = self._checkpoint_states[session_id]
            if "event_obj" in cp:
                cp["event_obj"].set()

    def set_checkpoint_event(self, session_id: str, event: LamEvent) -> asyncio.Event:
        import time
        evt = asyncio.Event()
        self._checkpoint_states[session_id] = {
            "event": event,
            "event_obj": evt,
            "created_at": time.time(),
            "approved": True,
        }
        return evt

    async def wait_checkpoint(self, session_id: str, timeout: float = 300.0) -> bool:
        cp = self._checkpoint_states.get(session_id)
        if not cp or "event_obj" not in cp:
            return True
        try:
            await asyncio.wait_for(cp["event_obj"].wait(), timeout=timeout)
            return cp.get("approved", False)
        except asyncio.TimeoutError:
            cp["approved"] = False
            cp["event_obj"].set()
            return False

    def resolve_checkpoint(self, session_id: str, approved: bool, retry_level: str = "approve") -> bool:
        cp = self._checkpoint_states.get(session_id)
        if cp and "event_obj" in cp:
            cp["approved"] = approved
            cp["retry_level"] = retry_level
            cp["event_obj"].set()
            return True
        return False

    def set_checkpoint_state(self, session_id: str, state: dict):
        self._checkpoint_states[session_id] = state

    def get_checkpoint_state(self, session_id: str) -> dict | None:
        return self._checkpoint_states.get(session_id)

    def store_graph_config(self, session_id: str, config: dict):
        cp = self._checkpoint_states.get(session_id, {})
        cp["graph_config"] = config
        self._checkpoint_states[session_id] = cp

    def get_graph_config(self, session_id: str) -> dict | None:
        cp = self._checkpoint_states.get(session_id)
        return cp.get("graph_config") if cp else None

    def clear_checkpoint_state(self, session_id: str):
        self._checkpoint_states.pop(session_id, None)

    def cleanup_task(self, session_id: str):
        self._tasks.pop(session_id, None)
        self._cancel_events.pop(session_id, None)


task_manager = TaskManager()
