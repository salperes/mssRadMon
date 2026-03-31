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
