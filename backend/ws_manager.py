"""
ws_manager.py — WebSocket connection manager.
Extracted from main.py so state.py can instantiate it without circular imports.
"""
from __future__ import annotations

import json
from typing import Dict, List

from fastapi import WebSocket

_WS_MAX_TOTAL = 200
_WS_MAX_PER_IP = 10


class ConnectionManager:
    def __init__(self):
        self.connections: List[WebSocket] = []
        self._per_ip: Dict[str, int] = {}

    async def connect(self, ws: WebSocket) -> bool:
        """Accept the WebSocket and track it. Returns False and closes if limits exceeded."""
        ip = (ws.client.host if ws.client else "unknown") or "unknown"
        if len(self.connections) >= _WS_MAX_TOTAL:
            await ws.close(code=1008, reason="Server connection limit reached")
            return False
        if self._per_ip.get(ip, 0) >= _WS_MAX_PER_IP:
            await ws.close(code=1008, reason="Per-IP connection limit reached")
            return False
        await ws.accept()
        self.connections.append(ws)
        self._per_ip[ip] = self._per_ip.get(ip, 0) + 1
        return True

    def disconnect(self, ws: WebSocket):
        if ws in self.connections:
            self.connections.remove(ws)
            ip = (ws.client.host if ws.client else "unknown") or "unknown"
            self._per_ip[ip] = max(0, self._per_ip.get(ip, 1) - 1)
            if self._per_ip[ip] == 0:
                self._per_ip.pop(ip, None)

    async def broadcast(self, msg: dict):
        text = json.dumps(msg)
        dead = []
        for ws in self.connections:
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)
