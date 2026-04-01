# msgService Entegrasyon Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** mssRadMon alarm sistemine msgService üzerinden seviyeye göre yapılandırılabilir e-posta ve WhatsApp bildirimi ekle; SMTP kodu değişmeden kalsın.

**Architecture:** Yeni `app/msg_service.py` modülü stdlib `urllib.request` ile msgService REST API'sini çağırır; `AlarmManager._trigger_alarm` mevcut `_send_email` bloğunun yanına iki yeni private metod çağrısı alır; admin paneline yeni bir "msgService" bölümü ve üç API endpoint eklenir.

**Tech Stack:** Python 3.11 stdlib (`urllib.request`, `ssl`, `json`), FastAPI, asyncio executor, pytest + unittest.mock

---

## Dosya Haritası

| Eylem | Dosya | Sorumluluk |
|-------|-------|-----------|
| Oluştur | `app/msg_service.py` | msgService HTTP client — send_mail, send_whatsapp, health_check |
| Oluştur | `tests/test_msg_service.py` | msg_service modülü unit testleri |
| Değiştir | `app/config.py` | DEFAULTS'a 9 yeni key ekle |
| Değiştir | `app/alarm.py` | import + _send_msgservice_mail + _send_msgservice_wa + _trigger_alarm'da 2 çağrı |
| Değiştir | `app/routers/admin.py` | import + 3 yeni endpoint |
| Değiştir | `app/templates/admin.html` | Sidebar link + sec-msgservice bölümü |
| Değiştir | `app/static/js/admin.js` | FIELDS, TOGGLE_FIELDS, event handler'lar |

---

## Task 1: `app/msg_service.py` — HTTP Client (TDD)

**Files:**
- Create: `tests/test_msg_service.py`
- Create: `app/msg_service.py`

- [ ] **Step 1: Test dosyasını oluştur**

```python
# tests/test_msg_service.py
"""app/msg_service.py unit testleri."""
import json
from unittest.mock import MagicMock, patch

import pytest

from app import msg_service


def _make_resp(data: dict):
    """urllib.request.urlopen context manager mock'u."""
    resp = MagicMock()
    resp.read.return_value = json.dumps(data).encode()
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


class TestSendMail:
    def test_returns_message_id_on_success(self):
        resp = _make_resp({"success": True, "messageId": "abc-123"})
        with patch("urllib.request.urlopen", return_value=resp):
            result = msg_service.send_mail(
                "http://localhost:3501", "key123",
                ["test@example.com"], "", "HIGH", 0.55, "GammaScout-01", ""
            )
        assert result == "abc-123"

    def test_returns_none_on_empty_to_list(self):
        result = msg_service.send_mail(
            "http://localhost:3501", "key123", [], "", "HIGH", 0.55, "GammaScout-01", ""
        )
        assert result is None

    def test_returns_none_on_missing_url(self):
        result = msg_service.send_mail(
            "", "key123", ["a@b.com"], "", "HIGH", 0.55, "GammaScout-01", ""
        )
        assert result is None

    def test_returns_none_on_missing_api_key(self):
        result = msg_service.send_mail(
            "http://localhost:3501", "", ["a@b.com"], "", "HIGH", 0.55, "GammaScout-01", ""
        )
        assert result is None

    def test_returns_none_on_connection_error(self):
        with patch("urllib.request.urlopen", side_effect=Exception("connection refused")):
            result = msg_service.send_mail(
                "http://localhost:3501", "key123",
                ["a@b.com"], "", "HIGH", 0.55, "GammaScout-01", ""
            )
        assert result is None

    def test_returns_none_when_success_false(self):
        resp = _make_resp({"success": False, "error": "Invalid key"})
        with patch("urllib.request.urlopen", return_value=resp):
            result = msg_service.send_mail(
                "http://localhost:3501", "key123",
                ["a@b.com"], "", "HIGH", 0.55, "GammaScout-01", ""
            )
        assert result is None

    def test_includes_reply_to_when_set(self):
        resp = _make_resp({"success": True, "messageId": "x1"})
        captured = {}
        original_urlopen = __import__("urllib.request", fromlist=["urlopen"]).urlopen

        def fake_urlopen(req, **kwargs):
            import json as _json
            captured["body"] = _json.loads(req.data.decode())
            return resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            msg_service.send_mail(
                "http://localhost:3501", "key123",
                ["a@b.com"], "noreply@test.com", "HIGH", 0.55, "GammaScout-01", ""
            )
        assert captured["body"].get("replyTo") == "noreply@test.com"

    def test_omits_reply_to_when_empty(self):
        resp = _make_resp({"success": True, "messageId": "x2"})
        captured = {}

        def fake_urlopen(req, **kwargs):
            import json as _json
            captured["body"] = _json.loads(req.data.decode())
            return resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            msg_service.send_mail(
                "http://localhost:3501", "key123",
                ["a@b.com"], "", "HIGH", 0.55, "GammaScout-01", ""
            )
        assert "replyTo" not in captured["body"]


class TestSendWhatsapp:
    def test_returns_message_ids_on_success(self):
        resp = _make_resp({"success": True, "messageId": "wa-001"})
        with patch("urllib.request.urlopen", return_value=resp):
            result = msg_service.send_whatsapp(
                "http://localhost:3501", "key123",
                ["905551234567"], "HIGH", 0.55, "GammaScout-01"
            )
        assert result == ["wa-001"]

    def test_returns_empty_on_empty_phone_list(self):
        result = msg_service.send_whatsapp(
            "http://localhost:3501", "key123", [], "HIGH", 0.55, "GammaScout-01"
        )
        assert result == []

    def test_returns_empty_on_missing_url(self):
        result = msg_service.send_whatsapp(
            "", "key123", ["905551234567"], "HIGH", 0.55, "GammaScout-01"
        )
        assert result == []

    def test_returns_none_entries_on_failure(self):
        with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            result = msg_service.send_whatsapp(
                "http://localhost:3501", "key123",
                ["905551234567", "905559876543"], "HIGH", 0.55, "GammaScout-01"
            )
        assert result == [None, None]

    def test_sends_one_request_per_phone(self):
        call_count = 0
        resp = _make_resp({"success": True, "messageId": "wa-x"})

        def fake_urlopen(req, **kwargs):
            nonlocal call_count
            call_count += 1
            return resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            msg_service.send_whatsapp(
                "http://localhost:3501", "key123",
                ["905551111111", "905552222222", "905553333333"],
                "HIGH", 0.55, "GammaScout-01"
            )
        assert call_count == 3


class TestHealthCheck:
    def test_returns_health_data(self):
        data = {"status": "ok", "version": "0.2.18", "uptime": 3600}
        resp = _make_resp(data)
        with patch("urllib.request.urlopen", return_value=resp):
            result = msg_service.health_check("http://localhost:3501")
        assert result == data

    def test_returns_none_on_error(self):
        with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            result = msg_service.health_check("http://localhost:3501")
        assert result is None
```

- [ ] **Step 2: Testleri çalıştır — hepsinin FAIL ettiğini doğrula**

```bash
cd /home/mssadmin/mssRadMon && source .venv/bin/activate
pytest tests/test_msg_service.py -v 2>&1 | head -30
```

Beklenen çıktı: `ModuleNotFoundError` veya `ImportError` — modül henüz yok.

- [ ] **Step 3: `app/msg_service.py` oluştur**

```python
# app/msg_service.py
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
```

- [ ] **Step 4: Testleri çalıştır — hepsinin geçtiğini doğrula**

```bash
pytest tests/test_msg_service.py -v
```

Beklenen çıktı: 13 test, hepsi `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add app/msg_service.py tests/test_msg_service.py
git commit -m "feat: msgService HTTP client modülü (send_mail, send_whatsapp, health_check)"
```

---

## Task 2: `app/config.py` — Yeni DEFAULTS Key'leri

**Files:**
- Modify: `app/config.py`

- [ ] **Step 1: DEFAULTS dict'e 9 yeni key ekle**

`app/config.py` içindeki `DEFAULTS` dict'inin `"shifts": "[]",` satırından önce şunu ekle:

```python
    "msg_service_url": "http://192.168.88.112:3501",
    "msg_service_api_key": "",
    "msg_service_mail_enabled": "false",
    "msg_service_wa_enabled": "false",
    "msg_service_reply_to": "",
    "msg_service_high_mail_to": "",
    "msg_service_high_wa_to": "",
    "msg_service_high_high_mail_to": "",
    "msg_service_high_high_wa_to": "",
```

- [ ] **Step 2: Mevcut testlerin hâlâ geçtiğini doğrula**

```bash
pytest tests/test_config.py -v
```

Beklenen çıktı: tüm testler `PASSED`.

- [ ] **Step 3: Commit**

```bash
git add app/config.py
git commit -m "feat: config DEFAULTS'a msgService key'leri ekle"
```

---

## Task 3: `app/alarm.py` — msgService Bildirim Metodları

**Files:**
- Modify: `app/alarm.py`

- [ ] **Step 1: `app/alarm.py` başına import ekle**

Dosyanın `import asyncio` satırından hemen sonrasına ekle:

```python
from app import msg_service
```

- [ ] **Step 2: `_trigger_alarm` metoduna iki çağrı ekle**

`alarm.py:157` — `logger.warning(...)` satırından hemen **önce** şunu ekle:

```python
        # msgService bildirimleri
        await self._send_msgservice_mail(level, dose_rate)
        await self._send_msgservice_wa(level, dose_rate)
```

Bağlam (değişiklik sonrası `_trigger_alarm` sonu):

```python
        # E-posta gonder (SMTP)
        email_enabled = await self._config.get("alarm_email_enabled")
        if email_enabled == "true":
            await self._send_email(level, dose_rate)

        # msgService bildirimleri
        await self._send_msgservice_mail(level, dose_rate)
        await self._send_msgservice_wa(level, dose_rate)

        logger.warning("ALARM %s: %.3f µSv/h — aksiyonlar: %s", level.value, dose_rate, action_taken)
```

- [ ] **Step 3: İki private metod ekle — `shutdown` metodundan hemen önce**

```python
    async def _send_msgservice_mail(self, level: AlarmLevel, dose_rate: float):
        """msgService uzerinden alarm maili gonder."""
        if await self._config.get("msg_service_mail_enabled") != "true":
            return
        base_url = await self._config.get("msg_service_url") or ""
        api_key = await self._config.get("msg_service_api_key") or ""
        reply_to = await self._config.get("msg_service_reply_to") or ""
        to_raw = await self._config.get(f"msg_service_{level.value}_mail_to") or ""
        to_list = [e.strip() for e in to_raw.split(",") if e.strip()]
        if not to_list:
            return
        device_name = await self._config.get("device_name") or "GammaScout-01"
        device_location = await self._config.get("device_location") or ""
        label = level.value.upper().replace("_", "-")
        loop = asyncio.get_event_loop()
        msg_id = await loop.run_in_executor(
            None,
            lambda: msg_service.send_mail(
                base_url, api_key, to_list, reply_to,
                label, dose_rate, device_name, device_location,
            ),
        )
        if msg_id:
            logger.info("msgService mail gonderildi: %s -> %s", level.value, msg_id)
        else:
            logger.warning("msgService mail gonderilemedi (level=%s)", level.value)

    async def _send_msgservice_wa(self, level: AlarmLevel, dose_rate: float):
        """msgService uzerinden alarm WA mesaji gonder."""
        if await self._config.get("msg_service_wa_enabled") != "true":
            return
        base_url = await self._config.get("msg_service_url") or ""
        api_key = await self._config.get("msg_service_api_key") or ""
        to_raw = await self._config.get(f"msg_service_{level.value}_wa_to") or ""
        phone_list = [p.strip() for p in to_raw.split(",") if p.strip()]
        if not phone_list:
            return
        device_name = await self._config.get("device_name") or "GammaScout-01"
        label = level.value.upper().replace("_", "-")
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None,
            lambda: msg_service.send_whatsapp(
                base_url, api_key, phone_list, label, dose_rate, device_name,
            ),
        )
        sent = sum(1 for r in results if r)
        logger.info(
            "msgService WA gonderildi: %d/%d (level=%s)", sent, len(phone_list), level.value
        )
```

- [ ] **Step 4: Mevcut alarm testlerinin hâlâ geçtiğini doğrula**

```bash
pytest tests/test_alarm.py -v
```

Beklenen çıktı: tüm testler `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add app/alarm.py
git commit -m "feat: alarm.py'e msgService mail ve WA bildirim metodları ekle"
```

---

## Task 4: `app/routers/admin.py` — Üç Yeni Endpoint

**Files:**
- Modify: `app/routers/admin.py`

- [ ] **Step 1: Import'ları güncelle**

Dosyanın başındaki import bloğunu şununla değiştir:

```python
"""Admin API endpointleri — ayar yönetimi ve WiFi kontrolü."""
import asyncio

from fastapi import APIRouter, Request

from app import msg_service, wifi
```

- [ ] **Step 2: Üç yeni endpoint ekle — dosyanın sonuna**

```python
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
```

- [ ] **Step 3: Admin testlerinin hâlâ geçtiğini doğrula**

```bash
pytest tests/test_admin.py -v
```

Beklenen çıktı: tüm testler `PASSED`.

- [ ] **Step 4: Commit**

```bash
git add app/routers/admin.py
git commit -m "feat: admin API'ye msgService health/test-mail/test-wa endpoint'leri ekle"
```

---

## Task 5: Admin Panel UI

**Files:**
- Modify: `app/templates/admin.html`
- Modify: `app/static/js/admin.js`

- [ ] **Step 1: `admin.html` sidebar'a "msgService" linki ekle**

Sidebar'daki `data-section="email"` linkinden hemen sonrasına ekle:

```html
            <a href="#" class="sidebar-link" data-section="msgservice">msgService</a>
```

- [ ] **Step 2: `admin.html`'e yeni section ekle — `<!-- Uzak Log -->` yorumundan hemen önce**

```html
        <!-- msgService -->
        <section class="admin-section" id="sec-msgservice">
            <h2 class="section-title">msgService Bildirimleri</h2>

            <div class="card">
                <div class="card-title">Genel Ayarlar</div>
                <div class="dashboard-grid">
                    <div class="form-group">
                        <label for="msg_service_url">Servis URL</label>
                        <input type="url" id="msg_service_url" placeholder="http://192.168.88.112:3501">
                    </div>
                    <div class="form-group">
                        <label for="msg_service_api_key">API Key</label>
                        <input type="text" id="msg_service_api_key" placeholder="pk_mssradmon_...">
                    </div>
                </div>
                <div class="form-group">
                    <label for="msg_service_reply_to">Reply-To (opsiyonel)</label>
                    <input type="email" id="msg_service_reply_to" placeholder="noreply@msspektral.com">
                </div>
                <div class="dashboard-grid">
                    <div class="form-group">
                        <label>
                            <span class="toggle">
                                <input type="checkbox" id="msg_service_mail_enabled">
                                <span class="slider"></span>
                            </span>
                            E-posta Bildirimi Aktif
                        </label>
                    </div>
                    <div class="form-group">
                        <label>
                            <span class="toggle">
                                <input type="checkbox" id="msg_service_wa_enabled">
                                <span class="slider"></span>
                            </span>
                            WhatsApp Bildirimi Aktif
                        </label>
                    </div>
                </div>
            </div>

            <div class="card">
                <div class="card-title">HIGH Seviye Alıcılar</div>
                <div class="form-group">
                    <label for="msg_service_high_mail_to">E-posta Alıcıları (virgülle ayrılmış)</label>
                    <input type="text" id="msg_service_high_mail_to" placeholder="a@msspektral.com, b@msspektral.com">
                </div>
                <div class="form-group">
                    <label for="msg_service_high_wa_to">WhatsApp Numaraları (virgülle, E.164 formatsız)</label>
                    <input type="text" id="msg_service_high_wa_to" placeholder="905551234567, 905559876543">
                </div>
            </div>

            <div class="card">
                <div class="card-title">HIGH-HIGH Seviye Alıcılar</div>
                <div class="form-group">
                    <label for="msg_service_high_high_mail_to">E-posta Alıcıları (virgülle ayrılmış)</label>
                    <input type="text" id="msg_service_high_high_mail_to" placeholder="a@msspektral.com, b@msspektral.com">
                </div>
                <div class="form-group">
                    <label for="msg_service_high_high_wa_to">WhatsApp Numaraları (virgülle, E.164 formatsız)</label>
                    <input type="text" id="msg_service_high_high_wa_to" placeholder="905551234567, 905559876543">
                </div>
            </div>

            <div style="display:flex; align-items:center; gap:0.75rem; flex-wrap:wrap; margin-bottom:1rem;">
                <button class="btn save-section-btn">Ayarları Kaydet</button>
                <span class="save-msg save-section-msg">Ayarlar kaydedildi.</span>
            </div>

            <div style="display:flex; align-items:center; gap:0.75rem; flex-wrap:wrap;">
                <button class="btn" id="msgHealthBtn" style="background:var(--surface);border:1px solid var(--accent);">Bağlantı Testi</button>
                <button class="btn" id="msgTestMailHighBtn" style="background:var(--surface);border:1px solid rgba(255,255,255,0.15);">Test Mail (HIGH)</button>
                <button class="btn" id="msgTestMailHHBtn" style="background:var(--surface);border:1px solid rgba(255,255,255,0.15);">Test Mail (HIGH-HIGH)</button>
                <button class="btn" id="msgTestWaHighBtn" style="background:var(--surface);border:1px solid rgba(255,255,255,0.15);">Test WA (HIGH)</button>
                <button class="btn" id="msgTestWaHHBtn" style="background:var(--surface);border:1px solid rgba(255,255,255,0.15);">Test WA (HIGH-HIGH)</button>
            </div>
            <div id="msgServiceResult" style="margin-top:0.75rem;font-size:0.85rem;min-height:1.2rem;"></div>
        </section>

```

- [ ] **Step 3: `admin.js` FIELDS dizisine yeni key'leri ekle**

`admin.js:40` — `"alarm_email_to", "smtp_host", ...` satırından hemen sonra (aynı satıra veya yeni satır):

```js
const FIELDS = [
    "device_name", "device_location", "device_serial",
    "sampling_interval", "calibration_factor",
    "threshold_high", "threshold_high_high",
    "threshold_high_duration", "threshold_high_high_duration",
    "alarm_high_actions", "alarm_high_high_actions",
    "gpio_buzzer_pin", "gpio_light_pin", "gpio_emergency_pin",
    "alarm_buzzer_enabled", "alarm_email_enabled",
    "alarm_email_to", "smtp_host", "smtp_port", "smtp_user", "smtp_pass",
    "remote_log_enabled", "remote_log_url", "remote_log_api_key",
    "msg_service_url", "msg_service_api_key", "msg_service_reply_to",
    "msg_service_mail_enabled", "msg_service_wa_enabled",
    "msg_service_high_mail_to", "msg_service_high_wa_to",
    "msg_service_high_high_mail_to", "msg_service_high_high_wa_to",
];
```

- [ ] **Step 4: `admin.js` TOGGLE_FIELDS'a yeni toggle'ları ekle**

```js
const TOGGLE_FIELDS = [
    "alarm_buzzer_enabled", "alarm_email_enabled", "remote_log_enabled",
    "msg_service_mail_enabled", "msg_service_wa_enabled",
];
```

- [ ] **Step 5: `admin.js` dosyasının sonuna msgService event handler'larını ekle**

Dosyanın en sonuna (mevcut son satırdan sonra) ekle:

```js
// --- msgService ---

async function msgServiceAction(endpoint, body, resultEl) {
    resultEl.textContent = "İşleniyor...";
    resultEl.style.color = "var(--text-dim)";
    try {
        const res = await fetch(endpoint, {
            method: endpoint.includes("health") ? "GET" : "POST",
            headers: { "Content-Type": "application/json" },
            body: endpoint.includes("health") ? undefined : JSON.stringify(body),
        });
        const data = await res.json();
        if (data.ok) {
            let msg = "Başarılı.";
            if (data.version) msg = `Bağlantı OK — v${data.version} | smtp:${data.smtp || "?"} | wa:${data.whatsapp || "?"}`;
            if (data.messageId) msg = `Gönderildi (ID: ${data.messageId})`;
            if (data.sent !== undefined) msg = `Gönderildi: ${data.sent}/${data.total}`;
            resultEl.textContent = msg;
            resultEl.style.color = "var(--green)";
        } else {
            resultEl.textContent = `Hata: ${data.message || "Bilinmeyen hata"}`;
            resultEl.style.color = "var(--red)";
        }
    } catch (e) {
        resultEl.textContent = `İstek hatası: ${e.message}`;
        resultEl.style.color = "var(--red)";
    }
}

const _msgResult = () => document.getElementById("msgServiceResult");

document.getElementById("msgHealthBtn").addEventListener("click", () =>
    msgServiceAction("/api/msgservice/health", null, _msgResult()));

document.getElementById("msgTestMailHighBtn").addEventListener("click", () =>
    msgServiceAction("/api/msgservice/test-mail", { level: "high" }, _msgResult()));

document.getElementById("msgTestMailHHBtn").addEventListener("click", () =>
    msgServiceAction("/api/msgservice/test-mail", { level: "high_high" }, _msgResult()));

document.getElementById("msgTestWaHighBtn").addEventListener("click", () =>
    msgServiceAction("/api/msgservice/test-wa", { level: "high" }, _msgResult()));

document.getElementById("msgTestWaHHBtn").addEventListener("click", () =>
    msgServiceAction("/api/msgservice/test-wa", { level: "high_high" }, _msgResult()));
```

- [ ] **Step 6: Tüm testleri çalıştır**

```bash
pytest -v 2>&1 | tail -20
```

Beklenen çıktı: tüm testler `PASSED`, 0 hata.

- [ ] **Step 7: Commit**

```bash
git add app/templates/admin.html app/static/js/admin.js
git commit -m "feat: admin panele msgService bildirimleri bölümü ekle"
```

---

## Son Doğrulama

- [ ] **Tüm testleri son kez çalıştır**

```bash
pytest -v
```

Beklenen: tüm testler `PASSED`.

- [ ] **Uygulamayı başlat ve manuel kontrol**

```bash
source .venv/bin/activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8090 --reload
```

1. `http://<ip>:8090/admin` → "msgService" sidebar linki görünüyor mu?
2. Bölüme gir → alanlar yükleniyor mu?
3. "Bağlantı Testi" → `{"ok": true, "version": "..."}` dönüyor mu?
4. Alıcıları kaydet → "Ayarlar kaydedildi" görünüyor mu?
5. "Test Mail (HIGH)" → mail kuyrukta görünüyor mu?
