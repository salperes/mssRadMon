"""WebSocket endpoint — canlı veri akışı."""
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/live")
async def websocket_live(websocket: WebSocket):
    """Canlı veri akışı WebSocket endpoint'i."""
    await websocket.accept()
    clients = websocket.app.state.ws_clients
    clients.add(websocket)
    logger.info("WebSocket client bağlandı (toplam: %d)", len(clients))
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        clients.discard(websocket)
        logger.info("WebSocket client ayrıldı (toplam: %d)", len(clients))
