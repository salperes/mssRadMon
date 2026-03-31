import pytest
import pytest_asyncio
from unittest.mock import MagicMock

from app.db import Database
from app.config import Config


@pytest_asyncio.fixture
async def seeded_db(test_db_path):
    """Test verileri ile doldurulmuş DB."""
    db = Database(test_db_path)
    await db.init()
    config = Config(db)
    await config.init()

    await db.execute(
        "INSERT INTO readings (timestamp, dose_rate, cumulative_dose) VALUES (?, ?, ?)",
        ("2026-03-31T10:00:00Z", 0.10, 10.0),
    )
    await db.execute(
        "INSERT INTO readings (timestamp, dose_rate, cumulative_dose) VALUES (?, ?, ?)",
        ("2026-03-31T12:00:00Z", 0.15, 20.0),
    )
    await db.execute(
        "INSERT INTO readings (timestamp, dose_rate, cumulative_dose) VALUES (?, ?, ?)",
        ("2026-03-31T23:00:00Z", 0.12, 30.0),
    )

    await db.execute(
        "INSERT INTO alarm_log (timestamp, level, dose_rate, action_taken) VALUES (?, ?, ?, ?)",
        ("2026-03-31T12:00:00Z", "high", 0.55, "buzzer,light"),
    )

    yield db, config
    await db.close()


@pytest.mark.asyncio
async def test_get_current(seeded_db):
    """GET /api/current son okumayı döndürmeli."""
    from app.routers.api import get_current

    db, config = seeded_db
    request = MagicMock()
    request.app.state.db = db
    request.app.state.reader = MagicMock()
    request.app.state.reader.connected = True

    result = await get_current(request)
    assert result["dose_rate"] == 0.12
    assert result["cumulative_dose"] == 30.0
    assert result["connected"] is True


@pytest.mark.asyncio
async def test_get_current_empty(test_db_path):
    """Veri yoksa None döndürmeli."""
    from app.routers.api import get_current

    db = Database(test_db_path)
    await db.init()
    request = MagicMock()
    request.app.state.db = db
    request.app.state.reader = MagicMock()
    request.app.state.reader.connected = False

    result = await get_current(request)
    assert result["dose_rate"] is None
    assert result["connected"] is False
    await db.close()


@pytest.mark.asyncio
async def test_get_alarms(seeded_db):
    """GET /api/alarms alarm geçmişini döndürmeli."""
    from app.routers.api import get_alarms

    db, config = seeded_db
    request = MagicMock()
    request.app.state.db = db

    result = await get_alarms(request, last="24h")
    assert len(result) == 1
    assert result[0]["level"] == "high"


@pytest.mark.asyncio
async def test_get_status(seeded_db):
    """GET /api/status cihaz durumunu döndürmeli."""
    from app.routers.api import get_status

    db, config = seeded_db
    request = MagicMock()
    request.app.state.reader = MagicMock()
    request.app.state.reader.connected = True
    request.app.state.reader.port = "/dev/ttyUSB0"

    result = await get_status(request)
    assert result["connected"] is True
    assert result["port"] == "/dev/ttyUSB0"
