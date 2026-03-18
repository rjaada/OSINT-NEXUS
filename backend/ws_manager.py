"""
ws_manager.py — WebSocket connection manager.
Extracted from main.py so state.py can instantiate it without circular imports.
"""
from __future__ import annotations

import asyncio
import json
from typing import Dict, List

from fastapi import WebSocket

_WS_MAX_TOTAL = 200
_WS_MAX_PER_IP = 10
_WS_HEARTBEAT_INTERVAL = 30  # seconds


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
        # Heartbeat task — cleans up dead connections proactively
        t = asyncio.create_task(self._heartbeat(ws))
        t.add_done_callback(lambda _: None)
        return True

    def disconnect(self, ws: WebSocket):
        if ws in self.connections:
            self.connections.remove(ws)
            ip = (ws.client.host if ws.client else "unknown") or "unknown"
            self._per_ip[ip] = max(0, self._per_ip.get(ip, 1) - 1)
            if self._per_ip[ip] == 0:
                self._per_ip.pop(ip, None)

    async def _heartbeat(self, ws: WebSocket):
        """Ping every 30s. On any send failure, disconnect the zombie connection."""
        while ws in self.connections:
            await asyncio.sleep(_WS_HEARTBEAT_INTERVAL)
            if ws not in self.connections:
                return
            try:
                await ws.send_text('{"type":"ping"}')
            except Exception:
                self.disconnect(ws)
                return

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
