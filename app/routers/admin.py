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
async def wifi_connect(request: Request, body: dict):
    """Client modunda WiFi ağına bağlan ve listeye kaydet."""
    config = request.app.state.config
    ssid = body.get("ssid", "")
    password = body.get("password", "")
    if not ssid:
        return {"ok": False, "message": "SSID gerekli"}
    result = await wifi.connect_client(ssid, password)
    if result["ok"]:
        await wifi.add_saved_network(config, ssid, password)
    return result


@router.get("/wifi/saved")
async def wifi_saved(request: Request):
    """Kayıtlı ağ listesini döndür (şifreler maskelenir)."""
    config = request.app.state.config
    nets = await wifi.get_saved_networks(config)
    return [{"ssid": n["ssid"], "has_password": bool(n.get("password"))} for n in nets]


@router.post("/wifi/saved")
async def wifi_add_saved(request: Request, body: dict):
    """Kayıtlı ağ ekle/güncelle."""
    config = request.app.state.config
    ssid = body.get("ssid", "")
    password = body.get("password", "")
    if not ssid:
        return {"ok": False, "message": "SSID gerekli"}
    nets = await wifi.add_saved_network(config, ssid, password)
    return {"ok": True, "count": len(nets)}


@router.delete("/wifi/saved/{ssid}")
async def wifi_remove_saved(request: Request, ssid: str):
    """Kayıtlı ağı sil."""
    config = request.app.state.config
    nets = await wifi.remove_saved_network(config, ssid)
    return {"ok": True, "count": len(nets)}


@router.post("/wifi/ap")
async def wifi_ap(body: dict):
    """AP modunu başlat."""
    ssid = body.get("ssid", "")
    password = body.get("password", "")
    return await wifi.start_ap(ssid, password)
