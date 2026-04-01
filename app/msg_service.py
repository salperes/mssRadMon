"""msgService REST API client — e-posta ve WhatsApp gonderimi."""
import json
import logging
import ssl
import urllib.request
from datetime import datetime

logger = logging.getLogger(__name__)

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

_TIMEOUT = 5


def _local_time() -> str:
    return datetime.now().strftime("%H:%M - %d/%m/%Y")


def _post(url: str, api_key: str, payload: dict) -> dict | None:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "X-API-Key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT, context=_ssl_ctx) as resp:
            return json.loads(resp.read())
    except Exception as e:
        logger.error("msgService POST %s hatasi: %s", url, e)
        return None


def _get(url: str) -> dict | None:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT, context=_ssl_ctx) as resp:
            return json.loads(resp.read())
    except Exception as e:
        logger.error("msgService GET %s hatasi: %s", url, e)
        return None


def send_mail(
    base_url: str,
    api_key: str,
    to_list: list[str],
    reply_to: str,
    level_label: str,
    dose_rate: float,
    device_name: str,
    device_location: str,
) -> str | None:
    """E-posta gonder. Basarida messageId, hatada None doner."""
    if not base_url or not api_key or not to_list:
        return None

    body = (
        f"Radyasyon alarmi tetiklendi.<br><br>"
        f"Seviye &nbsp;&nbsp;: {level_label}<br>"
        f"Doz Hizi : {dose_rate:.3f} µSv/h<br>"
        f"Zaman &nbsp;&nbsp;: {_local_time()}<br>"
        f"Cihaz &nbsp;&nbsp;: {device_name}<br>"
    )
    if device_location:
        body += f"Lokasyon : {device_location}<br>"

    payload: dict = {
        "to": to_list,
        "subject": f"[mssRadMon] ALARM {level_label}: {dose_rate:.3f} µSv/h",
        "body": body,
        "bodyType": "html",
        "template": "alert",
        "metadata": {
            "source": "mssradmon",
            "entityType": "alarm",
            "entityId": level_label.lower(),
        },
    }
    if reply_to:
        payload["replyTo"] = reply_to

    result = _post(f"{base_url}/api/send", api_key, payload)
    if result and result.get("success"):
        return result.get("messageId")
    return None


def send_whatsapp(
    base_url: str,
    api_key: str,
    phone_list: list[str],
    level_label: str,
    dose_rate: float,
    device_name: str,
) -> list[str | None]:
    """Her numara icin ayri WA mesaji gonder. MessageId listesi doner (None = basarisiz)."""
    if not base_url or not api_key or not phone_list:
        return []

    body = (
        f"[mssRadMon] ALARM {level_label}\n"
        f"Doz: {dose_rate:.3f} µSv/h | {_local_time()}\n"
        f"Cihaz: {device_name}"
    )

    results: list[str | None] = []
    for phone in phone_list:
        payload = {
            "phone": phone.strip(),
            "body": body,
            "metadata": {
                "source": "mssradmon",
                "entityType": "alarm",
                "entityId": level_label.lower(),
            },
        }
        result = _post(f"{base_url}/api/wa/send", api_key, payload)
        if result and result.get("success"):
            results.append(result.get("messageId"))
        else:
            results.append(None)
    return results


def health_check(base_url: str) -> dict | None:
    """msgService /api/health endpoint'ini sorgula."""
    return _get(f"{base_url}/api/health")
