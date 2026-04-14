"""Uygulama ayarlari yonetimi -- SQLite settings tablosu uzerinden."""
from app.db import Database

DEFAULTS: dict[str, str] = {
    "device_name": "GammaScout-01",
    "device_location": "",
    "device_serial": "",
    "sampling_interval": "10",
    "threshold_high": "0.5",
    "threshold_high_high": "1.0",
    "threshold_high_duration": "120",
    "threshold_high_high_duration": "15",
    "alarm_buzzer_enabled": "true",
    "alarm_email_enabled": "false",
    "alarm_email_to": "",
    "smtp_host": "",
    "smtp_port": "587",
    "smtp_user": "",
    "smtp_pass": "",
    "remote_log_enabled": "false",
    "remote_log_url": "",
    "remote_log_api_key": "",
    "gpio_buzzer_pin": "17",
    "gpio_light_pin": "27",
    "gpio_emergency_pin": "22",
    "alarm_high_actions": "buzzer,light",
    "alarm_high_high_actions": "buzzer,light,emergency",
    "msg_service_url": "http://192.168.88.112:3501",
    "msg_service_api_key": "",
    "msg_service_mail_enabled": "false",
    "msg_service_wa_enabled": "false",
    "msg_service_reply_to": "",
    "msg_service_high_mail_to": "",
    "msg_service_high_wa_to": "",
    "msg_service_high_high_mail_to": "",
    "msg_service_high_high_wa_to": "",
    "shifts": "[]",
    "calibration_factor": "1.0",
    "api_key": "",
    "ca_server_url": "",
    "ca_api_key": "",
    "ssl_enabled": "false",
    "manager_url": "",
    "manager_register_token": "",
}


class Config:
    def __init__(self, db: Database):
        self._db = db

    async def init(self):
        """Eksik varsayilan ayarlari DB'ye yaz. Mevcutlarin uzerine yazmaz."""
        for key, value in DEFAULTS.items():
            existing = await self._db.fetch_one(
                "SELECT value FROM settings WHERE key = ?", (key,)
            )
            if existing is None:
                await self._db.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?)", (key, value)
                )

    async def get(self, key: str) -> str | None:
        """Tek bir ayar degerini dondur."""
        row = await self._db.fetch_one(
            "SELECT value FROM settings WHERE key = ?", (key,)
        )
        return row["value"] if row else None

    async def set(self, key: str, value: str):
        """Ayar yaz (INSERT OR REPLACE)."""
        await self._db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value)
        )

    async def get_all(self) -> dict[str, str]:
        """Tum ayarlari dict olarak dondur."""
        rows = await self._db.fetch_all("SELECT key, value FROM settings")
        return {row["key"]: row["value"] for row in rows}
