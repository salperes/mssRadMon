from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.remote_log import RemoteLogForwarder


@pytest.fixture
def forwarder():
    db = AsyncMock()
    config = AsyncMock()
    config.get = AsyncMock(side_effect=lambda k: {
        "remote_log_enabled": "true",
        "remote_log_url": "http://example.com/api",
        "remote_log_api_key": "test-key",
    }.get(k))
    return RemoteLogForwarder(db=db, config=config)


@pytest.mark.asyncio
async def test_disabled_does_nothing(forwarder):
    """remote_log_enabled=false ise hiçbir şey yapmamalı."""
    forwarder._config.get = AsyncMock(side_effect=lambda k: {
        "remote_log_enabled": "false",
        "remote_log_url": "",
        "remote_log_api_key": "",
    }.get(k))
    with patch("aiohttp.ClientSession") as mock_session:
        await forwarder.forward_reading(
            timestamp="2026-03-31T12:00:00Z", dose_rate=0.12, cumulative_dose=45.6, row_id=1
        )
        mock_session.assert_not_called()


@pytest.mark.asyncio
async def test_forward_reading_success(forwarder):
    """Başarılı push sonrası remote_synced=1 yapılmalı."""
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.post = MagicMock(return_value=mock_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        await forwarder.forward_reading(
            timestamp="2026-03-31T12:00:00Z", dose_rate=0.12, cumulative_dose=45.6, row_id=1
        )

    # remote_synced=1 güncellenmeli
    forwarder._db.execute.assert_called_with(
        "UPDATE readings SET remote_synced = 1 WHERE id = ?", (1,)
    )


@pytest.mark.asyncio
async def test_sync_unsynced_readings(forwarder):
    """Senkronize edilmemiş kayıtları batch olarak göndermeli."""
    forwarder._db.fetch_all = AsyncMock(side_effect=[
        [  # readings
            {"id": 1, "timestamp": "2026-03-31T10:00:00Z", "dose_rate": 0.10, "cumulative_dose": 10.0},
            {"id": 2, "timestamp": "2026-03-31T10:00:10Z", "dose_rate": 0.11, "cumulative_dose": 10.5},
        ],
        [],  # alarm_log (boş)
    ])

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.post = MagicMock(return_value=mock_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        await forwarder.sync_unsynced()

    assert forwarder._db.execute.call_count == 2  # Her satır için UPDATE
