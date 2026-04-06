from __future__ import annotations

from collections import defaultdict
from typing import Any

from fastapi import WebSocket


class RunEventHub:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, run_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[run_id].add(websocket)

    def disconnect(self, run_id: str, websocket: WebSocket) -> None:
        if run_id in self._connections:
            self._connections[run_id].discard(websocket)
            if not self._connections[run_id]:
                del self._connections[run_id]

    async def broadcast(self, run_id: str, payload: dict[str, Any]) -> None:
        stale: list[WebSocket] = []
        for socket in self._connections.get(run_id, set()):
            try:
                await socket.send_json(payload)
            except Exception:
                stale.append(socket)
        for socket in stale:
            self.disconnect(run_id, socket)


event_hub = RunEventHub()

