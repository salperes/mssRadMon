"""GammaScout Online serial okuyucu.

Cihaz protokolü: docs/gammascout-protocol.md
Bağlantı: 460800 baud, 7E1 (FW >= 6.90)
Mod: Dose rate online — 'R' komutu ile girilir, periyodik doz hızı çıktısı verir.
"""
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Awaitable

import serial

logger = logging.getLogger(__name__)

# Protokol sabitleri
DEFAULT_PORT = "/dev/ttyUSB0"
DEFAULT_BAUDRATE = 460800
BYTESIZE = serial.SEVENBITS
PARITY = serial.PARITY_EVEN
STOPBITS = serial.STOPBITS_ONE

# Komutlar (en az 550ms aralıkla gönderilmeli)
CMD_PC_MODE = b"P"
CMD_EXIT = b"X"
CMD_VERSION = b"v"
CMD_ONLINE_DOSE_RATE = b"R"
CMD_DELAY = 0.6  # 550ms + marj


@dataclass
class Reading:
    timestamp: str
    dose_rate: float  # µSv/h
    cumulative_dose: float  # µSv (kümülatif, cihaz version'dan okunur)


@dataclass
class DeviceInfo:
    firmware: str
    serial_number: str
    used_memory: str
    datetime_str: str


class GammaScoutReader:
    """GammaScout Online cihazından serial port üzerinden veri okur."""

    def __init__(
        self,
        port: str = DEFAULT_PORT,
        baudrate: int = DEFAULT_BAUDRATE,
    ):
        self.port = port
        self.baudrate = baudrate
        self._serial: serial.Serial | None = None
        self._running = False
        self._connected = False
        self._cumulative_dose = 0.0
        self._on_reading: Callable[[Reading], Awaitable[None]] | None = None

    @property
    def connected(self) -> bool:
        return self._connected

    def on_reading(self, callback: Callable[[Reading], Awaitable[None]]):
        """Yeni okuma geldiğinde çağrılacak async callback'i ata."""
        self._on_reading = callback

    def _send_command(self, cmd: bytes) -> bytes:
        """Komut gönder, yanıt oku. 550ms bekleme kuralına uyar."""
        if not self._serial or not self._serial.is_open:
            return b""
        self._serial.write(cmd)
        import time
        time.sleep(CMD_DELAY)
        data = self._serial.read(self._serial.in_waiting or 256)
        return data

    def connect(self) -> bool:
        """Serial porta bağlan."""
        try:
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=BYTESIZE,
                parity=PARITY,
                stopbits=STOPBITS,
                timeout=2,
            )
            self._connected = True
            logger.info("GammaScout bağlantısı kuruldu: %s @ %d", self.port, self.baudrate)
            return True
        except serial.SerialException as e:
            logger.error("Serial bağlantı hatası: %s", e)
            self._connected = False
            return False

    def enter_online_mode(self) -> bool:
        """Dose rate online moduna geç."""
        if not self._serial:
            return False
        try:
            resp = self._send_command(CMD_ONLINE_DOSE_RATE)
            logger.info("Online mode yanıtı: %s", resp)
            return True
        except serial.SerialException as e:
            logger.error("Online mod geçiş hatası: %s", e)
            return False

    def get_version(self) -> DeviceInfo | None:
        """PC moduna girip versiyon bilgisi al, sonra çık."""
        if not self._serial:
            return None
        try:
            self._send_command(CMD_PC_MODE)
            resp = self._send_command(CMD_VERSION)
            self._send_command(CMD_EXIT)
            return self._parse_version(resp)
        except serial.SerialException as e:
            logger.error("Versiyon sorgusu hatası: %s", e)
            return None

    def _parse_version(self, raw: bytes) -> DeviceInfo | None:
        """PC mode 'v' komut yanıtını parse et.

        Beklenen format (FW >= 6.90):
        Version FW_VER CPU_VER SN USED_MEM DATE TIME
        """
        if not raw:
            return None
        try:
            text = raw.decode("ascii", errors="ignore").strip()
            if not text:
                return None
            parts = text.split()
            # Minimum: version string ve serial
            return DeviceInfo(
                firmware=parts[0] if len(parts) > 0 else "unknown",
                serial_number=parts[2] if len(parts) > 2 else "unknown",
                used_memory=parts[3] if len(parts) > 3 else "unknown",
                datetime_str=" ".join(parts[4:6]) if len(parts) > 5 else "unknown",
            )
        except Exception as e:
            logger.warning("Version parse hatası: %s (raw: %s)", e, raw)
            return None

    def parse_online_data(self, raw: bytes) -> float | None:
        """Online mod çıktısını parse edip dose rate (µSv/h) döndür.

        GammaScout dose rate online modu CPS (counts per second) veya
        doğrudan µSv/h değeri verir. Gerçek format cihaz testinde doğrulanır.
        Beklenen: satır bazlı ASCII sayısal değer.
        """
        if not raw:
            return None
        try:
            text = raw.decode("ascii", errors="ignore").strip()
            if not text:
                return None
            # Birden fazla satır gelebilir, son geçerli değeri al
            for line in reversed(text.splitlines()):
                line = line.strip()
                if not line:
                    continue
                try:
                    return float(line)
                except ValueError:
                    # "Online x" gibi mod bildirimi olabilir
                    continue
            return None
        except Exception as e:
            logger.warning("Online data parse hatası: %s", e)
            return None

    def read_once(self) -> float | None:
        """Serial porttan mevcut veriyi oku ve dose rate döndür."""
        if not self._serial or not self._serial.is_open:
            return None
        try:
            waiting = self._serial.in_waiting
            if waiting == 0:
                # Kısa süre bekle
                import time
                time.sleep(0.1)
                waiting = self._serial.in_waiting
            if waiting == 0:
                return None
            raw = self._serial.read(waiting)
            return self.parse_online_data(raw)
        except serial.SerialException as e:
            logger.error("Okuma hatası: %s", e)
            self._connected = False
            return None

    def disconnect(self):
        """Online moddan çık ve bağlantıyı kapat."""
        if self._serial and self._serial.is_open:
            try:
                self._serial.write(CMD_EXIT)
                import time
                time.sleep(CMD_DELAY)
                self._serial.close()
            except serial.SerialException:
                pass
        self._connected = False
        logger.info("GammaScout bağlantısı kapatıldı")

    async def run(self, interval: int = 10):
        """Ana okuma döngüsü.

        1. Bağlan
        2. Online moda geç
        3. interval saniyede bir veri oku
        4. Callback ile bildir
        """
        self._running = True
        while self._running:
            if not self._connected:
                logger.info("GammaScout'a bağlanılıyor...")
                if not self.connect():
                    await asyncio.sleep(5)
                    continue
                if not self.enter_online_mode():
                    self.disconnect()
                    await asyncio.sleep(5)
                    continue

            loop = asyncio.get_event_loop()
            dose_rate = await loop.run_in_executor(None, self.read_once)

            if dose_rate is not None:
                self._cumulative_dose += dose_rate * (interval / 3600)
                reading = Reading(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    dose_rate=dose_rate,
                    cumulative_dose=round(self._cumulative_dose, 4),
                )
                if self._on_reading:
                    try:
                        await self._on_reading(reading)
                    except Exception as e:
                        logger.error("Reading callback hatası: %s", e)
            elif not self._connected:
                self.disconnect()
                await asyncio.sleep(5)
                continue

            await asyncio.sleep(interval)

    def stop(self):
        """Okuma döngüsünü durdur."""
        self._running = False
        self.disconnect()
