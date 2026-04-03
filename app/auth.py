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
