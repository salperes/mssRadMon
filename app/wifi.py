"""WiFi yönetimi — nmcli üzerinden AP ve Client mod kontrolü.

Kayıtlı ağlar DB'de JSON olarak tutulur. Periyodik olarak taranır,
bilinen bir ağ görülürse bağlanılır. İlk bağlantıda IP mail ile bildirilir.
"""
import asyncio
import json
import logging

logger = logging.getLogger(__name__)

AP_CON_NAME = "mssradmon-ap"
AP_DEFAULT_SSID = "mssRadMon"
AP_DEFAULT_PASS = "radmon2026"
AP_DEFAULT_IP = "192.168.4.1/24"
WIFI_DEVICE = "wlan0"


async def _run(cmd: str) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    stdout, _ = await proc.communicate()
    return proc.returncode, stdout.decode(errors="replace").strip()


# --- Status & Scan ---

async def get_wifi_status() -> dict:
    rc, out = await _run(
        f"nmcli -t -f GENERAL.TYPE,GENERAL.STATE,GENERAL.CONNECTION dev show {WIFI_DEVICE}"
    )
    lines = dict(line.split(":", 1) for line in out.splitlines() if ":" in line)

    mode = "unknown"
    ssid = ""
    ip = ""
    con_name = lines.get("GENERAL.CONNECTION", "")

    if con_name == AP_CON_NAME:
        mode = "ap"
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

    rc3, ip_out = await _run(f"nmcli -t -f IP4.ADDRESS dev show {WIFI_DEVICE}")
    if rc3 == 0:
        for line in ip_out.splitlines():
            if "IP4.ADDRESS" in line and ":" in line:
                ip = line.split(":", 1)[1]
                break

    return {"mode": mode, "ssid": ssid, "ip": ip, "connection": con_name}


async def scan_networks() -> list[dict]:
    await _run(f"nmcli dev wifi rescan ifname {WIFI_DEVICE}")
    await asyncio.sleep(2)

    rc, out = await _run(
        f"nmcli -t -f SSID,SIGNAL,SECURITY dev wifi list ifname {WIFI_DEVICE}"
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


# --- Saved Networks (DB) ---

async def get_saved_networks(config) -> list[dict]:
    """Kayıtlı ağ listesini döndür. Format: [{"ssid": "...", "password": "..."}]"""
    raw = await config.get("wifi_saved_networks")
    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return []


async def save_networks(config, networks: list[dict]):
    await config.set("wifi_saved_networks", json.dumps(networks, ensure_ascii=False))


async def add_saved_network(config, ssid: str, password: str) -> list[dict]:
    """Ağı listeye ekle veya güncelle."""
    nets = await get_saved_networks(config)
    for n in nets:
        if n["ssid"] == ssid:
            n["password"] = password
            await save_networks(config, nets)
            return nets
    nets.append({"ssid": ssid, "password": password})
    await save_networks(config, nets)
    return nets


async def remove_saved_network(config, ssid: str) -> list[dict]:
    nets = await get_saved_networks(config)
    nets = [n for n in nets if n["ssid"] != ssid]
    await save_networks(config, nets)
    return nets


# --- Connect ---

async def connect_client(ssid: str, password: str) -> dict:
    await _run(f"nmcli con down {AP_CON_NAME}")

    rc, existing = await _run("nmcli -t -f NAME con show")
    con_names = [line.strip() for line in existing.splitlines()]

    if ssid in con_names:
        if password:
            await _run(
                f"nmcli con modify \"{ssid}\" wifi-sec.key-mgmt wpa-psk wifi-sec.psk \"{password}\""
            )
        rc, out = await _run(f"nmcli con up \"{ssid}\"")
    else:
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
    ssid = ssid or AP_DEFAULT_SSID
    password = password or AP_DEFAULT_PASS

    if len(password) < 8:
        return {"ok": False, "message": "AP sifresi en az 8 karakter olmali"}

    rc, active = await _run(f"nmcli -t -f NAME,DEVICE con show --active")
    for line in active.splitlines():
        parts = line.split(":")
        if len(parts) >= 2 and parts[1] == WIFI_DEVICE:
            await _run(f"nmcli con down \"{parts[0]}\"")

    await _run(f"nmcli con delete {AP_CON_NAME}")

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


# --- Auto-connect Loop ---

async def auto_connect_loop(config, alarm_manager, interval: int = 30):
    """Periyodik olarak kayıtlı ağları tarayıp bağlan. İlk bağlantıda IP mail at."""
    last_ip = None
    notified_ip = False

    while True:
        try:
            status = await get_wifi_status()

            # Zaten bağlıysa IP takibi yap
            if status["mode"] == "client" and status["ip"]:
                current_ip = status["ip"]
                if current_ip != last_ip:
                    last_ip = current_ip
                    notified_ip = False

                if not notified_ip:
                    await _notify_ip(config, alarm_manager, status["ssid"], current_ip)
                    notified_ip = True

                await asyncio.sleep(interval)
                continue

            # Bağlı değilse kayıtlı ağları dene
            saved = await get_saved_networks(config)
            if not saved:
                await asyncio.sleep(interval)
                continue

            visible = await scan_networks()
            visible_ssids = {n["ssid"] for n in visible}

            for net in saved:
                if net["ssid"] in visible_ssids:
                    logger.info("Kayitli ag bulundu: %s, baglaniliyor...", net["ssid"])
                    result = await connect_client(net["ssid"], net["password"])
                    if result["ok"]:
                        logger.info("Baglandi: %s", net["ssid"])
                        # IP almak için kısa bekle
                        await asyncio.sleep(5)
                        new_status = await get_wifi_status()
                        if new_status["ip"]:
                            last_ip = new_status["ip"]
                            await _notify_ip(config, alarm_manager, net["ssid"], last_ip)
                            notified_ip = True
                        break
                    else:
                        logger.warning("Baglanti basarisiz %s: %s", net["ssid"], result["message"])

        except Exception as e:
            logger.error("WiFi auto-connect hatasi: %s", e)

        await asyncio.sleep(interval)


async def _notify_ip(config, alarm_manager, ssid: str, ip: str):
    """Yeni bağlantıda IP adresini mail ile bildir."""
    logger.info("WiFi baglandi: %s — IP: %s", ssid, ip)
    email_enabled = await config.get("alarm_email_enabled")
    if email_enabled != "true":
        return

    try:
        from email.message import EmailMessage
        from datetime import datetime, timezone

        to_addr = await config.get("alarm_email_to")
        host = await config.get("smtp_host")
        port = int(await config.get("smtp_port") or "587")
        user = await config.get("smtp_user")
        password = await config.get("smtp_pass")

        if not all([to_addr, host, user, password]):
            return

        device_name = await config.get("device_name") or "GammaScout-01"
        device_location = await config.get("device_location") or ""

        msg = EmailMessage()
        msg["Subject"] = f"[{device_name}] WiFi bağlandı: {ssid} — {ip}"
        msg["From"] = user
        msg["To"] = to_addr
        loc_line = f"Lokasyon: {device_location}\n" if device_location else ""
        msg.set_content(
            f"{device_name} WiFi bağlandı.\n\n"
            f"Cihaz: {device_name}\n"
            f"{loc_line}"
            f"Ağ: {ssid}\n"
            f"IP: {ip}\n"
            f"Zaman: {datetime.now().strftime('%H:%M - %d/%m/%Y')}\n"
        )

        import smtplib
        import asyncio
        loop = asyncio.get_event_loop()

        def _send():
            with smtplib.SMTP(host, port) as server:
                server.starttls()
                server.login(user, password)
                server.send_message(msg)

        await loop.run_in_executor(None, _send)
        logger.info("IP bildirim maili gonderildi: %s -> %s", ip, to_addr)
    except Exception as e:
        logger.error("IP bildirim maili hatasi: %s", e)
