# Admin Auth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/admin` sayfasını kullanıcı adı/şifre gerektiren session cookie ile koru.

**Architecture:** HMAC-SHA256 imzalı cookie (stdlib, bağımlılık yok). Login formu `/admin/login`'de, doğrulama `main.py`'de iki yardımcı fonksiyon ile. Cookie geçersizse `/admin/login`'e redirect.

**Tech Stack:** Python stdlib (`hmac`, `hashlib`, `secrets`, `time`), FastAPI `RedirectResponse`, Jinja2

---

## Dosya Haritası

| Dosya | İşlem | Ne Değişiyor |
|-------|-------|--------------|
| `app/main.py` | Modify | Sabit credentials + SECRET_KEY, `_sign_cookie` / `_verify_cookie` fonksiyonları, `/admin/login` GET+POST, `/admin/logout` POST, `/admin` GET güncelleme |
| `app/templates/login.html` | Create | Bağımsız login formu (base.html extend etmez) |
| `app/templates/admin.html` | Modify | Sidebar'a Logout butonu ekle |
| `tests/test_admin_auth.py` | Create | Login/logout/redirect testleri |

---

## Task 1: Cookie İmzalama Yardımcıları + Testler

**Files:**
- Modify: `app/main.py`
- Create: `tests/test_admin_auth.py`

- [ ] **Adım 1: Önce testi yaz**

`tests/test_admin_auth.py` dosyasını oluştur:

```python
"""Admin auth cookie imzalama testleri."""
import time
import hmac
import hashlib

SECRET_KEY = "test-secret"
SESSION_TTL = 28800
COOKIE_NAME = "mssradmon_session"


def _sign_cookie(username: str, secret: str) -> str:
    ts = str(int(time.time()))
    msg = f"{username}:{ts}"
    sig = hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
    return f"{msg}:{sig}"


def _verify_cookie(value: str, secret: str, ttl: int = SESSION_TTL) -> str | None:
    try:
        parts = value.split(":")
        if len(parts) != 3:
            return None
        username, ts_str, sig = parts
        msg = f"{username}:{ts_str}"
        expected = hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        if int(time.time()) - int(ts_str) > ttl:
            return None
        return username
    except Exception:
        return None


def test_sign_and_verify():
    token = _sign_cookie("mssadmin", SECRET_KEY)
    assert _verify_cookie(token, SECRET_KEY) == "mssadmin"


def test_wrong_secret_rejected():
    token = _sign_cookie("mssadmin", SECRET_KEY)
    assert _verify_cookie(token, "wrong-secret") is None


def test_tampered_token_rejected():
    token = _sign_cookie("mssadmin", SECRET_KEY)
    parts = token.split(":")
    parts[0] = "hacker"
    assert _verify_cookie(":".join(parts), SECRET_KEY) is None


def test_expired_token_rejected():
    username = "mssadmin"
    ts = str(int(time.time()) - SESSION_TTL - 1)
    msg = f"{username}:{ts}"
    sig = hmac.new(SECRET_KEY.encode(), msg.encode(), hashlib.sha256).hexdigest()
    token = f"{msg}:{sig}"
    assert _verify_cookie(token, SECRET_KEY) is None


def test_malformed_token_rejected():
    assert _verify_cookie("notavalidtoken", SECRET_KEY) is None
    assert _verify_cookie("", SECRET_KEY) is None
    assert _verify_cookie("a:b", SECRET_KEY) is None
```

- [ ] **Adım 2: Testi çalıştır, FAIL bekle**

```bash
cd /home/mssadmin/mssRadMon
source .venv/bin/activate
pytest tests/test_admin_auth.py -v
```

Beklenen: `ImportError` veya test fonksiyonları içindeki `_sign_cookie` / `_verify_cookie` henüz `main.py`'de olmadığından testler kendi içinde çalışır ve PASS eder — bu Task 1 için normal (fonksiyonlar testte lokal tanımlı). Task 2'de `main.py`'ye taşınacak.

- [ ] **Adım 3: Commit**

```bash
git add tests/test_admin_auth.py
git commit -m "test: admin auth cookie imzalama testleri"
```

---

## Task 2: `main.py`'e Auth Ekle

**Files:**
- Modify: `app/main.py`

- [ ] **Adım 1: Import'ları ve sabitleri ekle**

`main.py` dosyasının import bölümüne ekle:

```python
import hmac
import hashlib
import time
```

`create_app()` fonksiyonundan **önce** sabitleri ekle:

```python
ADMIN_USERNAME = "mssadmin"
ADMIN_PASSWORD = "Ankara12!"
_SECRET_KEY = "mssRadMon-session-key-2026"
_SESSION_TTL = 28800   # 8 saat
_COOKIE_NAME = "mssradmon_session"
```

- [ ] **Adım 2: Yardımcı fonksiyonları ekle**

Sabitlerden hemen sonra, `create_app()` fonksiyonundan önce:

```python
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
        expected = hmac.new(_SECRET_KEY.encode(), msg.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        if int(time.time()) - int(ts_str) > _SESSION_TTL:
            return None
        return username
    except Exception:
        return None
```

- [ ] **Adım 3: Mevcut `/admin` route'unu güncelle, login/logout ekle**

`main.py` içindeki `create_app()` fonksiyonunda, mevcut `/admin` route'unu ve ardından login/logout route'larını şöyle yaz (dashboard route'undan sonra):

```python
from fastapi.responses import HTMLResponse, RedirectResponse

@app.get("/admin/login", response_class=HTMLResponse, include_in_schema=False)
async def admin_login_page(request: Request, error: int = 0):
    return templates.TemplateResponse(
        "login.html", {"request": request, "error": bool(error)}
    )

@app.post("/admin/login", include_in_schema=False)
async def admin_login(request: Request):
    form = await request.form()
    username = form.get("username", "")
    password = form.get("password", "")
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        token = _sign_cookie(username)
        resp = RedirectResponse(url="/admin", status_code=303)
        resp.set_cookie(
            _COOKIE_NAME, token,
            max_age=_SESSION_TTL,
            httponly=True,
            samesite="lax",
        )
        return resp
    return RedirectResponse(url="/admin/login?error=1", status_code=303)

@app.post("/admin/logout", include_in_schema=False)
async def admin_logout(request: Request):
    resp = RedirectResponse(url="/admin/login", status_code=303)
    resp.delete_cookie(_COOKIE_NAME)
    return resp

@app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
async def admin_page(request: Request):
    token = request.cookies.get(_COOKIE_NAME, "")
    if not _verify_cookie(token):
        return RedirectResponse(url="/admin/login", status_code=303)
    return templates.TemplateResponse("admin.html", {"request": request, "active": "admin"})
```

> **Dikkat:** `main.py`'deki mevcut `@app.get("/admin", ...)` satırını **sil**, yukarıdaki ile değiştir. `RedirectResponse`'u import listesine ekle.

- [ ] **Adım 4: Uygulamayı başlat, manuel kontrol**

```bash
source .venv/bin/activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8090 --reload
```

Tarayıcıda `http://localhost:8090/admin` aç → `/admin/login`'e yönlenmeli.

- [ ] **Adım 5: Commit**

```bash
git add app/main.py
git commit -m "feat: admin auth — HMAC cookie, login/logout route'ları"
```

---

## Task 3: Login Sayfası Şablonu

**Files:**
- Create: `app/templates/login.html`

- [ ] **Adım 1: `login.html` oluştur**

```html
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Giriş — mssRadMon</title>
    <link rel="stylesheet" href="/static/css/style.css">
    <style>
        body { display: flex; align-items: center; justify-content: center; min-height: 100vh; }
        .login-card { width: 100%; max-width: 360px; }
        .login-title { font-size: 1.1rem; font-weight: 700; color: var(--accent); margin-bottom: 1.5rem; text-align: center; }
        .error-msg { color: var(--red); font-size: 0.85rem; margin-bottom: 0.75rem; text-align: center; }
    </style>
</head>
<body>
    <div class="card login-card">
        <div class="login-title">mssRadMon Yönetim</div>
        {% if error %}
        <div class="error-msg">Kullanıcı adı veya şifre hatalı.</div>
        {% endif %}
        <form method="post" action="/admin/login">
            <div class="form-group">
                <label for="username">Kullanıcı Adı</label>
                <input type="text" id="username" name="username" autocomplete="username" autofocus>
            </div>
            <div class="form-group">
                <label for="password">Şifre</label>
                <input type="password" id="password" name="password" autocomplete="current-password">
            </div>
            <button type="submit" class="btn" style="width:100%">Giriş</button>
        </form>
    </div>
</body>
</html>
```

- [ ] **Adım 2: Tarayıcıda login akışını test et**

1. `http://localhost:8090/admin` → login sayfasına redirect olmalı
2. Yanlış şifre gir → hata mesajı görünmeli
3. `mssadmin` / `Ankara12!` gir → `/admin` açılmalı
4. DevTools → Application → Cookies: `mssradmon_session` cookie'si olmalı, HttpOnly işaretli

- [ ] **Adım 3: Commit**

```bash
git add app/templates/login.html
git commit -m "feat: admin login sayfası şablonu"
```

---

## Task 4: Admin Sayfasına Logout Butonu

**Files:**
- Modify: `app/templates/admin.html`

- [ ] **Adım 1: Sidebar'a logout butonu ekle**

`admin.html`'de `<nav class="sidebar-nav">` bloğunun sonuna, kapanış `</nav>` etiketinden önce ekle:

```html
            <form method="post" action="/admin/logout" style="margin-top:auto;padding-top:0.5rem;">
                <button type="submit" class="sidebar-link" style="width:100%;background:none;border:none;cursor:pointer;color:var(--red);text-align:left;">Çıkış</button>
            </form>
```

- [ ] **Adım 2: Görsel kontrol**

Admin sayfasında sidebar'ın en altında kırmızı "Çıkış" linki görünmeli. Tıklandığında `/admin/login`'e dönmeli ve cookie silinmeli.

- [ ] **Adım 3: Tam akış testi**

1. `/admin` → login redirect ✓
2. Yanlış credentials → hata mesajı ✓
3. Doğru credentials → admin sayfası açılır ✓
4. Çıkış → login sayfasına döner, `/admin`'e gitmeye çalışınca tekrar redirect ✓

- [ ] **Adım 4: Testleri çalıştır**

```bash
pytest tests/test_admin_auth.py -v
```

Beklenen çıktı:
```
tests/test_admin_auth.py::test_sign_and_verify PASSED
tests/test_admin_auth.py::test_wrong_secret_rejected PASSED
tests/test_admin_auth.py::test_tampered_token_rejected PASSED
tests/test_admin_auth.py::test_expired_token_rejected PASSED
tests/test_admin_auth.py::test_malformed_token_rejected PASSED
5 passed
```

- [ ] **Adım 5: Son commit ve servisi yeniden başlat**

```bash
git add app/templates/admin.html
git commit -m "feat: admin sidebar logout butonu"

sudo systemctl restart mssradmon
```
