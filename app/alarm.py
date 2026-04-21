"""Alarm yonetimi — esik kontrolu, GPIO cikislari, e-posta."""
import asyncio
import logging
from app import msg_service
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from enum import Enum
import time

logger = logging.getLogger(__name__)


def _local_time() -> str:
    """Lokal zaman: HH:MM - DD/MM/YYYY"""
    return datetime.now().strftime("%H:%M - %d/%m/%Y")

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
        self._exceed_start: float | None = None
        self._exceed_level: AlarmLevel | None = None
        self._active_alarm_id: int | None = None

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
        """Doz hizini kontrol et. Sure dolunca alarm tetikle."""
        high = float(await self._config.get("threshold_high") or "0.5")
        high_high = float(await self._config.get("threshold_high_high") or "1.0")
        high_dur = float(await self._config.get("threshold_high_duration") or "120")
        high_high_dur = float(await self._config.get("threshold_high_high_duration") or "15")

        # Esik altina dustuyse sayaci sifirla ve temizle
        if dose_rate < high:
            self._exceed_start = None
            self._exceed_level = None
            if self._active_level is not None:
                await self._clear_alarm()
            return None

        # Seviyeyi belirle
        if dose_rate >= high_high:
            new_level = AlarmLevel.HIGH_HIGH
            required_dur = high_high_dur
        else:
            new_level = AlarmLevel.HIGH
            required_dur = high_dur

        now = time.monotonic()

        # Seviye degistiyse sayaci sifirla
        if self._exceed_level != new_level:
            self._exceed_start = now
            self._exceed_level = new_level
            return None

        # Gecen sureyi hesapla
        elapsed = now - self._exceed_start

        # Sure dolmadiysa pending olarak kal
        if elapsed < required_dur:
            return None

        # Zaten ayni seviyede aktif alarm varsa — exceed_duration guncelle
        if self._active_level == new_level:
            await self._update_exceed_duration(elapsed)
            return None

        # Sure doldu — alarm tetikle
        self._active_level = new_level
        self._active_alarm_id = await self._trigger_alarm(new_level, dose_rate, elapsed)
        return new_level

    async def get_pending_info(self) -> dict:
        """Pending alarm bilgisi — dashboard ve WS icin."""
        if self._exceed_start is None or self._exceed_level is None or self._active_level == self._exceed_level:
            return {
                "alarm_pending": False,
                "alarm_pending_level": None,
                "alarm_pending_elapsed": 0,
                "alarm_pending_duration": 0,
            }
        elapsed = time.monotonic() - self._exceed_start
        dur_key = f"threshold_{self._exceed_level.value}_duration"
        duration = float(await self._config.get(dur_key) or "0")
        return {
            "alarm_pending": True,
            "alarm_pending_level": self._exceed_level.value,
            "alarm_pending_elapsed": round(elapsed),
            "alarm_pending_duration": round(duration),
        }

    async def _trigger_alarm(self, level: AlarmLevel, dose_rate: float, exceed_duration: float = 0) -> int | None:
        """Alarm aksiyonlarini calistir. Alarm log row ID dondurur."""
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
        row_id = await self._db.execute(
            "INSERT INTO alarm_log (timestamp, level, dose_rate, action_taken, exceed_duration) VALUES (?, ?, ?, ?, ?)",
            (timestamp, level.value, dose_rate, action_taken, round(exceed_duration)),
        )

        # E-posta gonder
        email_enabled = await self._config.get("alarm_email_enabled")
        if email_enabled == "true":
            await self._send_email(level, dose_rate)

        # msgService bildirimleri
        await self._send_msgservice_mail(level, dose_rate)
        await self._send_msgservice_wa(level, dose_rate)

        logger.warning("ALARM %s: %.3f µSv/h — süre: %ds — aksiyonlar: %s", level.value, dose_rate, round(exceed_duration), action_taken)
        return row_id

    async def _update_exceed_duration(self, elapsed: float):
        """Aktif alarm kaydinin exceed_duration'ini guncelle."""
        if not self._active_alarm_id:
            return
        await self._db.execute(
            "UPDATE alarm_log SET exceed_duration = ? WHERE id = ?",
            (round(elapsed), self._active_alarm_id),
        )

    async def _clear_alarm(self):
        """Aktif alarmi temizle, GPIO'lari kapat."""
        # Kapanmadan once son exceed_duration'i kaydet
        if self._exceed_start is not None and self._active_alarm_id:
            final_elapsed = time.monotonic() - self._exceed_start
            await self._update_exceed_duration(final_elapsed)
        if self._buzzer_task:
            self._buzzer_task.cancel()
            self._buzzer_task = None
        for device in self._gpio_devices.values():
            device.off()
        logger.info("Alarm temizlendi (onceki seviye: %s)", self._active_level)
        self._active_level = None
        self._active_alarm_id = None

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

            device_name = await self._config.get("device_name") or "GammaScout-01"
            device_serial = await self._config.get("device_serial") or ""
            device_location = await self._config.get("device_location") or ""
            loc_line = f"Lokasyon: {device_location}\n" if device_location else ""
            sn_line = f"Seri No: {device_serial}\n" if device_serial else ""

            msg = EmailMessage()
            msg["Subject"] = f"[{device_name}] ALARM {level.value.upper()}: {dose_rate:.3f} µSv/h"
            msg["From"] = user
            msg["To"] = to_addr
            msg.set_content(
                f"Radyasyon alarmi tetiklendi.\n\n"
                f"Seviye: {level.value.upper()}\n"
                f"Doz Hizi: {dose_rate:.3f} µSv/h\n"
                f"Zaman: {_local_time()}\n"
                f"Cihaz: {device_name}\n"
                f"{sn_line}"
                f"{loc_line}"
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

            device_name = await self._config.get("device_name") or "GammaScout-01"
            device_location = await self._config.get("device_location") or ""
            device_serial = await self._config.get("device_serial") or ""

            from app import wifi
            status = await wifi.get_wifi_status()
            ip = status.get("ip", "")

            loc_line = f"Lokasyon: {device_location}\n" if device_location else ""
            sn_line = f"Seri No: {device_serial}\n" if device_serial else ""

            msg = EmailMessage()
            msg["Subject"] = f"[{device_name}] Test E-postası"
            msg["From"] = user
            msg["To"] = to_addr
            msg.set_content(
                f"Bu bir test e-postasıdır.\n\n"
                f"mssRadMon e-posta bildirimleri düzgün çalışıyor.\n\n"
                f"Cihaz: {device_name}\n"
                f"{loc_line}"
                f"{sn_line}"
                f"IP: {ip}\n"
                f"Zaman: {_local_time()}\n"
            )

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._smtp_send, host, port, user, password, msg)
            logger.info("Test e-postasi gonderildi: %s", to_addr)
            return {"ok": True, "message": f"Test e-postasi gonderildi: {to_addr}"}
        except Exception as e:
            logger.error("Test e-postasi hatasi: %s", e)
            return {"ok": False, "message": str(e)}

    async def _send_msgservice_mail(self, level: AlarmLevel, dose_rate: float):
        """msgService uzerinden alarm maili gonder."""
        if await self._config.get("msg_service_mail_enabled") != "true":
            return
        base_url = await self._config.get("msg_service_url") or ""
        api_key = await self._config.get("msg_service_api_key") or ""
        reply_to = await self._config.get("msg_service_reply_to") or ""
        to_raw = await self._config.get(f"msg_service_{level.value}_mail_to") or ""
        to_list = [e.strip() for e in to_raw.split(",") if e.strip()]
        if not to_list:
            return
        device_name = await self._config.get("device_name") or "GammaScout-01"
        device_location = await self._config.get("device_location") or ""
        device_serial = await self._config.get("device_serial") or ""
        label = level.value.upper().replace("_", "-")
        loop = asyncio.get_event_loop()
        msg_id = await loop.run_in_executor(
            None,
            lambda: msg_service.send_mail(
                base_url, api_key, to_list, reply_to,
                label, dose_rate, device_name, device_location, device_serial,
            ),
        )
        if msg_id:
            logger.info("msgService mail gonderildi: %s -> %s", level.value, msg_id)
        else:
            logger.warning("msgService mail gonderilemedi (level=%s)", level.value)

    async def _send_msgservice_wa(self, level: AlarmLevel, dose_rate: float):
        """msgService uzerinden alarm WA mesaji gonder."""
        if await self._config.get("msg_service_wa_enabled") != "true":
            return
        base_url = await self._config.get("msg_service_url") or ""
        api_key = await self._config.get("msg_service_api_key") or ""
        to_raw = await self._config.get(f"msg_service_{level.value}_wa_to") or ""
        phone_list = [p.strip() for p in to_raw.split(",") if p.strip()]
        if not phone_list:
            return
        device_name = await self._config.get("device_name") or "GammaScout-01"
        device_serial = await self._config.get("device_serial") or ""
        label = level.value.upper().replace("_", "-")
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None,
            lambda: msg_service.send_whatsapp(
                base_url, api_key, phone_list, label, dose_rate, device_name, device_serial,
            ),
        )
        sent = sum(1 for r in results if r["ok"])
        for r in results:
            if not r["ok"] and r["error"]:
                logger.warning("msgService WA basarisiz (%s): %s", r["phone"], r["error"])
        logger.info(
            "msgService WA gonderildi: %d/%d (level=%s)", sent, len(phone_list), level.value
        )

    def shutdown(self):
        """GPIO'lari kapat."""
        if self._buzzer_task:
            self._buzzer_task.cancel()
        for device in self._gpio_devices.values():
            device.off()
            device.close()
