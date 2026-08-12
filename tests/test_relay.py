import pytest
import pytest_asyncio
from unittest.mock import MagicMock

from app import relay as relay_mod
from app.config import Config
from app.db import Database
from app.relay import DEFAULT_PINS, RelayBoard, resolve_channels


class FakeOutputDevice:
    """gpiozero.OutputDevice yerine geçen sahte cihaz — gerçek GPIO'ya dokunmaz."""

    opened: list[int] = []

    def __init__(self, pin, **kwargs):
        self.pin = pin
        self.closed = False
        self._value = False
        FakeOutputDevice.opened.append(pin)

    def on(self):
        self._value = True

    def off(self):
        self._value = False

    @property
    def value(self):
        return 1 if self._value else 0

    def close(self):
        self.closed = True


@pytest.fixture
def fake_gpio(monkeypatch):
    FakeOutputDevice.opened = []
    monkeypatch.setattr(relay_mod, "OutputDevice", FakeOutputDevice)
    return FakeOutputDevice


@pytest_asyncio.fixture
async def config(test_db_path):
    db = Database(test_db_path)
    await db.init()
    cfg = Config(db)
    await cfg.init()
    yield cfg
    await db.close()


@pytest.mark.asyncio
async def test_default_pins_match_relay_board(config):
    """Varsayilan ayarlar Waveshare kartinin pinleriyle ayni olmali (CH1/CH2/CH3)."""
    channels = await resolve_channels(config)
    assert channels == {"buzzer": 26, "light": 20, "emergency": 21}


@pytest.mark.asyncio
async def test_resolve_channels_uses_db_override(config):
    """DB'deki pin degeri varsayilani ezmeli."""
    await config.set("gpio_light_pin", "13")
    channels = await resolve_channels(config)
    assert channels["light"] == 13
    assert channels["buzzer"] == 26


@pytest.mark.asyncio
async def test_resolve_channels_falls_back_on_garbage(config):
    """Bos/gecersiz pin degeri servisi cokertmemeli, varsayilana dusmeli."""
    await config.set("gpio_buzzer_pin", "")
    await config.set("gpio_light_pin", "abc")
    channels = await resolve_channels(config)
    assert channels["buzzer"] == DEFAULT_PINS["buzzer"]
    assert channels["light"] == DEFAULT_PINS["light"]


def test_pins_reports_live_channels(fake_gpio):
    """pins() surecin fiilen surdugu pinleri dondurmeli."""
    board = RelayBoard({"buzzer": 26, "light": 20, "emergency": 21})
    assert board.pins() == {"buzzer": 26, "light": 20, "emergency": 21}


def test_reconfigure_noop_when_unchanged(fake_gpio):
    """Ayni pinlerle cagrilinca cihazlar kapatilip yeniden acilmamali."""
    board = RelayBoard({"buzzer": 26, "light": 20, "emergency": 21})
    devices_before = dict(board._devices)

    assert board.reconfigure({"buzzer": 26, "light": 20, "emergency": 21}) is False
    assert board._devices == devices_before
    assert fake_gpio.opened == [26, 20, 21]


def test_reconfigure_switches_pins(fake_gpio):
    """Pin degisince eski cihazlar kapatilip yeni pinler acilmali."""
    board = RelayBoard({"buzzer": 17, "light": 27, "emergency": 22})
    old_buzzer = board._devices["buzzer"]

    assert board.reconfigure({"buzzer": 26, "light": 20, "emergency": 21}) is True
    assert old_buzzer.closed is True
    assert board.pins() == {"buzzer": 26, "light": 20, "emergency": 21}
    assert fake_gpio.opened == [17, 27, 22, 26, 20, 21]


def test_reconfigure_preserves_active_outputs(fake_gpio):
    """Cekili kanal, pin degisiminden sonra yeni pin uzerinde cekili kalmali."""
    board = RelayBoard({"buzzer": 17, "light": 27, "emergency": 22})
    board.set("buzzer", True)

    board.reconfigure({"buzzer": 26, "light": 20, "emergency": 21})

    assert board.is_on("buzzer") is True
    assert board.is_on("light") is False
    assert board._devices["buzzer"].pin == 26


@pytest.mark.asyncio
async def test_update_settings_reloads_relay_on_pin_change(config, fake_gpio):
    """Panelden pin degistirilince role karti aninda yeniden kurulmali."""
    from app.routers.admin import update_settings

    board = RelayBoard(await resolve_channels(config))
    request = MagicMock()
    request.app.state.config = config
    request.app.state.relay = board

    result = await update_settings(request, {"gpio_light_pin": "13"})

    assert result["relay_reloaded"] is True
    assert board.pins()["light"] == 13


@pytest.mark.asyncio
async def test_update_settings_leaves_relay_alone_without_pin_change(config, fake_gpio):
    """GPIO disi ayar kaydi roleleri yeniden kurmamali."""
    from app.routers.admin import update_settings

    board = RelayBoard(await resolve_channels(config))
    request = MagicMock()
    request.app.state.relay = board
    request.app.state.config = config
    opened_before = list(fake_gpio.opened)

    result = await update_settings(request, {"threshold_high": "0.8"})

    assert result["relay_reloaded"] is False
    assert fake_gpio.opened == opened_before
