"""Remote log forwarding — HTTP POST ile uzak sunucuya veri iletimi."""
import asyncio
import logging

import aiohttp

logger = logging.getLogger(__name__)

BATCH_SIZE = 100
RETRY_DELAYS = [5, 15, 45]


class RemoteLogForwarder:
    def __init__(self, db, config):
        self._db = db
        self._config = config

    async def _is_enabled(self) -> bool:
        return (await self._config.get("remote_log_enabled")) == "true"

    async def _get_url(self) -> str:
        return await self._config.get("remote_log_url") or ""

    async def _get_api_key(self) -> str:
        return await self._config.get("remote_log_api_key") or ""

    async def _device_info(self) -> dict:
        name = await self._config.get("device_name") or "GammaScout-01"
        location = await self._config.get("device_location") or ""
        return {"device_name": name, "device_location": location}

    async def forward_reading(self, timestamp: str, dose_rate: float,
                               cumulative_dose: float, row_id: int):
        """Tek bir okumayı uzak sunucuya gönder."""
        if not await self._is_enabled():
            return

        url = await self._get_url()
        api_key = await self._get_api_key()
        if not url:
            return

        info = await self._device_info()
        payload = {
            **info,
            "timestamp": timestamp,
            "dose_rate": dose_rate,
            "cumulative_dose": cumulative_dose,
        }

        success = await self._post(f"{url}/reading", api_key, payload)
        if success:
            await self._db.execute(
                "UPDATE readings SET remote_synced = 1 WHERE id = ?", (row_id,)
            )

    async def forward_alarm(self, timestamp: str, level: str,
                             dose_rate: float, action_taken: str, row_id: int):
        """Tek bir alarm kaydını uzak sunucuya gönder."""
        if not await self._is_enabled():
            return

        url = await self._get_url()
        api_key = await self._get_api_key()
        if not url:
            return

        info = await self._device_info()
        payload = {
            **info,
            "timestamp": timestamp,
            "level": level,
            "dose_rate": dose_rate,
            "action_taken": action_taken,
        }

        success = await self._post(f"{url}/alarm", api_key, payload)
        if success:
            await self._db.execute(
                "UPDATE alarm_log SET remote_synced = 1 WHERE id = ?", (row_id,)
            )

    async def sync_unsynced(self):
        """Senkronize edilmemiş tüm kayıtları batch halinde gönder."""
        if not await self._is_enabled():
            return

        # Okumaları senkronize et
        rows = await self._db.fetch_all(
            "SELECT id, timestamp, dose_rate, cumulative_dose FROM readings "
            "WHERE remote_synced = 0 ORDER BY timestamp LIMIT ?",
            (BATCH_SIZE,),
        )
        for row in rows:
            await self.forward_reading(
                row["timestamp"], row["dose_rate"], row["cumulative_dose"], row["id"]
            )

        # Alarmları senkronize et
        alarm_rows = await self._db.fetch_all(
            "SELECT id, timestamp, level, dose_rate, action_taken FROM alarm_log "
            "WHERE remote_synced = 0 ORDER BY timestamp LIMIT ?",
            (BATCH_SIZE,),
        )
        for row in alarm_rows:
            await self.forward_alarm(
                row["timestamp"], row["level"], row["dose_rate"],
                row["action_taken"], row["id"]
            )

    async def _post(self, url: str, api_key: str, payload: dict) -> bool:
        """HTTP POST ile veri gönder. Retry mekanizması ile."""
        headers = {"X-API-Key": api_key, "Content-Type": "application/json"}

        for attempt, delay in enumerate(RETRY_DELAYS):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status == 200:
                            return True
                        logger.warning("Remote log POST %s: HTTP %d (deneme %d)", url, resp.status, attempt + 1)
            except Exception as e:
                logger.warning("Remote log POST hatası: %s (deneme %d)", e, attempt + 1)

            if attempt < len(RETRY_DELAYS) - 1:
                await asyncio.sleep(delay)

        logger.error("Remote log POST başarısız: %s (%d deneme tükendi)", url, len(RETRY_DELAYS))
        return False

    async def run_sync_loop(self, interval: int = 60):
        """Periyodik senkronizasyon döngüsü."""
        while True:
            try:
                await self.sync_unsynced()
            except Exception as e:
                logger.error("Sync döngüsü hatası: %s", e)
            await asyncio.sleep(interval)
