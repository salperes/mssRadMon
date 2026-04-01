"""WiFi yönetimi — nmcli üzerinden AP ve Client mod kontrolü."""
import asyncio
import logging
import re

logger = logging.getLogger(__name__)

AP_CON_NAME = "mssradmon-ap"
AP_DEFAULT_SSID = "mssRadMon"
AP_DEFAULT_PASS = "radmon2026"
AP_DEFAULT_IP = "192.168.4.1/24"
WIFI_DEVICE = "wlan0"


async def _run(cmd: str) -> tuple[int, str]:
    """Shell komutu çalıştır, (returncode, stdout) döndür."""
    proc = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    stdout, _ = await proc.communicate()
    return proc.returncode, stdout.decode(errors="replace").strip()


async def get_wifi_status() -> dict:
    """Mevcut WiFi durumunu döndür."""
    rc, out = await _run(f"nmcli -t -f GENERAL.TYPE,GENERAL.STATE,GENERAL.CONNECTION dev show {WIFI_DEVICE}")
    lines = dict(line.split(":", 1) for line in out.splitlines() if ":" in line)

    mode = "unknown"
    ssid = ""
    ip = ""

    con_name = lines.get("GENERAL.CONNECTION", "")

    if con_name == AP_CON_NAME:
        mode = "ap"
        # AP SSID'ini al
        rc2, ssid_out = await _run(
            f"nmcli -t -f 802-11-wireless.ssid con show {AP_CON_NAME}"
        )
        if rc2 == 0 and ":" in ssid_out:
            ssid = ssid_out.split(":", 1)[1]
    elif con_name and con_name != "--":
        mode = "client"
        rc2, ssid_out = await _run(
            f"nmcli -t -f 802-11-wireless.ssid con show \"{con_name}\""
        )
        if rc2 == 0 and ":" in ssid_out:
            ssid = ssid_out.split(":", 1)[1]

    # IP adresi
    rc3, ip_out = await _run(
        f"nmcli -t -f IP4.ADDRESS dev show {WIFI_DEVICE}"
    )
    if rc3 == 0:
        for line in ip_out.splitlines():
            if "IP4.ADDRESS" in line and ":" in line:
                ip = line.split(":", 1)[1]
                break

    return {"mode": mode, "ssid": ssid, "ip": ip, "connection": con_name}


async def scan_networks() -> list[dict]:
    """Yakındaki WiFi ağlarını tara."""
    # Rescan tetikle
    await _run(f"nmcli dev wifi rescan ifname {WIFI_DEVICE}")
    await asyncio.sleep(2)

    rc, out = await _run(
        f"nmcli -t -f SSID,SIGNAL,SECURITY,FREQ dev wifi list ifname {WIFI_DEVICE}"
    )
    if rc != 0:
        return []

    networks = []
    seen = set()
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) < 3:
            continue
        ssid = parts[0]
        if not ssid or ssid in seen:
            continue
        seen.add(ssid)
        networks.append({
            "ssid": ssid,
            "signal": int(parts[1]) if parts[1].isdigit() else 0,
            "security": parts[2] if len(parts) > 2 else "",
        })

    networks.sort(key=lambda x: x["signal"], reverse=True)
    return networks


async def connect_client(ssid: str, password: str) -> dict:
    """Client moduna geç ve belirtilen ağa bağlan."""
    # Önce AP aktifse kapat
    await _run(f"nmcli con down {AP_CON_NAME}")

    # Mevcut bağlantıyı kontrol et
    rc, existing = await _run(f"nmcli -t -f NAME con show")
    con_names = [line.strip() for line in existing.splitlines()]

    if ssid in con_names:
        # Mevcut profili güncelle ve bağlan
        if password:
            await _run(
                f"nmcli con modify \"{ssid}\" wifi-sec.key-mgmt wpa-psk wifi-sec.psk \"{password}\""
            )
        rc, out = await _run(f"nmcli con up \"{ssid}\"")
    else:
        # Yeni bağlantı oluştur
        if password:
            rc, out = await _run(
                f"nmcli dev wifi connect \"{ssid}\" password \"{password}\" ifname {WIFI_DEVICE}"
            )
        else:
            rc, out = await _run(
                f"nmcli dev wifi connect \"{ssid}\" ifname {WIFI_DEVICE}"
            )

    if rc == 0:
        return {"ok": True, "message": f"{ssid} agina baglandi"}
    return {"ok": False, "message": out}


async def start_ap(ssid: str = "", password: str = "") -> dict:
    """AP modunu başlat."""
    ssid = ssid or AP_DEFAULT_SSID
    password = password or AP_DEFAULT_PASS

    if len(password) < 8:
        return {"ok": False, "message": "AP sifresi en az 8 karakter olmali"}

    # Mevcut bağlantıyı kes
    rc, active = await _run(
        f"nmcli -t -f NAME,DEVICE con show --active"
    )
    for line in active.splitlines():
        parts = line.split(":")
        if len(parts) >= 2 and parts[1] == WIFI_DEVICE:
            await _run(f"nmcli con down \"{parts[0]}\"")

    # Eski AP profili varsa sil
    await _run(f"nmcli con delete {AP_CON_NAME}")

    # Yeni AP oluştur
    rc, out = await _run(
        f"nmcli con add type wifi ifname {WIFI_DEVICE} con-name {AP_CON_NAME} "
        f"autoconnect no ssid \"{ssid}\" "
        f"wifi.mode ap wifi.band bg wifi.channel 6 "
        f"ipv4.method shared ipv4.addresses {AP_DEFAULT_IP} "
        f"wifi-sec.key-mgmt wpa-psk wifi-sec.psk \"{password}\""
    )
    if rc != 0:
        return {"ok": False, "message": out}

    rc, out = await _run(f"nmcli con up {AP_CON_NAME}")
    if rc == 0:
        return {"ok": True, "message": f"AP '{ssid}' baslatildi ({AP_DEFAULT_IP.split('/')[0]})"}
    return {"ok": False, "message": out}
