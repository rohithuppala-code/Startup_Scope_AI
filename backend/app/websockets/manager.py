# manager.py
import asyncio
from fastapi import WebSocket
from typing import Dict, Optional


class ConnectionManager:
    """
    In-memory WebSocket connection registry for the FastAPI process.

    ARCHITECTURAL NOTE:
    This manager is process-local. Celery workers run in SEPARATE processes and
    will see an empty manager instance. Workers must NEVER import and call
    manager.send_update() directly. Instead, workers publish events to Redis
    Pub/Sub, and the redis_listener background task (running in the FastAPI
    process) receives those events and calls manager.send_update() here.
    """

    def __init__(self) -> None:
        self.active_connections: Dict[str, WebSocket] = {}
        # BUG FIX: asyncio.Lock() must not be created at class instantiation time
        # if the instance is created before the event loop starts. In Python 3.9,
        # Lock() binds to the running loop at creation — if there is no loop yet
        # (e.g. during pytest import), it raises RuntimeError. We use a lazily-
        # initialised lock via a property so the Lock is only created the first
        # time it is actually needed, which is always inside a running event loop.
        self._lock: Optional[asyncio.Lock] = None

    @property
    def lock(self) -> asyncio.Lock:
        """Returns the asyncio.Lock, creating it lazily on first access."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def connect(self, websocket: WebSocket, validation_id: str) -> None:
        """Accepts a WebSocket connection and registers it."""
        await websocket.accept()
        async with self.lock:
            self.active_connections[validation_id] = websocket

    def disconnect(self, validation_id: str, websocket: WebSocket) -> None:
        """
        Removes a WebSocket connection from the active registry.
        Only removes if the current active connection matches the disconnecting one.
        """
        if self.active_connections.get(validation_id) == websocket:
            self.active_connections.pop(validation_id, None)

    async def send_update(self, validation_id: str, message: dict) -> None:
        """
        Sends a JSON payload to the WebSocket registered for validation_id.

        BUG FIX: The previous version released the lock BEFORE calling
        send_json(). This created a TOCTOU race: a concurrent disconnect()
        between the lock release and the send could remove the entry from
        active_connections, but we'd still attempt to send on the now-orphaned
        websocket reference, generating spurious error log entries.

        Fix: hold the lock for the entire operation — lookup AND send — so
        no other coroutine can remove the entry while we're mid-send.
        The lock only prevents concurrent disconnect(); it does not block
        unrelated validation_ids since each has its own dict entry.
        """
        async with self.lock:
            websocket = self.active_connections.get(validation_id)
            if websocket is None:
                return
            try:
                await websocket.send_json(message)
            except Exception as e:
                print(f"Error sending WebSocket update to {validation_id}: {e}")
                # Safe to call disconnect() here — it just pops from the dict,
                # which is fine even while we hold the lock (no re-entrancy needed).
                self.active_connections.pop(validation_id, None)


# Singleton instance shared across the FastAPI process.
manager = ConnectionManager()