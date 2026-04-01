"""Alarm yonetimi — esik kontrolu, GPIO cikislari, e-posta."""
import asyncio
import logging
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from enum import Enum

logger = logging.getLogger(__name__)

try:
    from gpiozero import OutputDevice
except ImportError:
    # GPIO olmayan ortamda (test, gelistirme) mock
    class OutputDevice:
        def __init__(self, pin, **kwargs):
            self.pin = pin
        def on(self): pass
        def off(self): pass
        def close(self): pass


class AlarmLevel(Enum):
    HIGH = "high"
    HIGH_HIGH = "high_high"


class AlarmManager:
    def __init__(self, db, config):
        self._db = db
        self._config = config
        self._active_level: AlarmLevel | None = None
        self._gpio_devices: dict[str, OutputDevice] = {}
        self._buzzer_task: asyncio.Task | None = None

    async def init(self):
        """GPIO cihazlarini baslat."""
        pin_keys = {
            "buzzer": "gpio_buzzer_pin",
            "light": "gpio_light_pin",
            "emergency": "gpio_emergency_pin",
        }
        for name, key in pin_keys.items():
            pin = await self._config.get(key)
            if pin:
                try:
                    self._gpio_devices[name] = OutputDevice(int(pin), initial_value=False)
                except Exception as e:
                    logger.warning("GPIO %s (pin %s) başlatılamadı: %s", name, pin, e)

    async def check(self, dose_rate: float) -> AlarmLevel | None:
        """Doz hizini kontrol et. Alarm tetiklenirse seviyeyi dondur."""
        high = float(await self._config.get("threshold_high") or "0.5")
        high_high = float(await self._config.get("threshold_high_high") or "1.0")

        # Esik altina dustuyse temizle
        if dose_rate < high:
            if self._active_level is not None:
                await self._clear_alarm()
            return None

        # Seviyeyi belirle
        if dose_rate >= high_high:
            new_level = AlarmLevel.HIGH_HIGH
        else:
            new_level = AlarmLevel.HIGH

        # Zaten ayni seviyede aktifse tekrar tetikleme
        if self._active_level == new_level:
            return None

        # Yeni alarm tetikle
        self._active_level = new_level
        await self._trigger_alarm(new_level, dose_rate)
        return new_level

    async def _trigger_alarm(self, level: AlarmLevel, dose_rate: float):
        """Alarm aksiyonlarini calistir."""
        actions_key = f"alarm_{level.value}_actions"
        actions_str = await self._config.get(actions_key) or ""
        actions = [a.strip() for a in actions_str.split(",") if a.strip()]

        # GPIO cikislarini aktifle
        for action in actions:
            if action in self._gpio_devices:
                self._gpio_devices[action].on()

        # Buzzer pattern'i baslat
        if "buzzer" in actions:
            if self._buzzer_task:
                self._buzzer_task.cancel()
            if level == AlarmLevel.HIGH:
                self._buzzer_task = asyncio.create_task(self._buzzer_pattern_high())
            # HIGH_HIGH: buzzer surekli acik kalir (on() zaten cagirildi)

        # DB'ye kaydet
        timestamp = datetime.now(timezone.utc).isoformat()
        action_taken = ",".join(actions)
        await self._db.execute(
            "INSERT INTO alarm_log (timestamp, level, dose_rate, action_taken) VALUES (?, ?, ?, ?)",
            (timestamp, level.value, dose_rate, action_taken),
        )

        # E-posta gonder
        email_enabled = await self._config.get("alarm_email_enabled")
        if email_enabled == "true":
            await self._send_email(level, dose_rate)

        logger.warning("ALARM %s: %.3f µSv/h — aksiyonlar: %s", level.value, dose_rate, action_taken)

    async def _clear_alarm(self):
        """Aktif alarmi temizle, GPIO'lari kapat."""
        if self._buzzer_task:
            self._buzzer_task.cancel()
            self._buzzer_task = None
        for device in self._gpio_devices.values():
            device.off()
        logger.info("Alarm temizlendi (onceki seviye: %s)", self._active_level)
        self._active_level = None

    async def _buzzer_pattern_high(self):
        """High alarm buzzer pattern: 1s acik, 5s kapali."""
        buzzer = self._gpio_devices.get("buzzer")
        if not buzzer:
            return
        try:
            while True:
                buzzer.on()
                await asyncio.sleep(1)
                buzzer.off()
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            buzzer.off()

    async def _send_email(self, level: AlarmLevel, dose_rate: float):
        """SMTP ile alarm e-postasi gonder."""
        try:
            to_addr = await self._config.get("alarm_email_to")
            host = await self._config.get("smtp_host")
            port = int(await self._config.get("smtp_port") or "587")
            user = await self._config.get("smtp_user")
            password = await self._config.get("smtp_pass")

            if not all([to_addr, host, user, password]):
                logger.warning("E-posta ayarlari eksik, gonderilemiyor")
                return

            msg = EmailMessage()
            msg["Subject"] = f"[mssRadMon] ALARM {level.value.upper()}: {dose_rate:.3f} µSv/h"
            msg["From"] = user
            msg["To"] = to_addr
            msg.set_content(
                f"Radyasyon alarmi tetiklendi.\n\n"
                f"Seviye: {level.value.upper()}\n"
                f"Doz Hizi: {dose_rate:.3f} µSv/h\n"
                f"Zaman: {datetime.now(timezone.utc).isoformat()}\n"
                f"Cihaz: GSNJR400"
            )

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._smtp_send, host, port, user, password, msg)
            logger.info("Alarm e-postasi gonderildi: %s", to_addr)
        except Exception as e:
            logger.error("E-posta gonderme hatasi: %s", e)

    @staticmethod
    def _smtp_send(host, port, user, password, msg):
        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)

    async def send_test_email(self) -> dict:
        """Test e-postasi gonder."""
        try:
            to_addr = await self._config.get("alarm_email_to")
            host = await self._config.get("smtp_host")
            port = int(await self._config.get("smtp_port") or "587")
            user = await self._config.get("smtp_user")
            password = await self._config.get("smtp_pass")

            if not all([to_addr, host, user, password]):
                return {"ok": False, "message": "E-posta ayarlari eksik (alici, SMTP sunucu, kullanici, sifre)"}

            msg = EmailMessage()
            msg["Subject"] = "[mssRadMon] Test E-postasi"
            msg["From"] = user
            msg["To"] = to_addr
            msg.set_content(
                f"Bu bir test e-postasıdır.\n\n"
                f"mssRadMon e-posta bildirimleri düzgün çalışıyor.\n"
                f"Zaman: {datetime.now(timezone.utc).isoformat()}\n"
                f"Cihaz: GSNJR400"
            )

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._smtp_send, host, port, user, password, msg)
            logger.info("Test e-postasi gonderildi: %s", to_addr)
            return {"ok": True, "message": f"Test e-postasi gonderildi: {to_addr}"}
        except Exception as e:
            logger.error("Test e-postasi hatasi: %s", e)
            return {"ok": False, "message": str(e)}

    def shutdown(self):
        """GPIO'lari kapat."""
        if self._buzzer_task:
            self._buzzer_task.cancel()
        for device in self._gpio_devices.values():
            device.off()
            device.close()
