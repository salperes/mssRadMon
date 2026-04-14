"""Manager sunucusuna self-registration loop."""
import asyncio
import logging
import socket

import aiohttp

logger = logging.getLogger(__name__)

REGISTER_INTERVAL = 300  # 5 dakikada bir
RETRY_DELAY = 30         # hata sonrasi


def _local_ip() -> str:
    """Bu makinenin ag IP'sini bul."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


async def register_once(config) -> bool:
    """Sunucuya bir kez register istegi gonder. Basariysa True doner."""
    manager_url = await config.get("manager_url") or ""
    register_token = await config.get("manager_register_token") or ""

    if not manager_url or not register_token:
        return False  # henuz yapilandirilmamis

    device_name = await config.get("device_name") or "mssRadMon"
    device_location = await config.get("device_location") or ""
    device_serial = await config.get("device_serial") or ""
    api_key = await config.get("api_key") or ""

    payload = {
        "serial": device_serial,
        "name": device_name,
        "location": device_location,
        "port": 8090,
        "ip": _local_ip(),
        "api_key": api_key or None,
    }

    url = manager_url.rstrip("/") + "/api/devices/register"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                headers={"X-Register-Token": register_token},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    logger.info(
                        "Registered with manager: %s (status=%s)",
                        data.get("device_id"), data.get("status"),
                    )
                    return True
                else:
                    body = await resp.text()
                    logger.warning("Register failed %d: %s", resp.status, body[:200])
                    return False
    except Exception as e:
        logger.warning("Register error: %s", e)
        return False


async def run_register_loop(config) -> None:
    """Startup'ta hemen, sonra her 5 dakikada bir register et."""
    while True:
        ok = await register_once(config)
        if ok:
            break
        await asyncio.sleep(RETRY_DELAY)

    while True:
        await asyncio.sleep(REGISTER_INTERVAL)
        await register_once(config)
