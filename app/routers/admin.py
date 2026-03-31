"""Admin API endpointleri — ayar yönetimi."""
from fastapi import APIRouter, Request

router = APIRouter(prefix="/api", tags=["admin"])


@router.get("/settings")
async def get_settings(request: Request):
    """Tüm ayarları döndür."""
    config = request.app.state.config
    return await config.get_all()


@router.put("/settings")
async def update_settings(request: Request, settings: dict):
    """Ayarları güncelle."""
    config = request.app.state.config
    for key, value in settings.items():
        await config.set(key, str(value))
    return {"status": "ok"}
