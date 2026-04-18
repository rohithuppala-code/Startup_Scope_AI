# ws_router.py

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.websockets.manager import manager

router = APIRouter()


@router.websocket("/ws/validation/{validation_id}")
async def validation_websocket(websocket: WebSocket, validation_id: str) -> None:
    """
    WebSocket endpoint. Clients connect here using their validation_id to listen
    for real-time background task updates from Celery (via Redis Pub/Sub).

    BUG FIXED: The original used `websocket.receive_text()` which raises a
    non-WebSocketDisconnect exception when the client sends a binary frame or
    a ping/pong control frame, leaking the connection from active_connections.
    We now use `websocket.receive()` which handles all WebSocket frame types
    (text, bytes, disconnect) uniformly. A disconnect is detected by the
    `type == "websocket.disconnect"` check or the WebSocketDisconnect exception.
    """
    await manager.connect(websocket, validation_id)
    try:
        while True:
            # receive() handles text, binary, and control frames gracefully.
            # We don't use the data; we only need this await to detect disconnects.
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"Unexpected WebSocket error for {validation_id}: {e}")
    finally:
        # Always clean up, regardless of how the loop exits.
        manager.disconnect(validation_id)