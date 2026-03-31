from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

import pytest

from app.serial_reader import GammaScoutReader, Reading, DeviceInfo


@pytest.fixture
def reader():
    """Test reader (bağlantı yok)."""
    return GammaScoutReader(port="/dev/ttyUSB0", baudrate=460800)


# --- Reading dataclass ---

def test_reading_dataclass():
    r = Reading(timestamp="2026-03-31T12:00:00Z", dose_rate=0.12, cumulative_dose=45.6)
    assert r.dose_rate == 0.12
    assert r.cumulative_dose == 45.6
    assert r.timestamp == "2026-03-31T12:00:00Z"


# --- parse_online_data ---

def test_parse_online_data_device_format(reader):
    """Gerçek cihaz formatı: '0,166 uSv/h' parse edilmeli."""
    assert reader.parse_online_data(b"0,166 uSv/h\r\n") == 0.166


def test_parse_online_data_dot_format(reader):
    """Noktalı format da desteklenmeli."""
    assert reader.parse_online_data(b"0.12 uSv/h\r\n") == 0.12


def test_parse_online_data_integer(reader):
    assert reader.parse_online_data(b"3 uSv/h\r\n") == 3.0


def test_parse_online_data_multiline(reader):
    """Birden fazla satırda son geçerli değer alınmalı."""
    raw = b"Online x\r\n0,08 uSv/h\r\n0,12 uSv/h\r\n"
    assert reader.parse_online_data(raw) == 0.12


def test_parse_online_data_empty(reader):
    assert reader.parse_online_data(b"") is None


def test_parse_online_data_none(reader):
    assert reader.parse_online_data(None) is None


def test_parse_online_data_garbage(reader):
    assert reader.parse_online_data(b"\xff\xfe\x00\x01") is None


def test_parse_online_data_only_text(reader):
    """Sadece non-numeric metin satırları varsa None dönmeli."""
    assert reader.parse_online_data(b"Standard\r\n") is None


# --- _parse_version ---

def test_parse_version_valid(reader):
    raw = b"7.14Lb07 6.90 085875 1234 31.03.26 12:00\r\n"
    info = reader._parse_version(raw)
    assert isinstance(info, DeviceInfo)
    assert info.firmware == "7.14Lb07"
    assert info.serial_number == "085875"


def test_parse_version_empty(reader):
    assert reader._parse_version(b"") is None


def test_parse_version_none(reader):
    assert reader._parse_version(None) is None


# --- connect / disconnect ---

def test_connect_success(reader):
    with patch("serial.Serial") as mock_cls:
        mock_ser = MagicMock()
        mock_cls.return_value = mock_ser
        assert reader.connect() is True
        assert reader.connected is True
        mock_cls.assert_called_once()


def test_connect_failure(reader):
    import serial as pyserial
    with patch("serial.Serial", side_effect=pyserial.SerialException("port yok")):
        assert reader.connect() is False
        assert reader.connected is False


def test_disconnect(reader):
    mock_ser = MagicMock()
    mock_ser.is_open = True
    reader._serial = mock_ser
    reader._connected = True

    reader.disconnect()

    mock_ser.write.assert_called_with(b"X")
    mock_ser.close.assert_called_once()
    assert reader.connected is False


# --- read_once ---

def test_read_once_returns_dose_rate(reader):
    mock_ser = MagicMock()
    mock_ser.is_open = True
    mock_ser.readline.return_value = b"0,150 uSv/h\r\n"
    reader._serial = mock_ser

    result = reader.read_once()
    assert result == 0.15


def test_read_once_no_serial(reader):
    assert reader.read_once() is None


def test_read_once_serial_error(reader):
    import serial as pyserial
    mock_ser = MagicMock()
    mock_ser.is_open = True
    mock_ser.readline.side_effect = pyserial.SerialException("hata")
    reader._serial = mock_ser
    reader._connected = True

    result = reader.read_once()
    assert result is None
    assert reader.connected is False


# --- run loop ---

@pytest.mark.asyncio
async def test_run_calls_callback(reader):
    """Run döngüsü okuma yapıp callback çağırmalı."""
    callback = AsyncMock()
    reader.on_reading(callback)

    # Mock connect + enter_online_mode + read_once
    reader.connect = MagicMock(return_value=True)
    reader.enter_online_mode = MagicMock(return_value=True)
    reader._connected = True

    call_count = 0

    def fake_read_once():
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            return 0.12
        reader._running = False  # 2 okumadan sonra dur
        return None

    reader.read_once = fake_read_once

    await reader.run(interval=0)

    assert callback.call_count == 2
    args = callback.call_args_list[0][0][0]
    assert isinstance(args, Reading)
    assert args.dose_rate == 0.12


@pytest.mark.asyncio
async def test_run_reconnects_on_disconnect(reader):
    """Bağlantı kopunca reconnect denemeli."""
    reader.on_reading(AsyncMock())
    connect_calls = 0

    def fake_connect():
        nonlocal connect_calls
        connect_calls += 1
        if connect_calls >= 2:
            reader._running = False
        return False

    reader.connect = fake_connect

    await reader.run(interval=0)

    assert connect_calls >= 2
