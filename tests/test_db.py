import pytest
import pytest_asyncio

from app.db import Database


@pytest_asyncio.fixture
async def db(test_db_path):
    database = Database(test_db_path)
    await database.init()
    yield database
    await database.close()


@pytest.mark.asyncio
async def test_tables_created(db):
    """init() readings, settings, alarm_log tablolarini olusturmali."""
    tables = await db.fetch_all(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    names = [row["name"] for row in tables]
    assert "alarm_log" in names
    assert "readings" in names
    assert "settings" in names


@pytest.mark.asyncio
async def test_insert_reading(db):
    """Olcum verisi eklenebilmeli."""
    await db.execute(
        "INSERT INTO readings (timestamp, dose_rate, cumulative_dose) VALUES (?, ?, ?)",
        ("2026-03-31T12:00:00Z", 0.12, 45.6),
    )
    rows = await db.fetch_all("SELECT * FROM readings")
    assert len(rows) == 1
    assert rows[0]["dose_rate"] == 0.12
    assert rows[0]["cumulative_dose"] == 45.6
    assert rows[0]["remote_synced"] == 0


@pytest.mark.asyncio
async def test_insert_alarm(db):
    """Alarm kaydi eklenebilmeli."""
    await db.execute(
        "INSERT INTO alarm_log (timestamp, level, dose_rate, action_taken) VALUES (?, ?, ?, ?)",
        ("2026-03-31T12:00:00Z", "high", 0.55, "buzzer,light"),
    )
    rows = await db.fetch_all("SELECT * FROM alarm_log")
    assert len(rows) == 1
    assert rows[0]["level"] == "high"


@pytest.mark.asyncio
async def test_readings_by_time_range(db):
    """Zaman araligina gore okuma sorgusu."""
    await db.execute(
        "INSERT INTO readings (timestamp, dose_rate, cumulative_dose) VALUES (?, ?, ?)",
        ("2026-03-31T10:00:00Z", 0.10, 10.0),
    )
    await db.execute(
        "INSERT INTO readings (timestamp, dose_rate, cumulative_dose) VALUES (?, ?, ?)",
        ("2026-03-31T12:00:00Z", 0.12, 20.0),
    )
    rows = await db.fetch_all(
        "SELECT * FROM readings WHERE timestamp >= ? ORDER BY timestamp",
        ("2026-03-31T11:00:00Z",),
    )
    assert len(rows) == 1
    assert rows[0]["dose_rate"] == 0.12
