from __future__ import annotations

import time
from dataclasses import dataclass, field
from uuid import uuid4


@dataclass
class LamEvent:
    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: int = field(default_factory=lambda: int(time.time() * 1000))
    source_product: str = "lamimager"
    target_product: str | None = None
    event_type: str = ""
    correlation_id: str = ""
    payload: dict = field(default_factory=dict)


class EventLog:
    def __init__(self, max_size: int = 2000):
        self.max_size = max_size
        self._events: list[tuple[str, LamEvent]] = []
        self._next_seq: int = 0

    def append(self, event: LamEvent) -> str:
        sse_id = f"{event.timestamp}-{self._next_seq:04d}"
        self._next_seq += 1
        self._events.append((sse_id, event))
        if len(self._events) > self.max_size:
            self._events = self._events[-self.max_size :]
        return sse_id

    def replay_since(self, last_event_id: str | None) -> list[tuple[str, LamEvent]]:
        if not last_event_id:
            return []
        for i, (eid, _) in enumerate(self._events):
            if eid == last_event_id:
                return self._events[i + 1 :]
        return []
