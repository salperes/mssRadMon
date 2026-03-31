from app.routers.ws import router


def test_ws_router_exists():
    """WebSocket router doğru tanımlanmış olmalı."""
    routes = [r.path for r in router.routes]
    assert "/ws/live" in routes
