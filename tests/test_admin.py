import pytest
import pytest_asyncio
from unittest.mock import MagicMock

from app.db import Database
from app.config import Config


@pytest_asyncio.fixture
async def admin_deps(test_db_path):
    db = Database(test_db_path)
    await db.init()
    config = Config(db)
    await config.init()
    yield db, config
    await db.close()


@pytest.mark.asyncio
async def test_get_settings(admin_deps):
    """GET /api/settings tüm ayarları döndürmeli."""
    from app.routers.admin import get_settings

    db, config = admin_deps
    request = MagicMock()
    request.app.state.config = config

    result = await get_settings(request)
    assert result["sampling_interval"] == "10"
    assert result["threshold_high"] == "0.5"


@pytest.mark.asyncio
async def test_update_settings(admin_deps):
    """PUT /api/settings ayarları güncellemeli."""
    from app.routers.admin import update_settings

    db, config = admin_deps
    request = MagicMock()
    request.app.state.config = config

    result = await update_settings(request, {"threshold_high": "0.8", "sampling_interval": "30"})
    assert result["status"] == "ok"

    val = await config.get("threshold_high")
    assert val == "0.8"
    val2 = await config.get("sampling_interval")
    assert val2 == "30"


@pytest.mark.asyncio
async def test_update_settings_viewer_rejected():
    """viewer rolüyle PUT /api/settings 403 dönmeli."""
    import tempfile
    import os
    from fastapi import HTTPException
    from app.routers.admin import update_settings, router
    from app.auth import _sign_cookie, _hash_password
    from app.db import Database
    from app.config import Config

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        db = Database(path)
        await db.init()
        config = Config(db)
        await config.init()
        await db.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("viewer1", _hash_password("pass", "viewer1"), "viewer"),
        )
        token = _sign_cookie("viewer1")
        request = MagicMock()
        request.app.state.config = config
        request.app.state.db = db
        request.cookies.get = lambda key, default="": token if key == "mssradmon_session" else default
        request.headers.get = MagicMock(return_value=None)
        # Auth fonksiyonunun 403 verdiğini doğrula
        from app.auth import require_admin_or_apikey
        with pytest.raises(HTTPException) as exc:
            await require_admin_or_apikey(request)
        assert exc.value.status_code == 403
        # Endpoint'in dependency olarak tanımlandığını doğrula
        put_route = next(r for r in router.routes if getattr(r, "path", "") == "/api/settings" and "PUT" in getattr(r, "methods", set()))
        dep_calls = [d.dependency for d in put_route.dependencies]
        assert require_admin_or_apikey in dep_calls, "require_admin_or_apikey /settings PUT'a bağlı değil"
        await db.close()
    finally:
        os.unlink(path)
