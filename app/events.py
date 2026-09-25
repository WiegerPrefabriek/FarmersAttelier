"""Append-only eventlog + live-updates (Server-Sent Events) voor de inbox.

`emit()` schrijft een rij in `events` én stuurt een compact bericht naar alle open
browser-verbindingen, zodat de inbox zonder herladen bijwerkt.
"""

from __future__ import annotations

import json
import queue
import threading

from app import db

_SUBS: list[queue.Queue] = []
_SUBS_LOCK = threading.Lock()


def subscribe() -> queue.Queue:
    q: queue.Queue = queue.Queue(maxsize=200)
    with _SUBS_LOCK:
        _SUBS.append(q)
    return q


def unsubscribe(q: queue.Queue) -> None:
    with _SUBS_LOCK:
        if q in _SUBS:
            _SUBS.remove(q)


def broadcast(payload: dict) -> None:
    data = json.dumps(payload, ensure_ascii=False, default=str)
    with _SUBS_LOCK:
        dood = []
        for q in _SUBS:
            try:
                q.put_nowait(data)
            except queue.Full:
                dood.append(q)
        for q in dood:
            _SUBS.remove(q)


def emit(type_: str, conversation_id: int | None = None, customer_id: int | None = None,
         actor_type: str = "system", actor_id: int | None = None, data: dict | None = None,
         conn=None) -> int:
    rij = {
        "conversation_id": conversation_id,
        "customer_id": customer_id,
        "type": type_,
        "actor_type": actor_type,
        "actor_id": actor_id,
        "data": data or {},
    }
    event_id = db.insert("events", rij, conn=conn)
    broadcast({"event": type_, "conversation_id": conversation_id, "customer_id": customer_id,
               "data": data or {}, "id": event_id})
    return event_id
