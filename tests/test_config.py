import pytest
import pytest_asyncio

from app.config import Config, DEFAULTS
from app.db import Database


@pytest_asyncio.fixture
async def config(test_db_path):
    db = Database(test_db_path)
    await db.init()
    cfg = Config(db)
    await cfg.init()
    yield cfg
    await db.close()


@pytest.mark.asyncio
async def test_defaults_loaded(config):
    """init() tum varsayilan ayarlari yuklemeli."""
    val = await config.get("sampling_interval")
    assert val == "10"


@pytest.mark.asyncio
async def test_get_nonexistent_returns_none(config):
    """Olmayan anahtar None dondurmeli."""
    val = await config.get("nonexistent_key")
    assert val is None


@pytest.mark.asyncio
async def test_set_and_get(config):
    """Ayar yazip okuyabilmeli."""
    await config.set("threshold_high", "0.8")
    val = await config.get("threshold_high")
    assert val == "0.8"


@pytest.mark.asyncio
async def test_get_all(config):
    """Tum ayarlari dict olarak dondurmeli."""
    all_settings = await config.get_all()
    assert isinstance(all_settings, dict)
    assert all_settings["sampling_interval"] == "10"
    assert all_settings["threshold_high"] == "0.5"


@pytest.mark.asyncio
async def test_defaults_not_overwritten(config):
    """Mevcut ayar varsa init() uzerine yazmamali."""
    await config.set("sampling_interval", "30")
    # Tekrar init() cagir
    await config.init()
    val = await config.get("sampling_interval")
    assert val == "30"
