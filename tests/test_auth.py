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


@pytest.mark.asyncio
async def test_get_current_user_valid_cookie():
    """Geçerli cookie ile kullanıcı dict döner."""
    from app.auth import get_current_user, _sign_cookie
    token = _sign_cookie("mssadmin")
    request = MagicMock()
    request.cookies.get = MagicMock(return_value=token)
    request.app.state.db.fetch_one = AsyncMock(return_value={"username": "mssadmin", "role": "admin"})
    result = await get_current_user(request)
    assert result["username"] == "mssadmin"
    assert result["role"] == "admin"


@pytest.mark.asyncio
async def test_get_current_user_invalid_cookie():
    """Geçersiz cookie 401 döner."""
    from fastapi import HTTPException
    from app.auth import get_current_user
    request = MagicMock()
    request.cookies.get = MagicMock(return_value="invalid:token:bad")
    with pytest.raises(HTTPException) as exc:
        await get_current_user(request)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_not_in_db():
    """Geçerli cookie ama DB'de kullanıcı yoksa 401 döner."""
    from fastapi import HTTPException
    from app.auth import get_current_user, _sign_cookie
    token = _sign_cookie("ghost")
    request = MagicMock()
    request.cookies.get = MagicMock(return_value=token)
    request.app.state.db.fetch_one = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as exc:
        await get_current_user(request)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_require_admin_passes_for_admin():
    """admin rolü geçer."""
    from app.auth import require_admin
    result = await require_admin({"username": "mssadmin", "role": "admin"})
    assert result["role"] == "admin"


@pytest.mark.asyncio
async def test_require_admin_rejects_viewer():
    """viewer rolü 403 döner."""
    from fastapi import HTTPException
    from app.auth import require_admin
    with pytest.raises(HTTPException) as exc:
        await require_admin({"username": "op1", "role": "viewer"})
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_admin_or_apikey_viewer_cookie_rejected():
    """viewer cookie 403 döner."""
    from fastapi import HTTPException
    from app.auth import require_admin_or_apikey, _sign_cookie
    token = _sign_cookie("viewer1")
    request = MagicMock()
    request.cookies.get = MagicMock(return_value=token)
    request.app.state.db.fetch_one = AsyncMock(return_value={"role": "viewer"})
    with pytest.raises(HTTPException) as exc:
        await require_admin_or_apikey(request)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_admin_or_apikey_admin_cookie_passes():
    """admin cookie geçer."""
    from app.auth import require_admin_or_apikey, _sign_cookie
    token = _sign_cookie("mssadmin")
    request = MagicMock()
    request.cookies.get = MagicMock(return_value=token)
    request.app.state.db.fetch_one = AsyncMock(return_value={"role": "admin"})
    await require_admin_or_apikey(request)  # exception yok


@pytest.mark.asyncio
async def test_require_admin_or_apikey_no_cookie_passes():
    """Cookie yoksa (API key path) geçer."""
    from app.auth import require_admin_or_apikey
    request = MagicMock()
    request.cookies.get = MagicMock(return_value="")
    await require_admin_or_apikey(request)  # exception yok
