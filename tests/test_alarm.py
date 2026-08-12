from unittest.mock import AsyncMock, MagicMock

import pytest

from app.alarm import AlarmManager, AlarmLevel


@pytest.fixture
def alarm_manager():
    """Mock'lanmış röle ile AlarmManager. Eşik süreleri 0 → anında tetikleme."""
    db = AsyncMock()
    config = AsyncMock()
    config.get = AsyncMock(side_effect=lambda k: {
        "threshold_high": "0.5",
        "threshold_high_high": "1.0",
        "threshold_critical": "10.0",
        "threshold_high_duration": "0",
        "threshold_high_high_duration": "0",
        "threshold_critical_duration": "0",
        "alarm_high_actions": "buzzer,light",
        "alarm_high_high_actions": "buzzer,light,emergency",
        "alarm_critical_actions": "buzzer,light,emergency",
        "alarm_buzzer_enabled": "true",
        "alarm_email_enabled": "false",
    }.get(k))

    relay = MagicMock()
    relay.has.return_value = True
    relay.is_on.return_value = False
    manager = AlarmManager(db=db, config=config, relay=relay)
    return manager


async def _trigger(manager, dose_rate):
    """İlk check sayacı başlatır, ikincisi (duration=0 mock'lu) tetikler."""
    await manager.check(dose_rate)
    return await manager.check(dose_rate)


@pytest.mark.asyncio
async def test_no_alarm_below_threshold(alarm_manager):
    """Esik altinda alarm tetiklenmemeli."""
    level = await _trigger(alarm_manager, 0.3)
    assert level is None


@pytest.mark.asyncio
async def test_high_alarm(alarm_manager):
    """High esiginde alarm tetiklenmeli."""
    level = await _trigger(alarm_manager, 0.6)
    assert level == AlarmLevel.HIGH


@pytest.mark.asyncio
async def test_high_high_alarm(alarm_manager):
    """High-High esiginde alarm tetiklenmeli."""
    level = await _trigger(alarm_manager, 1.5)
    assert level == AlarmLevel.HIGH_HIGH


@pytest.mark.asyncio
async def test_alarm_not_retriggered(alarm_manager):
    """Ayni seviye tekrar tetiklenmemeli."""
    level1 = await _trigger(alarm_manager, 0.6)
    assert level1 == AlarmLevel.HIGH
    level2 = await alarm_manager.check(0.7)
    assert level2 is None  # Zaten aktif, tekrar tetiklenmez


@pytest.mark.asyncio
async def test_alarm_clears_below_threshold(alarm_manager):
    """Esik altina dusunce alarm temizlenmeli ve tekrar tetiklenebilmeli."""
    await _trigger(alarm_manager, 0.6)  # HIGH tetikle
    await alarm_manager.check(0.3)  # Esik alti — temizle
    level = await _trigger(alarm_manager, 0.6)  # Tekrar tetiklenebilmeli
    assert level == AlarmLevel.HIGH


@pytest.mark.asyncio
async def test_alarm_logged_to_db(alarm_manager):
    """Alarm tetiklenince DB'ye yazilmali."""
    await _trigger(alarm_manager, 0.6)
    alarm_manager._db.execute.assert_called_once()
    call_args = alarm_manager._db.execute.call_args
    assert "alarm_log" in call_args[0][0]


@pytest.mark.asyncio
async def test_relay_set_on_trigger(alarm_manager):
    """Alarm tetiklenince ilgili röle kanalları çekilmeli."""
    await _trigger(alarm_manager, 0.6)  # HIGH → buzzer + light
    names_called = {c.args[0] for c in alarm_manager._relay.set.call_args_list if c.args[1] is True}
    assert "buzzer" in names_called
    assert "light" in names_called
    assert "emergency" not in names_called  # high actions'da yok
