"""WebSocket endpoint for streaming prose chunks and agent events."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from fastapi import WebSocket, WebSocketDisconnect

from api.dependencies import get_ws_queues


async def ws_stream(websocket: WebSocket, novel_id: str):
    """
    WebSocket handler that streams queued events for a novel.

    Clients receive JSON messages with shape:
        {"event_type": str, "agent_id": str, "payload": dict, "timestamp": str}

    The server polls the in-memory queue every 0.5s and pushes new events.
    """
    await websocket.accept()
    ws_queues = get_ws_queues()
    sent_index = 0

    try:
        while True:
            queue = ws_queues.get(novel_id, [])
            while sent_index < len(queue):
                event = queue[sent_index]
                await websocket.send_text(json.dumps(event))
                sent_index += 1

            # Check for a "done" event to close gracefully
            if queue and queue[-1].get("event_type") == "done":
                break

            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
    finally:
        await websocket.close()
