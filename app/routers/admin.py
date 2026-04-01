"""Admin API endpointleri — ayar yönetimi ve WiFi kontrolü."""
from fastapi import APIRouter, Request

from app import wifi

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


@router.post("/test-email")
async def test_email(request: Request):
    """Test e-postası gönder."""
    alarm = request.app.state.alarm
    return await alarm.send_test_email()


@router.get("/wifi/status")
async def wifi_status():
    """WiFi durumunu döndür (mod, SSID, IP)."""
    return await wifi.get_wifi_status()


@router.get("/wifi/scan")
async def wifi_scan():
    """Yakındaki WiFi ağlarını tara."""
    return await wifi.scan_networks()


@router.post("/wifi/connect")
async def wifi_connect(body: dict):
    """Client modunda WiFi ağına bağlan."""
    ssid = body.get("ssid", "")
    password = body.get("password", "")
    if not ssid:
        return {"ok": False, "message": "SSID gerekli"}
    return await wifi.connect_client(ssid, password)


@router.post("/wifi/ap")
async def wifi_ap(body: dict):
    """AP modunu başlat."""
    ssid = body.get("ssid", "")
    password = body.get("password", "")
    return await wifi.start_ap(ssid, password)
