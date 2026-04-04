# SSL / CA Trust Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** CA sertifikasını sisteme trust et, CA sunucudan hostname bazlı SSL sertifikası talep et, uvicorn'u HTTPS ile başlat, admin panelden yönet.

**Architecture:** Yeni `app/ssl.py` modülü SSL iş mantığını (CA trust, sertifika talep, durum kontrolü, servis restart) barındırır. Endpoint'ler `app/main.py`'de tanımlanır. Admin panelde yeni "SSL Yönetimi" bölümü eklenir. Uvicorn'a `--ssl-keyfile/--ssl-certfile` parametreleri systemd servis dosyası üzerinden verilir.

**Tech Stack:** Python 3.11+, FastAPI, httpx (async HTTP client), subprocess (openssl, systemctl, update-ca-certificates), aiosqlite

---

### Task 1: Config defaults — SSL ayar anahtarları

**Files:**
- Modify: `app/config.py:4-38`

- [ ] **Step 1: Add SSL defaults to config**

`app/config.py` — DEFAULTS dict'ine üç yeni anahtar ekle:

```python
# Mevcut son satırdan sonra (api_key satırından sonra) ekle:
    "ca_server_url": "",
    "ca_api_key": "",
    "ssl_enabled": "false",
```

- [ ] **Step 2: Verify config loads**

Run: `source .venv/bin/activate && python -c "from app.config import DEFAULTS; print('ca_server_url' in DEFAULTS, 'ca_api_key' in DEFAULTS, 'ssl_enabled' in DEFAULTS)"`

Expected: `True True True`

- [ ] **Step 3: Commit**

```bash
git add app/config.py
git commit -m "feat: SSL config defaults — ca_server_url, ca_api_key, ssl_enabled"
```

---

### Task 2: SSL modülü — durum kontrolü

**Files:**
- Create: `app/ssl.py`
- Create: `tests/test_ssl.py`

- [ ] **Step 1: Write failing test for ssl_status**

`tests/test_ssl.py`:

```python
"""SSL modülü testleri."""
import os
import tempfile
import pytest
import pytest_asyncio

from app.db import Database
from app.config import Config


@pytest_asyncio.fixture
async def ssl_deps(test_db_path):
    db = Database(test_db_path)
    await db.init()
    config = Config(db)
    await config.init()
    yield db, config
    await db.close()


@pytest.mark.asyncio
async def test_ssl_status_no_cert(ssl_deps):
    """Sertifika yokken durum doğru dönmeli."""
    from app.ssl import SslManager

    db, config = ssl_deps
    mgr = SslManager(config=config, ssl_dir="/tmp/nonexistent_ssl_dir_test")
    status = await mgr.get_status()
    assert status["has_cert"] is False
    assert status["ssl_enabled"] is False
    assert status["ca_trusted"] is False


@pytest.mark.asyncio
async def test_ssl_status_with_cert(ssl_deps):
    """Sertifika varken durum doğru dönmeli."""
    from app.ssl import SslManager

    db, config = ssl_deps
    with tempfile.TemporaryDirectory() as tmpdir:
        # Dummy sertifika ve key oluştur
        os.system(
            f'openssl req -x509 -newkey rsa:2048 -keyout {tmpdir}/server.key '
            f'-out {tmpdir}/server.crt -days 365 -nodes '
            f'-subj "/CN=test.mss.local" 2>/dev/null'
        )
        mgr = SslManager(config=config, ssl_dir=tmpdir)
        status = await mgr.get_status()
        assert status["has_cert"] is True
        assert status["subject"] is not None
        assert "test.mss.local" in status["subject"]
        assert status["expiry"] is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_ssl.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'app.ssl'`

- [ ] **Step 3: Write SslManager with get_status**

`app/ssl.py`:

```python
"""SSL yönetimi — CA trust, sertifika talep, durum kontrolü."""
import logging
import os
import subprocess

import httpx

from app.config import Config

logger = logging.getLogger(__name__)

CA_TRUST_PATH = "/usr/local/share/ca-certificates/mss-ca.crt"


class SslManager:
    def __init__(self, config: Config, ssl_dir: str = "data/ssl"):
        self._config = config
        self._ssl_dir = ssl_dir

    @property
    def cert_path(self) -> str:
        return os.path.join(self._ssl_dir, "server.crt")

    @property
    def key_path(self) -> str:
        return os.path.join(self._ssl_dir, "server.key")

    @property
    def ca_path(self) -> str:
        return os.path.join(self._ssl_dir, "ca.crt")

    async def get_status(self) -> dict:
        """Mevcut SSL durumunu döndür."""
        ssl_enabled = (await self._config.get("ssl_enabled")) == "true"
        ca_trusted = os.path.isfile(CA_TRUST_PATH)
        has_cert = os.path.isfile(self.cert_path) and os.path.isfile(self.key_path)

        expiry = None
        subject = None
        if has_cert:
            expiry, subject = self._parse_cert_info()

        ca_server = await self._check_ca_server()

        return {
            "ca_trusted": ca_trusted,
            "has_cert": has_cert,
            "ssl_enabled": ssl_enabled,
            "expiry": expiry,
            "subject": subject,
            "ca_server": ca_server,
        }

    def _parse_cert_info(self) -> tuple[str | None, str | None]:
        """openssl ile sertifika bilgilerini parse et."""
        try:
            info = subprocess.check_output(
                ["openssl", "x509", "-in", self.cert_path, "-noout", "-enddate", "-subject"],
                text=True,
            )
            expiry = None
            subject = None
            for line in info.strip().splitlines():
                if line.startswith("notAfter="):
                    expiry = line.split("=", 1)[1].strip()
                if line.startswith("subject="):
                    subject = line.split("=", 1)[1].strip()
            return expiry, subject
        except Exception as e:
            logger.warning("Sertifika bilgisi okunamadı: %s", e)
            return None, None

    async def _check_ca_server(self) -> dict:
        """CA sunucu erişilebilirliğini kontrol et."""
        ca_url = await self._config.get("ca_server_url")
        if not ca_url:
            return {"reachable": False, "initialized": False}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(f"{ca_url}/api/ca/status")
                data = res.json()
                return {"reachable": True, "initialized": data.get("initialized", False)}
        except Exception:
            return {"reachable": False, "initialized": False}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_ssl.py -v`

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add app/ssl.py tests/test_ssl.py
git commit -m "feat: SslManager — get_status ile SSL durum kontrolü"
```

---

### Task 3: SSL modülü — CA trust

**Files:**
- Modify: `app/ssl.py`
- Modify: `tests/test_ssl.py`

- [ ] **Step 1: Write failing test for trust_ca**

Append to `tests/test_ssl.py`:

```python
@pytest.mark.asyncio
async def test_trust_ca_no_url(ssl_deps):
    """CA URL yokken trust_ca hata dönmeli."""
    from app.ssl import SslManager

    db, config = ssl_deps
    mgr = SslManager(config=config, ssl_dir="/tmp/test_ssl_trust")
    result = await mgr.trust_ca()
    assert result["ok"] is False
    assert "url" in result["message"].lower() or "URL" in result["message"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_ssl.py::test_trust_ca_no_url -v`

Expected: FAIL — `AttributeError: 'SslManager' object has no attribute 'trust_ca'`

- [ ] **Step 3: Implement trust_ca method**

Add to `app/ssl.py` class `SslManager`:

```python
    async def trust_ca(self) -> dict:
        """CA sertifikasını indir ve sisteme güvenilir olarak ekle."""
        ca_url = await self._config.get("ca_server_url")
        if not ca_url:
            return {"ok": False, "message": "CA sunucu URL ayarlanmamış"}

        # 1. CA sertifikasını indir
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(f"{ca_url}/api/ca/certificate")
                res.raise_for_status()
                pem_data = res.text
        except Exception as e:
            return {"ok": False, "message": f"CA sertifikası indirilemedi: {e}"}

        # 2. data/ssl/ca.crt olarak kaydet
        os.makedirs(self._ssl_dir, exist_ok=True)
        with open(self.ca_path, "w") as f:
            f.write(pem_data)

        # 3. Sisteme trust olarak ekle
        try:
            subprocess.run(
                ["sudo", "cp", self.ca_path, CA_TRUST_PATH],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["sudo", "update-ca-certificates"],
                check=True, capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            return {"ok": False, "message": f"Sistem trust hatası: {e.stderr.decode().strip()}"}

        logger.info("CA sertifikası sisteme güvenilir olarak eklendi")
        return {"ok": True, "message": "CA sertifikası güvenilir olarak eklendi"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && pytest tests/test_ssl.py::test_trust_ca_no_url -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/ssl.py tests/test_ssl.py
git commit -m "feat: SslManager.trust_ca — CA sertifikasını indir ve sisteme trust et"
```

---

### Task 4: SSL modülü — sertifika talep ve servis restart

**Files:**
- Modify: `app/ssl.py`
- Modify: `tests/test_ssl.py`

- [ ] **Step 1: Write failing test for request_cert**

Append to `tests/test_ssl.py`:

```python
@pytest.mark.asyncio
async def test_request_cert_no_url(ssl_deps):
    """CA URL yokken request_cert hata dönmeli."""
    from app.ssl import SslManager

    db, config = ssl_deps
    mgr = SslManager(config=config, ssl_dir="/tmp/test_ssl_req")
    result = await mgr.request_cert("test.mss.local")
    assert result["ok"] is False


@pytest.mark.asyncio
async def test_request_cert_no_api_key(ssl_deps):
    """API key yokken request_cert hata dönmeli."""
    from app.ssl import SslManager

    db, config = ssl_deps
    await config.set("ca_server_url", "http://fake:3020")
    mgr = SslManager(config=config, ssl_dir="/tmp/test_ssl_req2")
    result = await mgr.request_cert("test.mss.local")
    assert result["ok"] is False
    assert "api key" in result["message"].lower() or "API" in result["message"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_ssl.py -k "request_cert" -v`

Expected: FAIL — `AttributeError: 'SslManager' object has no attribute 'request_cert'`

- [ ] **Step 3: Implement request_cert and _restart_service**

Add to `app/ssl.py` class `SslManager`:

```python
    async def request_cert(self, hostname: str) -> dict:
        """CA sunucudan sertifika talep et, kaydet, servisi SSL ile restart et."""
        ca_url = await self._config.get("ca_server_url")
        if not ca_url:
            return {"ok": False, "message": "CA sunucu URL ayarlanmamış"}

        ca_api_key = await self._config.get("ca_api_key")
        if not ca_api_key:
            return {"ok": False, "message": "CA API key ayarlanmamış"}

        # 1. Sertifika talep et
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.post(
                    f"{ca_url}/api/certificates/request",
                    json={
                        "hostname": hostname,
                        "ipAddress": "",
                        "appName": "mssradmon",
                    },
                    headers={"X-API-Key": ca_api_key},
                )
                res.raise_for_status()
                data = res.json()
        except Exception as e:
            return {"ok": False, "message": f"Sertifika talebi başarısız: {e}"}

        # 2. Dosyaları kaydet
        os.makedirs(self._ssl_dir, exist_ok=True)

        key_path = self.key_path
        with open(key_path, "w") as f:
            f.write(data["key"])
        os.chmod(key_path, 0o600)

        with open(self.cert_path, "w") as f:
            f.write(data["cert"])

        with open(self.ca_path, "w") as f:
            f.write(data["caCert"])

        # 3. ssl_enabled = true
        await self._config.set("ssl_enabled", "true")

        # 4. Servis restart
        restart_ok = self._restart_service()

        expiry = data.get("expiresAt", "")
        logger.info("SSL sertifikası yüklendi: %s (expiry: %s)", hostname, expiry)

        if not restart_ok:
            return {
                "ok": True,
                "message": "Sertifika kaydedildi ancak servis yeniden başlatılamadı — manuel restart gerekli",
                "expiry": expiry,
            }

        return {
            "ok": True,
            "message": "Sertifika yüklendi, HTTPS aktif — sayfa birkaç saniye içinde yeniden yüklenecek",
            "expiry": expiry,
        }

    def _restart_service(self) -> bool:
        """Systemd servisini SSL parametreleriyle restart et."""
        service_src = os.path.join(os.path.dirname(__file__), "..", "systemd", "mssradmon-ssl.service")
        service_src = os.path.abspath(service_src)
        try:
            subprocess.run(
                ["sudo", "cp", service_src, "/etc/systemd/system/mssradmon.service"],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["sudo", "systemctl", "daemon-reload"],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["sudo", "systemctl", "restart", "mssradmon"],
                check=True, capture_output=True,
            )
            return True
        except subprocess.CalledProcessError as e:
            logger.error("Servis restart hatası: %s", e.stderr.decode().strip())
            return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_ssl.py -k "request_cert" -v`

Expected: 2 passed

- [ ] **Step 5: Create SSL systemd service file**

`systemd/mssradmon-ssl.service`:

```ini
[Unit]
Description=mssRadMon - GammaScout Radyasyon Monitörü (HTTPS)
After=network.target

[Service]
Type=simple
User=mssadmin
WorkingDirectory=/home/mssadmin/mssRadMon
ExecStart=/home/mssadmin/mssRadMon/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8090 --ssl-keyfile /home/mssadmin/mssRadMon/data/ssl/server.key --ssl-certfile /home/mssadmin/mssRadMon/data/ssl/server.crt
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 6: Commit**

```bash
git add app/ssl.py tests/test_ssl.py systemd/mssradmon-ssl.service
git commit -m "feat: SslManager.request_cert + systemd SSL servis dosyası"
```

---

### Task 5: Backend endpoint'leri — main.py

**Files:**
- Modify: `app/main.py`

- [ ] **Step 1: Add SslManager to lifespan**

In `app/main.py`, add import at top:

```python
from app.ssl import SslManager
```

In lifespan, after `app.state.shift_manager = shift_manager` (around line 91), add:

```python
        ssl_manager = SslManager(config=config)
        app.state.ssl_manager = ssl_manager
```

- [ ] **Step 2: Add SSL endpoint'leri**

In `app/main.py`, after the `generate_api_key` endpoint (after line 237), add:

```python
    @app.get("/api/ssl/status", include_in_schema=False)
    async def ssl_status(
        request: Request,
        _user: dict = Depends(require_admin),
    ):
        return await request.app.state.ssl_manager.get_status()

    @app.post("/api/ssl/trust-ca", include_in_schema=False)
    async def ssl_trust_ca(
        request: Request,
        _user: dict = Depends(require_admin),
    ):
        return await request.app.state.ssl_manager.trust_ca()

    @app.post("/api/ssl/request", include_in_schema=False)
    async def ssl_request_cert(
        request: Request,
        body: dict,
        _user: dict = Depends(require_admin),
    ):
        hostname = body.get("hostname", "").strip()
        if not hostname:
            raise HTTPException(400, detail="hostname zorunlu")
        return await request.app.state.ssl_manager.request_cert(hostname)
```

- [ ] **Step 3: Run existing tests to ensure no regression**

Run: `source .venv/bin/activate && pytest tests/test_frontend_flows.py -v --tb=short`

Expected: All 48 tests pass

- [ ] **Step 4: Commit**

```bash
git add app/main.py
git commit -m "feat: SSL endpoint'leri — /api/ssl/status, trust-ca, request"
```

---

### Task 6: Entegrasyon testleri — SSL endpoint'leri

**Files:**
- Create: `tests/test_ssl_endpoints.py`

- [ ] **Step 1: Write endpoint tests**

`tests/test_ssl_endpoints.py`:

```python
"""SSL endpoint entegrasyon testleri."""
import pytest
from httpx import AsyncClient

from app.auth import _sign_cookie, COOKIE_NAME


def _admin_cookies(username: str = "mssadmin") -> dict:
    return {COOKIE_NAME: _sign_cookie(username)}


class TestSslStatus:

    @pytest.mark.asyncio
    async def test_status_requires_admin(self, test_client: AsyncClient):
        res = await test_client.get("/api/ssl/status")
        assert res.status_code == 401

    @pytest.mark.asyncio
    async def test_status_returns_fields(self, test_client: AsyncClient):
        res = await test_client.get("/api/ssl/status", cookies=_admin_cookies())
        assert res.status_code == 200
        data = res.json()
        assert "ca_trusted" in data
        assert "has_cert" in data
        assert "ssl_enabled" in data
        assert "ca_server" in data
        assert data["ssl_enabled"] is False
        assert data["has_cert"] is False


class TestSslTrustCa:

    @pytest.mark.asyncio
    async def test_trust_ca_requires_admin(self, test_client: AsyncClient):
        res = await test_client.post("/api/ssl/trust-ca")
        assert res.status_code == 401

    @pytest.mark.asyncio
    async def test_trust_ca_no_url(self, test_client: AsyncClient):
        res = await test_client.post("/api/ssl/trust-ca", cookies=_admin_cookies())
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is False


class TestSslRequest:

    @pytest.mark.asyncio
    async def test_request_requires_admin(self, test_client: AsyncClient):
        res = await test_client.post("/api/ssl/request", json={"hostname": "test"})
        assert res.status_code == 401

    @pytest.mark.asyncio
    async def test_request_empty_hostname(self, test_client: AsyncClient):
        res = await test_client.post(
            "/api/ssl/request",
            json={"hostname": ""},
            cookies=_admin_cookies(),
        )
        assert res.status_code == 400

    @pytest.mark.asyncio
    async def test_request_no_ca_url(self, test_client: AsyncClient):
        res = await test_client.post(
            "/api/ssl/request",
            json={"hostname": "test.mss.local"},
            cookies=_admin_cookies(),
        )
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is False

    @pytest.mark.asyncio
    async def test_viewer_cannot_access(self, test_client: AsyncClient):
        # viewer oluştur
        await test_client.post(
            "/api/users",
            json={"username": "sslviewer", "password": "Pass1", "role": "viewer"},
            cookies=_admin_cookies(),
        )
        res = await test_client.get(
            "/api/ssl/status",
            cookies={COOKIE_NAME: _sign_cookie("sslviewer")},
        )
        assert res.status_code == 403
```

- [ ] **Step 2: Run endpoint tests**

Run: `source .venv/bin/activate && pytest tests/test_ssl_endpoints.py -v`

Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add tests/test_ssl_endpoints.py
git commit -m "test: SSL endpoint entegrasyon testleri"
```

---

### Task 7: Admin panel — HTML bölümü

**Files:**
- Modify: `app/templates/admin.html`

- [ ] **Step 1: Add sidebar link**

In `admin.html`, after the `api-access` link (line 17), add:

```html
            <a href="#" class="sidebar-link" data-section="ssl">SSL Yönetimi</a>
```

- [ ] **Step 2: Add SSL section HTML**

In `admin.html`, before the `<!-- Alarm Geçmişi -->` comment (before line 463), add:

```html
        <!-- SSL Yönetimi -->
        <section class="admin-section" id="sec-ssl">
            <h2 class="section-title">SSL Yönetimi</h2>

            <div class="card">
                <div class="card-title">Durum</div>
                <div id="sslStatusPanel" style="display:flex;flex-direction:column;gap:0.4rem;font-size:0.9rem;">
                    <div><span id="sslCaDot" class="conn-dot"></span> CA: <span id="sslCaText">—</span></div>
                    <div><span id="sslCertDot" class="conn-dot"></span> Sertifika: <span id="sslCertText">—</span></div>
                    <div><span id="sslHttpsDot" class="conn-dot"></span> HTTPS: <span id="sslHttpsText">—</span></div>
                </div>
            </div>

            <div class="card">
                <div class="card-title">CA Ayarları</div>
                <div class="form-group">
                    <label for="ca_server_url">CA Sunucu URL</label>
                    <input type="url" id="ca_server_url" placeholder="http://192.168.88.111:3020">
                </div>
                <div class="form-group">
                    <label for="ca_api_key">CA API Key</label>
                    <input type="password" id="ca_api_key" placeholder="CA sunucudan alınan API key">
                </div>
                <div style="display:flex;gap:0.5rem;align-items:center;flex-wrap:wrap;">
                    <button class="btn save-section-btn">Kaydet</button>
                    <span class="save-msg save-section-msg">Ayarlar kaydedildi.</span>
                    <button class="btn" id="sslCaTestBtn" style="background:var(--surface);border:1px solid var(--accent);color:var(--accent);">Bağlantı Testi</button>
                    <button class="btn" id="sslTrustCaBtn" style="background:var(--surface);border:1px solid var(--green);color:var(--green);">CA Sertifikasını Güvenilir Yap</button>
                </div>
                <span id="sslCaMsg" style="display:block;margin-top:0.5rem;font-size:0.85rem;"></span>
            </div>

            <div class="card">
                <div class="card-title">Sertifika Talebi</div>
                <div class="form-group">
                    <label for="sslHostname">Hostname</label>
                    <input type="text" id="sslHostname" placeholder="mssradmon.mss.local">
                </div>
                <button class="btn" id="sslRequestBtn">Sertifika Talep Et</button>
                <span id="sslRequestMsg" style="display:inline-block;margin-left:0.75rem;font-size:0.85rem;"></span>
                <p style="font-size:0.8rem;color:var(--text-dim);margin-top:1rem;">
                    ⚠ Sertifika talep edildiğinde servis yeniden başlatılır. Bağlantınız birkaç saniye kesilecektir.
                </p>
            </div>
        </section>
```

- [ ] **Step 3: Add SSL fields to FIELDS array and viewer disabling**

In the inline `<script>` block with viewer restrictions, add `#sslTrustCaBtn, #sslRequestBtn` to the disabled buttons selector:

```javascript
document.querySelectorAll(".save-section-btn, #saveBtn, #generateApiKeyBtn, #addUserBtn, #sslTrustCaBtn, #sslRequestBtn")
```

- [ ] **Step 4: Add SSL settings fields to admin.js FIELDS array**

In `admin.js` line 32-46, add to the FIELDS array:

```javascript
    "ca_server_url", "ca_api_key",
```

- [ ] **Step 5: Commit**

```bash
git add app/templates/admin.html app/static/js/admin.js
git commit -m "feat: admin panel SSL Yönetimi bölümü — HTML + sidebar"
```

---

### Task 8: Admin panel — JS handler'ları

**Files:**
- Modify: `app/static/js/admin.js`

- [ ] **Step 1: Add SSL JS code**

In `admin.js`, before the `// --- Init ---` section (before line 704), add:

```javascript
// --- SSL Yönetimi ---

async function loadSslStatus() {
    try {
        const res = await fetch("/api/ssl/status");
        if (!res.ok) return;
        const s = await res.json();

        const caDot = document.getElementById("sslCaDot");
        const caText = document.getElementById("sslCaText");
        caDot.className = "conn-dot " + (s.ca_trusted ? "connected" : "");
        caText.textContent = s.ca_trusted ? "Güvenilir" : "Güvenilmiyor";

        const certDot = document.getElementById("sslCertDot");
        const certText = document.getElementById("sslCertText");
        if (s.has_cert) {
            certDot.className = "conn-dot connected";
            let txt = "Aktif";
            if (s.expiry) txt += " (son geçerlilik: " + s.expiry + ")";
            certText.textContent = txt;
        } else {
            certDot.className = "conn-dot";
            certText.textContent = "Yok";
        }

        const httpsDot = document.getElementById("sslHttpsDot");
        const httpsText = document.getElementById("sslHttpsText");
        httpsDot.className = "conn-dot " + (s.ssl_enabled ? "connected" : "");
        httpsText.textContent = s.ssl_enabled ? "Aktif" : "Pasif";
    } catch (e) {
        console.error("SSL durum yüklenemedi:", e);
    }
}

document.getElementById("sslCaTestBtn").addEventListener("click", async () => {
    const msgEl = document.getElementById("sslCaMsg");
    msgEl.textContent = "Test ediliyor...";
    msgEl.style.color = "var(--text-dim)";
    // Önce ayarları kaydet
    await saveSettings(null);
    try {
        const res = await fetch("/api/ssl/status");
        const s = await res.json();
        if (s.ca_server && s.ca_server.reachable) {
            msgEl.textContent = "CA sunucu erişilebilir" + (s.ca_server.initialized ? " — CA aktif" : " — CA başlatılmamış");
            msgEl.style.color = "var(--green)";
        } else {
            msgEl.textContent = "CA sunucu erişilemez";
            msgEl.style.color = "var(--red)";
        }
    } catch (e) {
        msgEl.textContent = "Bağlantı hatası";
        msgEl.style.color = "var(--red)";
    }
});

document.getElementById("sslTrustCaBtn").addEventListener("click", async () => {
    const msgEl = document.getElementById("sslCaMsg");
    msgEl.textContent = "CA sertifikası yükleniyor...";
    msgEl.style.color = "var(--text-dim)";
    try {
        const res = await fetch("/api/ssl/trust-ca", { method: "POST" });
        const data = await res.json();
        msgEl.textContent = data.message;
        msgEl.style.color = data.ok ? "var(--green)" : "var(--red)";
        if (data.ok) loadSslStatus();
    } catch (e) {
        msgEl.textContent = "İstek hatası";
        msgEl.style.color = "var(--red)";
    }
});

document.getElementById("sslRequestBtn").addEventListener("click", async () => {
    const hostname = document.getElementById("sslHostname").value.trim();
    const msgEl = document.getElementById("sslRequestMsg");
    if (!hostname) {
        msgEl.textContent = "Hostname zorunlu";
        msgEl.style.color = "var(--red)";
        return;
    }
    if (!confirm("Sertifika talep edilecek ve servis yeniden başlatılacak. Devam?")) return;
    msgEl.textContent = "Sertifika talep ediliyor...";
    msgEl.style.color = "var(--text-dim)";
    try {
        const res = await fetch("/api/ssl/request", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ hostname }),
        });
        const data = await res.json();
        msgEl.textContent = data.message;
        msgEl.style.color = data.ok ? "var(--green)" : "var(--red)";
        if (data.ok) {
            setTimeout(() => {
                window.location.protocol = "https:";
                window.location.reload();
            }, 3000);
        }
    } catch (e) {
        msgEl.textContent = "İstek hatası";
        msgEl.style.color = "var(--red)";
    }
});
```

- [ ] **Step 2: Add loadSslStatus to init**

In the `// --- Init ---` section, add after `loadApiKey();`:

```javascript
if (USER_ROLE === "admin") loadSslStatus();
```

- [ ] **Step 3: Verify JS syntax**

Run: `node --check app/static/js/admin.js && echo "OK"`

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add app/static/js/admin.js
git commit -m "feat: admin.js SSL handler'ları — durum, CA trust, sertifika talebi"
```

---

### Task 9: httpx dependency kontrolü

**Files:**
- Check/modify: `requirements.txt` or `pyproject.toml`

- [ ] **Step 1: Check if httpx is installed**

Run: `source .venv/bin/activate && python -c "import httpx; print(httpx.__version__)"`

If `ModuleNotFoundError`:

Run: `source .venv/bin/activate && pip install httpx`

- [ ] **Step 2: Add to requirements if exists**

Run: `ls requirements.txt pyproject.toml 2>/dev/null`

If `requirements.txt` exists, add `httpx` line. If `pyproject.toml`, add to dependencies.

- [ ] **Step 3: Commit if changed**

```bash
git add requirements.txt  # or pyproject.toml
git commit -m "chore: httpx dependency eklendi"
```

---

### Task 10: Version bump + full test run

**Files:**
- Modify: `app/__version__.py`

- [ ] **Step 1: Bump version**

`app/__version__.py`:

```python
__version__ = "1.2.0"
```

(Minor bump — yeni özellik)

- [ ] **Step 2: Run all tests**

Run: `source .venv/bin/activate && pytest tests/test_ssl.py tests/test_ssl_endpoints.py tests/test_frontend_flows.py -v --tb=short`

Expected: All tests pass

- [ ] **Step 3: Verify JS syntax**

Run: `node --check app/static/js/admin.js && echo "OK"`

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add app/__version__.py
git commit -m "feat: v1.2.0 — SSL/CA trust yönetimi"
```
