from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.alarm import AlarmManager, AlarmLevel


@pytest.fixture
def alarm_manager():
    """GPIO mock ile AlarmManager."""
    db = AsyncMock()
    config = AsyncMock()
    config.get = AsyncMock(side_effect=lambda k: {
        "threshold_high": "0.5",
        "threshold_high_high": "1.0",
        "alarm_high_actions": "buzzer,light",
        "alarm_high_high_actions": "buzzer,light,emergency",
        "alarm_buzzer_enabled": "true",
        "alarm_email_enabled": "false",
        "gpio_buzzer_pin": "17",
        "gpio_light_pin": "27",
        "gpio_emergency_pin": "22",
    }.get(k))

    patcher = patch("app.alarm.OutputDevice")
    mock_gpio = patcher.start()
    mock_gpio.return_value = MagicMock()
    manager = AlarmManager(db=db, config=config)
    yield manager
    patcher.stop()


@pytest.mark.asyncio
async def test_no_alarm_below_threshold(alarm_manager):
    """Esik altinda alarm tetiklenmemeli."""
    await alarm_manager.init()
    level = await alarm_manager.check(0.3)
    assert level is None


@pytest.mark.asyncio
async def test_high_alarm(alarm_manager):
    """High esiginde alarm tetiklenmeli."""
    await alarm_manager.init()
    level = await alarm_manager.check(0.6)
    assert level == AlarmLevel.HIGH


@pytest.mark.asyncio
async def test_high_high_alarm(alarm_manager):
    """High-High esiginde alarm tetiklenmeli."""
    await alarm_manager.init()
    level = await alarm_manager.check(1.5)
    assert level == AlarmLevel.HIGH_HIGH


@pytest.mark.asyncio
async def test_alarm_not_retriggered(alarm_manager):
    """Ayni seviye tekrar tetiklenmemeli."""
    await alarm_manager.init()
    level1 = await alarm_manager.check(0.6)
    assert level1 == AlarmLevel.HIGH
    level2 = await alarm_manager.check(0.7)
    assert level2 is None  # Zaten aktif, tekrar tetiklenmez


@pytest.mark.asyncio
async def test_alarm_clears_below_threshold(alarm_manager):
    """Esik altina dusunce alarm temizlenmeli ve tekrar tetiklenebilmeli."""
    await alarm_manager.init()
    await alarm_manager.check(0.6)  # HIGH tetikle
    await alarm_manager.check(0.3)  # Esik alti — temizle
    level = await alarm_manager.check(0.6)  # Tekrar tetiklenebilmeli
    assert level == AlarmLevel.HIGH


@pytest.mark.asyncio
async def test_alarm_logged_to_db(alarm_manager):
    """Alarm tetiklenince DB'ye yazilmali."""
    await alarm_manager.init()
    await alarm_manager.check(0.6)
    alarm_manager._db.execute.assert_called_once()
    call_args = alarm_manager._db.execute.call_args
    assert "alarm_log" in call_args[0][0]
