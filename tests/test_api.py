import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone, timedelta

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

    recent_ts = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    await db.execute(
        "INSERT INTO alarm_log (timestamp, level, dose_rate, action_taken) VALUES (?, ?, ?, ?)",
        (recent_ts, "high", 0.55, "buzzer,light"),
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
    request.app.state.alarm = MagicMock()
    request.app.state.alarm.get_pending_info = AsyncMock(return_value={
        "alarm_pending": False, "alarm_pending_level": None,
        "alarm_pending_elapsed": 0, "alarm_pending_duration": 0,
    })

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
    request.app.state.alarm = MagicMock()
    request.app.state.alarm.get_pending_info = AsyncMock(return_value={
        "alarm_pending": False, "alarm_pending_level": None,
        "alarm_pending_elapsed": 0, "alarm_pending_duration": 0,
    })

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


def test_period_start_iso_day():
    """Günlük başlangıç: bugünün UTC+3 gece yarısı → UTC'ye çevrilmiş."""
    from app.routers.api import _period_start_iso, TZ_TR
    now_local = datetime(2026, 4, 2, 14, 30, 0, tzinfo=TZ_TR)
    result = _period_start_iso(now_local, "day")
    # 2026-04-02 00:00 UTC+3 = 2026-04-01 21:00 UTC
    assert result == "2026-04-01T21:00:00+00:00"


def test_period_start_iso_month():
    from app.routers.api import _period_start_iso, TZ_TR
    now_local = datetime(2026, 4, 15, 10, 0, 0, tzinfo=TZ_TR)
    result = _period_start_iso(now_local, "month")
    # 2026-04-01 00:00 UTC+3 = 2026-03-31 21:00 UTC
    assert result == "2026-03-31T21:00:00+00:00"


def test_period_start_iso_quarter_q2():
    """Nisan Q2'de (Nis-Haz), başlangıç Nisan 1."""
    from app.routers.api import _period_start_iso, TZ_TR
    now_local = datetime(2026, 5, 20, 10, 0, 0, tzinfo=TZ_TR)
    result = _period_start_iso(now_local, "quarter")
    # 2026-04-01 00:00 UTC+3 = 2026-03-31 21:00 UTC
    assert result == "2026-03-31T21:00:00+00:00"


def test_period_start_iso_quarter_q1():
    """Ocak Q1'de (Oca-Mar), başlangıç Ocak 1."""
    from app.routers.api import _period_start_iso, TZ_TR
    now_local = datetime(2026, 2, 10, 10, 0, 0, tzinfo=TZ_TR)
    result = _period_start_iso(now_local, "quarter")
    # 2026-01-01 00:00 UTC+3 = 2025-12-31 21:00 UTC
    assert result == "2025-12-31T21:00:00+00:00"


def test_period_start_iso_half_year_h2():
    """Temmuz–Aralık H2, başlangıç Temmuz 1."""
    from app.routers.api import _period_start_iso, TZ_TR
    now_local = datetime(2026, 9, 1, 10, 0, 0, tzinfo=TZ_TR)
    result = _period_start_iso(now_local, "half_year")
    # 2026-07-01 00:00 UTC+3 = 2026-06-30 21:00 UTC
    assert result == "2026-06-30T21:00:00+00:00"


def test_period_start_iso_year():
    from app.routers.api import _period_start_iso, TZ_TR
    now_local = datetime(2026, 4, 2, 10, 0, 0, tzinfo=TZ_TR)
    result = _period_start_iso(now_local, "year")
    # 2026-01-01 00:00 UTC+3 = 2025-12-31 21:00 UTC
    assert result == "2025-12-31T21:00:00+00:00"


@pytest.mark.asyncio
async def test_calc_period_dose_empty(test_db_path):
    """Veri yoksa 0.0 döndürmeli."""
    from app.routers.api import _calc_period_dose
    db = Database(test_db_path)
    await db.init()
    result = await _calc_period_dose(db, "2026-01-01T00:00:00+00:00")
    assert result == 0.0
    await db.close()


@pytest.mark.asyncio
async def test_calc_period_dose_with_data(test_db_path):
    """İlk ve son cumulative_dose farkını hesaplamalı."""
    from app.routers.api import _calc_period_dose
    db = Database(test_db_path)
    await db.init()
    await db.execute(
        "INSERT INTO readings (timestamp, dose_rate, cumulative_dose) VALUES (?, ?, ?)",
        ("2026-04-01T22:00:00+00:00", 0.10, 100.0),
    )
    await db.execute(
        "INSERT INTO readings (timestamp, dose_rate, cumulative_dose) VALUES (?, ?, ?)",
        ("2026-04-02T08:00:00+00:00", 0.12, 115.5),
    )
    result = await _calc_period_dose(db, "2026-04-01T21:00:00+00:00")
    assert result == 15.5
    await db.close()


@pytest.mark.asyncio
async def test_get_period_doses_returns_all_keys(seeded_db):
    """Endpoint tüm periyot anahtarlarını döndürmeli."""
    from app.routers.api import get_period_doses
    db, config = seeded_db
    request = MagicMock()
    request.app.state.db = db
    result = await get_period_doses(request)
    assert set(result.keys()) == {"daily", "monthly", "quarterly", "half_yearly", "yearly"}
    for v in result.values():
        assert isinstance(v, float)


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
