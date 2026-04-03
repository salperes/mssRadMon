# API Key Auth + Kullanıcı Yönetimi Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tüm `/api/*` endpoint'lerini API key ile koru, rol tabanlı kullanıcı yönetimi ekle, admin panele API Erişimi ve Kullanıcılar bölümlerini ekle.

**Architecture:** `app/auth.py` yeni dosyası tüm auth logic'i barındırır (cookie, API key, rol kontrolü). Router'lara `Depends(verify_api_key)` eklenir. Kullanıcılar `users` tablosunda tutulur, hardcoded credentials kaldırılır. Cookie auth ve API key alternatif yollar olarak çalışır — admin panel JS cookie kullanmaya devam eder, manager API key kullanır.

**Tech Stack:** FastAPI Depends, hashlib.pbkdf2_hmac, secrets.token_hex, aiosqlite, vanilla JS

---

## Dosya Değişiklik Haritası

| Dosya | Değişiklik |
|---|---|
| `app/auth.py` | **Yeni** — cookie utils, `verify_api_key`, `get_current_user`, `require_admin`, `require_admin_or_apikey`, `_hash_password` |
| `app/db.py` | `users` tablosu SCHEMA'ya eklenir |
| `app/config.py` | `api_key: ""` DEFAULTS'a eklenir |
| `app/main.py` | Cookie util'leri auth'dan import, hardcoded creds kaldırılır, lifespan'e migration, login DB'den doğrulanır, admin page role geçer, `/api/apikey/generate` + user CRUD endpoint'leri eklenir |
| `app/routers/api.py` | Router'a `Depends(verify_api_key)`, `GET /api/device` endpoint'i |
| `app/routers/admin.py` | Router'a `Depends(verify_api_key)`, `update_settings`'e `Depends(require_admin_or_apikey)` |
| `app/templates/admin.html` | Sidebar'a 2 link, `sec-api-access` + `sec-users` bölümleri, Jinja `user_role` değişkeni |
| `app/static/js/admin.js` | API key UI + kullanıcı yönetimi UI |
| `tests/test_auth.py` | **Yeni** — auth.py birimleri için testler |
| `tests/test_admin_auth.py` | auth.py'den import edecek şekilde güncellenir |

---

## Task 1: `app/auth.py` — Temel Auth Modülü

**Files:**
- Create: `app/auth.py`
- Create: `tests/test_auth.py`

- [ ] **Step 1: Failing testleri yaz**

`tests/test_auth.py`:
```python
"""app/auth.py birimleri için testler."""
import time
import pytest
from unittest.mock import AsyncMock, MagicMock


def test_hash_password_deterministic():
    from app.auth import _hash_password
    h1 = _hash_password("Ankara12!", "mssadmin")
    h2 = _hash_password("Ankara12!", "mssadmin")
    assert h1 == h2
    assert len(h1) == 64  # hex(32 bytes)


def test_hash_password_different_users():
    from app.auth import _hash_password
    h1 = _hash_password("aynıŞifre", "user1")
    h2 = _hash_password("aynıŞifre", "user2")
    assert h1 != h2


def test_sign_and_verify_cookie():
    from app.auth import _sign_cookie, _verify_cookie
    token = _sign_cookie("mssadmin")
    assert _verify_cookie(token) == "mssadmin"


def test_wrong_cookie_rejected():
    from app.auth import _verify_cookie
    assert _verify_cookie("tampered:123:badsig") is None


def test_malformed_cookie_rejected():
    from app.auth import _verify_cookie
    assert _verify_cookie("") is None
    assert _verify_cookie("a:b") is None


def test_expired_cookie_rejected():
    import hmac, hashlib
    from app.auth import _SECRET_KEY, _SESSION_TTL
    username = "mssadmin"
    ts = str(int(time.time()) - _SESSION_TTL - 1)
    msg = f"{username}:{ts}"
    sig = hmac.new(_SECRET_KEY.encode(), msg.encode(), hashlib.sha256).hexdigest()
    token = f"{msg}:{sig}"
    from app.auth import _verify_cookie
    assert _verify_cookie(token) is None


@pytest.mark.asyncio
async def test_verify_api_key_no_key_configured():
    """Key yoksa 503 döner."""
    from fastapi import HTTPException
    from app.auth import verify_api_key
    request = MagicMock()
    request.cookies.get = MagicMock(return_value="")
    request.app.state.config.get = AsyncMock(return_value="")
    request.headers.get = MagicMock(return_value=None)
    with pytest.raises(HTTPException) as exc:
        await verify_api_key(request)
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_verify_api_key_wrong_key():
    """Yanlış key 401 döner."""
    from fastapi import HTTPException
    from app.auth import verify_api_key
    request = MagicMock()
    request.cookies.get = MagicMock(return_value="")
    request.app.state.config.get = AsyncMock(return_value="correctkey")
    request.headers.get = MagicMock(return_value="wrongkey")
    with pytest.raises(HTTPException) as exc:
        await verify_api_key(request)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_verify_api_key_correct_key():
    """Doğru key geçer."""
    from app.auth import verify_api_key
    request = MagicMock()
    request.cookies.get = MagicMock(return_value="")
    request.app.state.config.get = AsyncMock(return_value="mykey")
    request.headers.get = MagicMock(return_value="mykey")
    await verify_api_key(request)  # exception yok


@pytest.mark.asyncio
async def test_verify_api_key_valid_cookie_bypasses_key():
    """Geçerli cookie varsa API key kontrolü yapılmaz."""
    from app.auth import verify_api_key, _sign_cookie
    token = _sign_cookie("mssadmin")
    request = MagicMock()
    request.cookies.get = MagicMock(return_value=token)
    request.app.state.config.get = AsyncMock(return_value="")  # key yok ama önemli değil
    request.headers.get = MagicMock(return_value=None)
    await verify_api_key(request)  # exception yok
```

- [ ] **Step 2: Testlerin başarısız olduğunu doğrula**

```bash
cd /home/mssadmin/mssRadMon && source .venv/bin/activate && pytest tests/test_auth.py -v 2>&1 | head -30
```
Beklenen: `ModuleNotFoundError: No module named 'app.auth'`

- [ ] **Step 3: `app/auth.py` yaz**

```python
"""Auth utilities — API key doğrulama, session cookie, şifre hash, rol kontrolü."""
import hashlib
import hmac
import time

from fastapi import Depends, HTTPException, Request

_SECRET_KEY = "mssRadMon-session-key-2026"
_SESSION_TTL = 28800  # 8 saat
COOKIE_NAME = "mssradmon_session"


def _hash_password(password: str, username: str) -> str:
    """PBKDF2-SHA256 ile şifre hash'le. Salt olarak username kullanılır."""
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), username.encode(), 260000
    )
    return dk.hex()


def _sign_cookie(username: str) -> str:
    ts = str(int(time.time()))
    msg = f"{username}:{ts}"
    sig = hmac.new(_SECRET_KEY.encode(), msg.encode(), hashlib.sha256).hexdigest()
    return f"{msg}:{sig}"


def _verify_cookie(value: str) -> str | None:
    try:
        parts = value.split(":")
        if len(parts) != 3:
            return None
        username, ts_str, sig = parts
        msg = f"{username}:{ts_str}"
        expected = hmac.new(
            _SECRET_KEY.encode(), msg.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        if int(time.time()) - int(ts_str) > _SESSION_TTL:
            return None
        return username
    except Exception:
        return None


async def verify_api_key(request: Request) -> None:
    """Geçerli session cookie VEYA geçerli X-API-Key header kabul eder."""
    token = request.cookies.get(COOKIE_NAME, "")
    if _verify_cookie(token):
        return
    key = await request.app.state.config.get("api_key")
    if not key:
        raise HTTPException(503, detail="API key henüz üretilmemiş")
    if request.headers.get("X-API-Key") != key:
        raise HTTPException(401, detail="Geçersiz API key")


async def get_current_user(request: Request) -> dict:
    """Cookie doğrulama — kullanıcı dict döndürür. Sadece cookie auth."""
    token = request.cookies.get(COOKIE_NAME, "")
    username = _verify_cookie(token)
    if not username:
        raise HTTPException(401)
    row = await request.app.state.db.fetch_one(
        "SELECT username, role FROM users WHERE username = ?", (username,)
    )
    if not row:
        raise HTTPException(401)
    return row


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Cookie ile giriş yapmış kullanıcının admin rolünü zorunlu kılar."""
    if user["role"] != "admin":
        raise HTTPException(403, detail="Admin yetkisi gerekli")
    return user


async def require_admin_or_apikey(request: Request) -> None:
    """Yazma endpoint'leri için: cookie+admin veya geçerli API key kabul eder."""
    token = request.cookies.get(COOKIE_NAME, "")
    username = _verify_cookie(token)
    if username:
        row = await request.app.state.db.fetch_one(
            "SELECT role FROM users WHERE username = ?", (username,)
        )
        if not row or row["role"] != "admin":
            raise HTTPException(403, detail="Admin yetkisi gerekli")
        return
    # Cookie yoksa — verify_api_key router seviyesinde zaten doğruladı
```

- [ ] **Step 4: Testleri çalıştır, hepsinin geçtiğini doğrula**

```bash
cd /home/mssadmin/mssRadMon && source .venv/bin/activate && pytest tests/test_auth.py -v
```
Beklenen: 11 passed

- [ ] **Step 5: `tests/test_admin_auth.py` güncelle**

`test_admin_auth.py` içindeki yerel kopyaları kaldır, auth.py'den import et:

```python
"""Admin auth cookie imzalama testleri."""
import time
import hmac
import hashlib
import pytest

from app.auth import _sign_cookie, _verify_cookie, _SECRET_KEY, _SESSION_TTL


def test_sign_and_verify():
    token = _sign_cookie("mssadmin")
    assert _verify_cookie(token) == "mssadmin"


def test_wrong_secret_rejected():
    token = _sign_cookie("mssadmin")
    # İmzayı bozmak için token'ı manipüle et
    parts = token.split(":")
    parts[2] = "badsig"
    assert _verify_cookie(":".join(parts)) is None


def test_tampered_token_rejected():
    token = _sign_cookie("mssadmin")
    parts = token.split(":")
    parts[0] = "hacker"
    assert _verify_cookie(":".join(parts)) is None


def test_expired_token_rejected():
    username = "mssadmin"
    ts = str(int(time.time()) - _SESSION_TTL - 1)
    msg = f"{username}:{ts}"
    sig = hmac.new(_SECRET_KEY.encode(), msg.encode(), hashlib.sha256).hexdigest()
    token = f"{msg}:{sig}"
    assert _verify_cookie(token) is None


def test_malformed_token_rejected():
    assert _verify_cookie("notavalidtoken") is None
    assert _verify_cookie("") is None
    assert _verify_cookie("a:b") is None
```

- [ ] **Step 6: Tüm auth testlerini çalıştır**

```bash
cd /home/mssadmin/mssRadMon && source .venv/bin/activate && pytest tests/test_auth.py tests/test_admin_auth.py -v
```
Beklenen: 16 passed

- [ ] **Step 7: Commit**

```bash
cd /home/mssadmin/mssRadMon && git add app/auth.py tests/test_auth.py tests/test_admin_auth.py && git commit -m "feat: auth modülü — API key, cookie, şifre hash, rol kontrolü"
```

---

## Task 2: `app/db.py` — Users Tablosu

**Files:**
- Modify: `app/db.py`
- Create: `tests/test_users_db.py`

- [ ] **Step 1: Failing testi yaz**

`tests/test_users_db.py`:
```python
"""users tablosu şema testi."""
import pytest
from app.db import Database
import tempfile, os


@pytest.mark.asyncio
async def test_users_table_exists():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        db = Database(path)
        await db.init()
        # users tablosuna insert yapabilmeli
        await db.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("testuser", "hash123", "admin"),
        )
        row = await db.fetch_one("SELECT username, role FROM users WHERE username = ?", ("testuser",))
        assert row["username"] == "testuser"
        assert row["role"] == "admin"
        await db.close()
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_users_role_constraint():
    """Geçersiz rol reddedilmeli."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        db = Database(path)
        await db.init()
        import aiosqlite
        with pytest.raises(Exception):
            await db.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                ("testuser", "hash123", "superuser"),
            )
        await db.close()
    finally:
        os.unlink(path)
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

```bash
cd /home/mssadmin/mssRadMon && source .venv/bin/activate && pytest tests/test_users_db.py -v
```
Beklenen: `OperationalError: no such table: users`

- [ ] **Step 3: `app/db.py` SCHEMA'ya users tablosu ekle**

`app/db.py` dosyasındaki `SCHEMA` string'ine `shift_doses` tablosundan sonra ekle:

```python
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin', 'viewer'))
);
```

- [ ] **Step 4: Testleri çalıştır**

```bash
cd /home/mssadmin/mssRadMon && source .venv/bin/activate && pytest tests/test_users_db.py -v
```
Beklenen: 2 passed

- [ ] **Step 5: Commit**

```bash
cd /home/mssadmin/mssRadMon && git add app/db.py tests/test_users_db.py && git commit -m "feat: users tablosu şemaya eklendi"
```

---

## Task 3: `app/config.py` — api_key Default

**Files:**
- Modify: `app/config.py`

- [ ] **Step 1: `api_key` DEFAULTS'a ekle**

`app/config.py` dosyasındaki `DEFAULTS` dict'ine, `"calibration_factor"` satırından sonra ekle:

```python
    "api_key": "",
```

- [ ] **Step 2: Mevcut testlerin geçtiğini doğrula**

```bash
cd /home/mssadmin/mssRadMon && source .venv/bin/activate && pytest tests/test_config.py -v
```
Beklenen: tüm testler passed

- [ ] **Step 3: Commit**

```bash
cd /home/mssadmin/mssRadMon && git add app/config.py && git commit -m "feat: api_key config anahtarı eklendi"
```

---

## Task 4: `app/main.py` — Migration + Login + Yeni Endpoint'ler

**Files:**
- Modify: `app/main.py`

Bu task `main.py`'de birden fazla değişiklik içerir.

### 4a: Import ve hardcoded credentials

- [ ] **Step 1: Import'ları güncelle, hardcoded constants'ları kaldır**

`main.py` başındaki mevcut auth import'larını ve sabitlerini şununla değiştir:

```python
from app.auth import (
    _hash_password,
    _sign_cookie,
    _verify_cookie,
    _SESSION_TTL,
    COOKIE_NAME,
    get_current_user,
    require_admin,
    require_admin_or_apikey,
    verify_api_key,
)
```

Aşağıdaki satırları **sil**:
```python
import hashlib
import hmac
# (varsa)
ADMIN_USERNAME = "mssadmin"
ADMIN_PASSWORD = "Ankara12!"
_SECRET_KEY = "mssRadMon-session-key-2026"
_SESSION_TTL = 28800
_COOKIE_NAME = "mssradmon_session"

def _sign_cookie(username: str) -> str: ...
def _verify_cookie(value: str) -> str | None: ...
```

### 4b: Lifespan — migration

- [ ] **Step 2: Lifespan'e users migration ekle**

`lifespan` fonksiyonu içinde `shift_manager = ShiftManager(...)` satırından **önce** ekle:

```python
        # users tablosu boşsa mssadmin'i ekle (ilk kurulum)
        user_count = await db.fetch_one("SELECT COUNT(*) as n FROM users")
        if user_count["n"] == 0:
            pw_hash = _hash_password("Ankara12!", "mssadmin")
            await db.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                ("mssadmin", pw_hash, "admin"),
            )
            logger.info("İlk kullanıcı oluşturuldu: mssadmin (admin)")
```

### 4c: Login endpoint — DB tabanlı doğrulama

- [ ] **Step 3: `admin_login` fonksiyonunu güncelle**

Mevcut `admin_login` endpoint'ini şununla değiştir:

```python
    @app.post("/admin/login", include_in_schema=False)
    async def admin_login(request: Request):
        form = await request.form()
        username = str(form.get("username", ""))
        password = str(form.get("password", ""))
        db = request.app.state.db
        pw_hash = _hash_password(password, username)
        row = await db.fetch_one(
            "SELECT username FROM users WHERE username = ? AND password_hash = ?",
            (username, pw_hash),
        )
        if row:
            token = _sign_cookie(username)
            resp = RedirectResponse(url="/admin", status_code=303)
            resp.set_cookie(
                COOKIE_NAME, token,
                max_age=_SESSION_TTL,
                httponly=True,
                samesite="lax",
            )
            return resp
        return RedirectResponse(url="/admin/login?error=1", status_code=303)
```

### 4d: Admin page — role bilgisi template'e geçir

- [ ] **Step 4: `admin_page` fonksiyonunu güncelle**

```python
    @app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
    async def admin_page(request: Request):
        token = request.cookies.get(COOKIE_NAME, "")
        if not _verify_cookie(token):
            return RedirectResponse(url="/admin/login", status_code=303)
        username = _verify_cookie(token)
        row = await request.app.state.db.fetch_one(
            "SELECT role FROM users WHERE username = ?", (username,)
        )
        user_role = row["role"] if row else "viewer"
        return templates.TemplateResponse(
            "admin.html",
            {"request": request, "active": "admin", "user_role": user_role},
        )
```

### 4e: Logout endpoint — COOKIE_NAME güncelle

- [ ] **Step 5: `admin_logout` fonksiyonunda cookie ismini güncelle**

```python
    @app.post("/admin/logout", include_in_schema=False)
    async def admin_logout(request: Request):
        resp = RedirectResponse(url="/admin/login", status_code=303)
        resp.delete_cookie(COOKIE_NAME)
        return resp
```

### 4f: Yeni endpoint'ler

- [ ] **Step 6: `POST /api/apikey/generate` endpoint'ini ekle**

`app.include_router(admin.router)` satırından sonra ekle:

```python
    import secrets

    @app.post("/api/apikey/generate", include_in_schema=False)
    async def generate_api_key(
        request: Request,
        _user: dict = Depends(require_admin),
    ):
        """Yeni API key üret ve kaydet. Admin cookie zorunlu."""
        new_key = secrets.token_hex(32)
        await request.app.state.config.set("api_key", new_key)
        return {"api_key": new_key}

    @app.get("/api/users", include_in_schema=False)
    async def list_users(
        request: Request,
        _user: dict = Depends(require_admin),
    ):
        rows = await request.app.state.db.fetch_all(
            "SELECT id, username, role FROM users ORDER BY id"
        )
        return rows

    @app.post("/api/users", include_in_schema=False)
    async def create_user(
        request: Request,
        body: dict,
        _user: dict = Depends(require_admin),
    ):
        username = body.get("username", "").strip()
        password = body.get("password", "")
        role = body.get("role", "viewer")
        if not username or not password:
            raise HTTPException(400, detail="username ve password zorunlu")
        if role not in ("admin", "viewer"):
            raise HTTPException(400, detail="role 'admin' veya 'viewer' olmalı")
        pw_hash = _hash_password(password, username)
        try:
            await request.app.state.db.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, pw_hash, role),
            )
        except Exception:
            raise HTTPException(409, detail="Bu kullanıcı adı zaten mevcut")
        return {"ok": True}

    @app.delete("/api/users/{username}", include_in_schema=False)
    async def delete_user(
        request: Request,
        username: str,
        current_user: dict = Depends(require_admin),
    ):
        if username == current_user["username"]:
            raise HTTPException(400, detail="Kendi hesabınızı silemezsiniz")
        # Son admin kontrolü
        target = await request.app.state.db.fetch_one(
            "SELECT role FROM users WHERE username = ?", (username,)
        )
        if not target:
            raise HTTPException(404, detail="Kullanıcı bulunamadı")
        if target["role"] == "admin":
            count = await request.app.state.db.fetch_one(
                "SELECT COUNT(*) as n FROM users WHERE role = 'admin'"
            )
            if count["n"] <= 1:
                raise HTTPException(400, detail="Son admin silinemez")
        await request.app.state.db.execute(
            "DELETE FROM users WHERE username = ?", (username,)
        )
        return {"ok": True}

    @app.put("/api/users/{username}/password", include_in_schema=False)
    async def change_password(
        request: Request,
        username: str,
        body: dict,
        current_user: dict = Depends(get_current_user),
    ):
        is_self = username == current_user["username"]
        is_admin = current_user["role"] == "admin"
        if not is_self and not is_admin:
            raise HTTPException(403, detail="Başkasının şifresini değiştiremezsiniz")
        new_password = body.get("new_password", "")
        if not new_password:
            raise HTTPException(400, detail="new_password zorunlu")
        if is_self:
            current_password = body.get("current_password", "")
            if not current_password:
                raise HTTPException(400, detail="current_password zorunlu")
            row = await request.app.state.db.fetch_one(
                "SELECT id FROM users WHERE username = ? AND password_hash = ?",
                (username, _hash_password(current_password, username)),
            )
            if not row:
                raise HTTPException(400, detail="Mevcut şifre yanlış")
        new_hash = _hash_password(new_password, username)
        await request.app.state.db.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?",
            (new_hash, username),
        )
        return {"ok": True}
```

- [ ] **Step 7: Mevcut testleri çalıştır**

```bash
cd /home/mssadmin/mssRadMon && source .venv/bin/activate && pytest -x -q 2>&1 | tail -20
```
Beklenen: tüm testler passed (bazıları skip veya warning olabilir)

- [ ] **Step 8: Commit**

```bash
cd /home/mssadmin/mssRadMon && git add app/main.py && git commit -m "feat: DB tabanlı login, kullanıcı CRUD, apikey/generate endpoint'leri"
```

---

## Task 5: `app/routers/api.py` — verify_api_key + GET /api/device

**Files:**
- Modify: `app/routers/api.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Failing testi yaz**

`tests/test_api.py` dosyasına şu testi ekle (dosyanın sonuna):

```python
@pytest.mark.asyncio
async def test_get_device(seeded_db):
    """GET /api/device cihaz bilgilerini döndürmeli."""
    from app.routers.api import get_device
    db, config = seeded_db
    await config.set("device_name", "TestCihaz")
    await config.set("device_location", "Test Odası")
    await config.set("device_serial", "SN-001")
    request = MagicMock()
    request.app.state.config = config
    result = await get_device(request)
    assert result["device_name"] == "TestCihaz"
    assert result["device_location"] == "Test Odası"
    assert result["device_serial"] == "SN-001"


@pytest.mark.asyncio
async def test_get_device_empty_serial(seeded_db):
    """Seri no okunmamışsa boş string döner."""
    from app.routers.api import get_device
    db, config = seeded_db
    request = MagicMock()
    request.app.state.config = config
    result = await get_device(request)
    assert result["device_serial"] == ""
```

- [ ] **Step 2: Testlerin başarısız olduğunu doğrula**

```bash
cd /home/mssadmin/mssRadMon && source .venv/bin/activate && pytest tests/test_api.py::test_get_device tests/test_api.py::test_get_device_empty_serial -v
```
Beklenen: `ImportError: cannot import name 'get_device'`

- [ ] **Step 3: `api.py` güncelle**

`app/routers/api.py` dosyasında:

1. Dosya başına import ekle:
```python
from app.auth import verify_api_key
from fastapi import Depends
```

2. Router tanımını güncelle:
```python
router = APIRouter(prefix="/api", tags=["api"], dependencies=[Depends(verify_api_key)])
```

3. Dosyanın sonuna `GET /api/device` endpoint'ini ekle:
```python
@router.get("/device")
async def get_device(request: Request):
    """Cihaz kimlik bilgilerini döndür."""
    config = request.app.state.config
    return {
        "device_name": await config.get("device_name") or "",
        "device_location": await config.get("device_location") or "",
        "device_serial": await config.get("device_serial") or "",
    }
```

- [ ] **Step 4: Testleri çalıştır**

```bash
cd /home/mssadmin/mssRadMon && source .venv/bin/activate && pytest tests/test_api.py -v
```
Beklenen: tüm testler passed

- [ ] **Step 5: Commit**

```bash
cd /home/mssadmin/mssRadMon && git add app/routers/api.py tests/test_api.py && git commit -m "feat: api router'a verify_api_key dependency + GET /api/device"
```

---

## Task 6: `app/routers/admin.py` — verify_api_key + require_admin_or_apikey

**Files:**
- Modify: `app/routers/admin.py`
- Modify: `tests/test_admin.py`

- [ ] **Step 1: Mevcut admin testini incele, failing testi ekle**

`tests/test_admin.py` dosyasına şu testi ekle (dosyanın sonuna):

```python
@pytest.mark.asyncio
async def test_update_settings_viewer_rejected():
    """viewer rolüyle PUT /api/settings 403 dönmeli."""
    from fastapi import HTTPException
    from app.routers.admin import update_settings
    from app.auth import _sign_cookie
    import json

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        from app.db import Database
        from app.config import Config
        db = Database(path)
        await db.init()
        config = Config(db)
        await config.init()
        # viewer kullanıcı ekle
        from app.auth import _hash_password
        await db.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("viewer1", _hash_password("pass", "viewer1"), "viewer"),
        )
        token = _sign_cookie("viewer1")
        request = MagicMock()
        request.app.state.config = config
        request.app.state.db = db
        request.cookies.get = MagicMock(return_value=token)
        request.headers.get = MagicMock(return_value=None)
        with pytest.raises(HTTPException) as exc:
            await update_settings(request, {"device_name": "test"})
        assert exc.value.status_code == 403
        await db.close()
    finally:
        os.unlink(path)
```

`tests/test_admin.py` dosyasının başına eksik import'ları ekle (zaten yoksa):
```python
import tempfile
import os
from unittest.mock import MagicMock
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

```bash
cd /home/mssadmin/mssRadMon && source .venv/bin/activate && pytest tests/test_admin.py::test_update_settings_viewer_rejected -v
```
Beklenen: test 403 yerine başarıyla geçer (henüz kontrol yok)

- [ ] **Step 3: `admin.py` güncelle**

`app/routers/admin.py` dosyasında:

1. Dosya başına import ekle:
```python
from app.auth import verify_api_key, require_admin_or_apikey
from fastapi import Depends
```

2. Router tanımını güncelle:
```python
router = APIRouter(prefix="/api", tags=["admin"], dependencies=[Depends(verify_api_key)])
```

3. `update_settings` endpoint'ine `require_admin_or_apikey` dependency ekle:
```python
@router.put("/settings", dependencies=[Depends(require_admin_or_apikey)])
async def update_settings(request: Request, settings: dict):
    """Ayarları güncelle."""
    config = request.app.state.config
    for key, value in settings.items():
        await config.set(key, str(value))
    return {"status": "ok"}
```

- [ ] **Step 4: Testleri çalıştır**

```bash
cd /home/mssadmin/mssRadMon && source .venv/bin/activate && pytest tests/test_admin.py -v
```
Beklenen: tüm testler passed

- [ ] **Step 5: Commit**

```bash
cd /home/mssadmin/mssRadMon && git add app/routers/admin.py tests/test_admin.py && git commit -m "feat: admin router'a verify_api_key + PUT /api/settings admin koruması"
```

---

## Task 7: `app/templates/admin.html` — API Erişimi + Kullanıcılar Bölümleri

**Files:**
- Modify: `app/templates/admin.html`

- [ ] **Step 1: Sidebar'a 2 yeni link ekle**

`admin.html` dosyasındaki sidebar `<nav>` içinde, `Alarm Geçmişi` linkinden önce ekle:

```html
            <a href="#" class="sidebar-link" data-section="api-access">API Erişimi</a>
            <a href="#" class="sidebar-link" id="usersLink" data-section="users">Kullanıcılar</a>
```

- [ ] **Step 2: admin-content div içine iki yeni section ekle**

`sec-history` section'ından önce şunu ekle:

```html
        <!-- API Erişimi -->
        <section class="admin-section" id="sec-api-access">
            <h2 class="section-title">API Erişimi</h2>
            <div class="card">
                <div class="form-group">
                    <label>API Key</label>
                    <div style="display:flex;gap:0.5rem;align-items:center;">
                        <input type="text" id="apiKeyDisplay" readonly
                               style="flex:1;font-family:monospace;font-size:0.85rem;"
                               placeholder="Henüz üretilmemiş">
                        <button class="btn" id="copyApiKeyBtn"
                                style="background:var(--surface);border:1px solid var(--accent);white-space:nowrap;">
                            Kopyala
                        </button>
                    </div>
                </div>
                <button class="btn" id="generateApiKeyBtn">Yeni Key Üret</button>
                <span id="apiKeyMsg" class="save-msg"></span>
                <p style="font-size:0.8rem;color:var(--text-dim);margin-top:1rem;">
                    ⚠ Yeni key üretildiğinde eski key geçersiz olur. Bağlı manager'ı güncellemeyi unutmayın.
                </p>
            </div>
        </section>

        <!-- Kullanıcılar -->
        <section class="admin-section" id="sec-users">
            <h2 class="section-title">Kullanıcı Yönetimi</h2>

            <div class="card">
                <div class="card-title">Kullanıcılar</div>
                <div id="userList" style="margin-bottom:1rem;"></div>
            </div>

            <div class="card">
                <div class="card-title">Yeni Kullanıcı Ekle</div>
                <div class="dashboard-grid">
                    <div class="form-group">
                        <label for="newUsername">Kullanıcı Adı</label>
                        <input type="text" id="newUsername" placeholder="operator1">
                    </div>
                    <div class="form-group">
                        <label for="newUserRole">Rol</label>
                        <select id="newUserRole" style="width:100%;padding:0.5rem 0.75rem;background:var(--surface);border:1px solid rgba(255,255,255,0.15);border-radius:6px;color:var(--text);font-size:0.95rem;">
                            <option value="viewer">viewer</option>
                            <option value="admin">admin</option>
                        </select>
                    </div>
                </div>
                <div class="form-group">
                    <label for="newUserPassword">Şifre</label>
                    <input type="password" id="newUserPassword">
                </div>
                <button class="btn" id="addUserBtn">Kullanıcı Ekle</button>
                <span id="addUserMsg" class="save-msg"></span>
            </div>

            <div class="card">
                <div class="card-title">Şifremi Değiştir</div>
                <div class="form-group">
                    <label for="currentPassword">Mevcut Şifre</label>
                    <input type="password" id="currentPassword">
                </div>
                <div class="form-group">
                    <label for="newPassword">Yeni Şifre</label>
                    <input type="password" id="newPassword">
                </div>
                <div class="form-group">
                    <label for="confirmPassword">Yeni Şifre (Tekrar)</label>
                    <input type="password" id="confirmPassword">
                </div>
                <button class="btn" id="changePasswordBtn">Şifreyi Güncelle</button>
                <span id="changePasswordMsg" class="save-msg"></span>
            </div>
        </section>
```

- [ ] **Step 3: Jinja user_role değişkenini template'e aktar**

`admin.html` dosyasının `{% block scripts %}` bloğundan **önce** ekle:

```html
<script>
    const USER_ROLE = "{{ user_role }}";
</script>
```

- [ ] **Step 4: viewer için kısıtlamalar ekle**

`{% block scripts %}` bloğundan önce, `USER_ROLE` script tag'inden sonra ekle:

```html
<script>
    // viewer rolünde kaydet butonları ve kullanıcı yönetimi bölümü gizlenir
    if (USER_ROLE === "viewer") {
        document.addEventListener("DOMContentLoaded", () => {
            document.querySelectorAll(".save-section-btn, #saveBtn, #generateApiKeyBtn, #addUserBtn")
                .forEach(btn => { btn.disabled = true; btn.style.opacity = "0.4"; });
            const usersLink = document.getElementById("usersLink");
            if (usersLink) usersLink.style.display = "none";
        });
    }
</script>
```

- [ ] **Step 5: Uygulama başlatılabilir mi kontrol et**

```bash
cd /home/mssadmin/mssRadMon && source .venv/bin/activate && python -c "from app.main import create_app; app = create_app(); print('OK')"
```
Beklenen: `OK`

- [ ] **Step 6: Commit**

```bash
cd /home/mssadmin/mssRadMon && git add app/templates/admin.html && git commit -m "feat: admin panel — API Erişimi ve Kullanıcılar bölümleri eklendi"
```

---

## Task 8: `app/static/js/admin.js` — API Key + Kullanıcı Yönetimi UI

**Files:**
- Modify: `app/static/js/admin.js`

- [ ] **Step 1: API key bölümü JS ekle**

`admin.js` dosyasında `// --- Init ---` bölümünden önce ekle:

```javascript
// --- API Key ---

let _fullApiKey = null;  // Üretilen key bellekte tutulur (kopyala için)

async function loadApiKey() {
    try {
        const res = await fetch("/api/settings");
        const s = await res.json();
        const el = document.getElementById("apiKeyDisplay");
        if (!el) return;
        if (s.api_key) {
            // İlk 4 karakter görünür, geri kalanı maskelenir
            el.value = s.api_key.substring(0, 4) + "•".repeat(s.api_key.length - 4);
            el.dataset.hasKey = "true";
        } else {
            el.value = "";
            el.placeholder = "Henüz üretilmemiş";
            el.dataset.hasKey = "false";
        }
    } catch (e) {
        console.error("API key yüklenemedi:", e);
    }
}

document.getElementById("generateApiKeyBtn")?.addEventListener("click", async () => {
    if (!confirm("Yeni key üretildiğinde eski key geçersiz olur. Devam etmek istiyor musunuz?")) return;
    const msgEl = document.getElementById("apiKeyMsg");
    try {
        const res = await fetch("/api/apikey/generate", { method: "POST" });
        if (!res.ok) {
            const err = await res.json();
            msgEl.textContent = err.detail || "Hata oluştu";
            msgEl.style.color = "var(--red)";
            msgEl.classList.add("show");
            return;
        }
        const data = await res.json();
        _fullApiKey = data.api_key;
        const el = document.getElementById("apiKeyDisplay");
        el.value = _fullApiKey;  // Üretim sonrası tam key göster
        el.dataset.hasKey = "true";
        msgEl.textContent = "Key üretildi. Kopyalamayı unutmayın!";
        msgEl.style.color = "var(--green)";
        msgEl.classList.add("show");
        setTimeout(() => {
            // 30 saniye sonra maskelenir
            el.value = _fullApiKey.substring(0, 4) + "•".repeat(_fullApiKey.length - 4);
            msgEl.classList.remove("show");
        }, 30000);
    } catch (e) {
        console.error("Key üretilemedi:", e);
    }
});

document.getElementById("copyApiKeyBtn")?.addEventListener("click", async () => {
    const el = document.getElementById("apiKeyDisplay");
    const msgEl = document.getElementById("apiKeyMsg");
    let keyToCopy = _fullApiKey;
    if (!keyToCopy) {
        // Maskelenmiş değeri kopyalamaya çalışıyorsa tam key'i fetch et
        msgEl.textContent = "Tam key için önce 'Yeni Key Üret' ile yenileyin.";
        msgEl.style.color = "var(--text-dim)";
        msgEl.classList.add("show");
        setTimeout(() => msgEl.classList.remove("show"), 3000);
        return;
    }
    try {
        await navigator.clipboard.writeText(keyToCopy);
        const btn = document.getElementById("copyApiKeyBtn");
        btn.textContent = "Kopyalandı!";
        setTimeout(() => { btn.textContent = "Kopyala"; }, 2000);
    } catch (e) {
        msgEl.textContent = "Kopyalama başarısız";
        msgEl.style.color = "var(--red)";
        msgEl.classList.add("show");
    }
});
```

- [ ] **Step 2: Kullanıcı yönetimi JS ekle**

`// --- API Key ---` bloğundan sonra ekle:

```javascript
// --- Kullanıcı Yönetimi ---

async function loadUsers() {
    const container = document.getElementById("userList");
    if (!container) return;
    try {
        const res = await fetch("/api/users");
        if (!res.ok) { container.innerHTML = '<span style="color:var(--text-dim)">Yüklenemedi</span>'; return; }
        const users = await res.json();
        if (users.length === 0) { container.innerHTML = '<span style="color:var(--text-dim)">Kullanıcı yok</span>'; return; }
        container.innerHTML = "";
        const adminCount = users.filter(u => u.role === "admin").length;
        users.forEach(u => {
            const row = document.createElement("div");
            row.style.cssText = "display:flex;justify-content:space-between;align-items:center;padding:0.4rem 0.6rem;background:var(--bg);border-radius:4px;margin-bottom:0.25rem;font-size:0.85rem;";
            const badge = u.role === "admin"
                ? '<span style="background:var(--accent);color:#fff;border-radius:4px;padding:0.1rem 0.4rem;font-size:0.75rem;margin-left:0.4rem;">admin</span>'
                : '<span style="background:var(--surface);border:1px solid rgba(255,255,255,0.15);border-radius:4px;padding:0.1rem 0.4rem;font-size:0.75rem;margin-left:0.4rem;">viewer</span>';
            const canDelete = !(u.role === "admin" && adminCount <= 1);
            const delBtn = document.createElement("button");
            delBtn.textContent = "Sil";
            delBtn.disabled = !canDelete;
            delBtn.style.cssText = `background:none;border:1px solid var(--red);color:var(--red);border-radius:4px;padding:0.15rem 0.5rem;cursor:${canDelete ? "pointer" : "default"};font-size:0.75rem;opacity:${canDelete ? 1 : 0.3};`;
            delBtn.addEventListener("click", async () => {
                if (!confirm(`'${u.username}' silinsin mi?`)) return;
                const r = await fetch(`/api/users/${encodeURIComponent(u.username)}`, { method: "DELETE" });
                const d = await r.json();
                if (d.ok) loadUsers();
                else alert(d.detail || "Silinemedi");
            });
            row.innerHTML = `<span>${u.username}${badge}</span>`;
            row.appendChild(delBtn);
            container.appendChild(row);
        });
    } catch (e) {
        if (container) container.innerHTML = '<span style="color:var(--text-dim)">Yüklenemedi</span>';
    }
}

document.getElementById("addUserBtn")?.addEventListener("click", async () => {
    const username = document.getElementById("newUsername").value.trim();
    const password = document.getElementById("newUserPassword").value;
    const role = document.getElementById("newUserRole").value;
    const msgEl = document.getElementById("addUserMsg");
    if (!username || !password) {
        msgEl.textContent = "Kullanıcı adı ve şifre zorunlu";
        msgEl.style.color = "var(--red)";
        msgEl.classList.add("show");
        return;
    }
    try {
        const res = await fetch("/api/users", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username, password, role }),
        });
        const data = await res.json();
        if (data.ok) {
            msgEl.textContent = "Kullanıcı eklendi.";
            msgEl.style.color = "var(--green)";
            document.getElementById("newUsername").value = "";
            document.getElementById("newUserPassword").value = "";
            loadUsers();
        } else {
            msgEl.textContent = data.detail || "Eklenemedi";
            msgEl.style.color = "var(--red)";
        }
        msgEl.classList.add("show");
        setTimeout(() => msgEl.classList.remove("show"), 3000);
    } catch (e) {
        console.error("Kullanıcı eklenemedi:", e);
    }
});

document.getElementById("changePasswordBtn")?.addEventListener("click", async () => {
    const currentPassword = document.getElementById("currentPassword").value;
    const newPassword = document.getElementById("newPassword").value;
    const confirmPassword = document.getElementById("confirmPassword").value;
    const msgEl = document.getElementById("changePasswordMsg");
    if (newPassword !== confirmPassword) {
        msgEl.textContent = "Yeni şifreler eşleşmiyor";
        msgEl.style.color = "var(--red)";
        msgEl.classList.add("show");
        return;
    }
    if (!newPassword) {
        msgEl.textContent = "Yeni şifre boş olamaz";
        msgEl.style.color = "var(--red)";
        msgEl.classList.add("show");
        return;
    }
    // Kendi kullanıcı adını bulmak için /api/users çağrısı gerekmiyor — mevcut session cookie var
    // endpoint kendi şifresini değiştirirken current_password doğrular
    try {
        const usersRes = await fetch("/api/users");
        const users = await usersRes.json();
        // Cookie'deki kullanıcı kendi şifresini değiştiriyor
        // Kullanıcı adını bulmak için küçük bir trick: listedeki ilk admin değil,
        // bunun yerine geçici olarak bir endpoint yok — session'dan oku
        // En basit yaklaşım: page'e username'i de göm
        const currentUsername = document.querySelector("meta[name='username']")?.content;
        if (!currentUsername) {
            msgEl.textContent = "Oturum bilgisi alınamadı, sayfayı yenileyin";
            msgEl.style.color = "var(--red)";
            msgEl.classList.add("show");
            return;
        }
        const res = await fetch(`/api/users/${encodeURIComponent(currentUsername)}/password`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
        });
        const data = await res.json();
        if (data.ok) {
            msgEl.textContent = "Şifre güncellendi.";
            msgEl.style.color = "var(--green)";
            document.getElementById("currentPassword").value = "";
            document.getElementById("newPassword").value = "";
            document.getElementById("confirmPassword").value = "";
        } else {
            msgEl.textContent = data.detail || "Güncellenemedi";
            msgEl.style.color = "var(--red)";
        }
        msgEl.classList.add("show");
        setTimeout(() => msgEl.classList.remove("show"), 3000);
    } catch (e) {
        console.error("Şifre değiştirilemedi:", e);
    }
});
```

- [ ] **Step 3: `admin.html`'e kullanıcı adı meta tag'i ekle**

`admin.html` dosyasında `USER_ROLE` script tag'inden önce ekle:

```html
<meta name="username" content="{{ username }}">
```

Ve `main.py`'deki `admin_page` fonksiyonuna `username` değişkenini template context'e ekle:

```python
        return templates.TemplateResponse(
            "admin.html",
            {"request": request, "active": "admin", "user_role": user_role, "username": username},
        )
```

- [ ] **Step 4: Init bölümüne `loadApiKey` ve `loadUsers` ekle**

`admin.js` dosyasındaki `// --- Init ---` bölümünde:

```javascript
// --- Init ---

loadSettings();
loadAlarmHistory();
loadWifiStatus();
loadShifts();
loadApiKey();
loadUsers();
```

- [ ] **Step 5: Tüm testleri çalıştır**

```bash
cd /home/mssadmin/mssRadMon && source .venv/bin/activate && pytest -q 2>&1 | tail -10
```
Beklenen: tüm testler passed

- [ ] **Step 6: Commit**

```bash
cd /home/mssadmin/mssRadMon && git add app/static/js/admin.js app/templates/admin.html app/main.py && git commit -m "feat: API key UI ve kullanıcı yönetimi UI tamamlandı"
```

---

## Task 9: MANAGER_INTEGRATION.md Güncelle

**Files:**
- Modify: `MANAGER_INTEGRATION.md`

- [ ] **Step 1: Auth bölümünü güncelle**

`MANAGER_INTEGRATION.md` dosyasındaki "Temel Bilgiler" tablosundaki kimlik doğrulama satırını güncelle:

```markdown
| Kimlik doğrulama | `X-API-Key: <key>` header — tüm `/api/*` endpoint'leri |
```

Ayrıca "Ayar Yönetimi" bölümündeki güvenlik notunu güncelle:

```markdown
> **Güvenlik notu:** API key admin panelinden üretilir. Key'i güvenli saklayın.
> `PUT /api/settings` sadece admin cookie VEYA geçerli API key ile çağrılabilir.
```

- [ ] **Step 2: Commit**

```bash
cd /home/mssadmin/mssRadMon && git add MANAGER_INTEGRATION.md && git commit -m "docs: manager entegrasyon rehberi API key auth ile güncellendi"
```

---

## Self-Review

**Spec coverage kontrolü:**

| Spec maddesi | Task |
|---|---|
| Tüm `/api/*` API key koruması | Task 5 (api.py), Task 6 (admin.py) |
| Cookie veya API key kabul | Task 1 `verify_api_key` |
| Key üretimi endpoint | Task 4f |
| `GET /api/device` | Task 5 |
| Admin panel "API Erişimi" bölümü | Task 7, Task 8 |
| Key maskeleme + kopyala | Task 8 |
| `users` tablosu | Task 2 |
| Şifre hash PBKDF2 | Task 1 `_hash_password` |
| mssadmin migration | Task 4b |
| Hardcoded creds kaldırma | Task 4a |
| DB tabanlı login | Task 4c |
| Rol tabanlı erişim: viewer 403 | Task 6 |
| Kullanıcı listesi/ekle/sil | Task 4f, Task 8 |
| Şifre değiştirme | Task 4f, Task 8 |
| Son admin silinemiyor | Task 4f |
| Viewer kaydet butonları disabled | Task 7 |
| Kullanıcılar bölümü viewer'da gizli | Task 7 |
