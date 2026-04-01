"""Admin API endpointleri — ayar yönetimi ve WiFi kontrolü."""
import asyncio

from fastapi import APIRouter, Request

from app import msg_service, wifi

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


@router.get("/msgservice/health")
async def msgservice_health(request: Request):
    """msgService /api/health endpoint'ini proxy'le."""
    config = request.app.state.config
    base_url = await config.get("msg_service_url") or ""
    if not base_url:
        return {"ok": False, "message": "msg_service_url ayarlanmamis"}
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: msg_service.health_check(base_url))
    if result is None:
        return {"ok": False, "message": "Servise ulasilamadi"}
    return {"ok": True, **result}


@router.post("/msgservice/test-mail")
async def msgservice_test_mail(request: Request, body: dict):
    """Secilen seviyenin alicilarına test maili gonder."""
    config = request.app.state.config
    level = body.get("level", "high")
    if level not in ("high", "high_high"):
        return {"ok": False, "message": "Gecersiz level (high | high_high)"}
    base_url = await config.get("msg_service_url") or ""
    api_key = await config.get("msg_service_api_key") or ""
    reply_to = await config.get("msg_service_reply_to") or ""
    to_raw = await config.get(f"msg_service_{level}_mail_to") or ""
    to_list = [e.strip() for e in to_raw.split(",") if e.strip()]
    if not to_list:
        return {"ok": False, "message": "Alici listesi bos — once kaydet"}
    device_name = await config.get("device_name") or "GammaScout-01"
    device_location = await config.get("device_location") or ""
    label = level.upper().replace("_", "-")
    loop = asyncio.get_event_loop()
    msg_id = await loop.run_in_executor(
        None,
        lambda: msg_service.send_mail(
            base_url, api_key, to_list, reply_to,
            label, 0.0, device_name, device_location,
        ),
    )
    if msg_id:
        return {"ok": True, "messageId": msg_id, "to": to_list}
    return {"ok": False, "message": "Gonderilemedi — URL/key/alici kontrol edin"}


@router.post("/msgservice/test-wa")
async def msgservice_test_wa(request: Request, body: dict):
    """Secilen seviyenin numaralarına test WA mesaji gonder."""
    config = request.app.state.config
    level = body.get("level", "high")
    if level not in ("high", "high_high"):
        return {"ok": False, "message": "Gecersiz level (high | high_high)"}
    base_url = await config.get("msg_service_url") or ""
    api_key = await config.get("msg_service_api_key") or ""
    to_raw = await config.get(f"msg_service_{level}_wa_to") or ""
    phone_list = [p.strip() for p in to_raw.split(",") if p.strip()]
    if not phone_list:
        return {"ok": False, "message": "Numara listesi bos — once kaydet"}
    device_name = await config.get("device_name") or "GammaScout-01"
    label = level.upper().replace("_", "-")
    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(
        None,
        lambda: msg_service.send_whatsapp(
            base_url, api_key, phone_list, label, 0.0, device_name,
        ),
    )
    sent = [r for r in results if r]
    return {"ok": bool(sent), "sent": len(sent), "total": len(phone_list)}
