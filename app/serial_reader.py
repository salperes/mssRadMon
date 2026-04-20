"""GammaScout Online serial okuyucu.

Cihaz protokolü: docs/gammascout-protocol.md
Bağlantı: 460800 baud, 7E1 (FW >= 6.90)
Mod: Dose rate online — 'R' komutu ile girilir, periyodik doz hızı çıktısı verir.
"""
import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Awaitable

import serial
from serial.tools import list_ports

logger = logging.getLogger(__name__)

# Protokol sabitleri
DEFAULT_PORT = "/dev/ttyGammaScout"
DEFAULT_BAUDRATE = 460800
BYTESIZE = serial.SEVENBITS
PARITY = serial.PARITY_EVEN
STOPBITS = serial.STOPBITS_ONE

# GammaScout USB kimliği (FTDI)
GAMMASCOUT_VID = 0x0403
GAMMASCOUT_PID = 0xD678

# Komutlar (en az 550ms aralıkla gönderilmeli)
CMD_PC_MODE = b"P"
CMD_EXIT = b"X"
CMD_VERSION = b"v"
CMD_ONLINE_DOSE_RATE = b"R"
CMD_SET_TIME = b"t"
CMD_DELAY = 0.6  # 550ms + marj
CMD_CHAR_DELAY = 0.002  # parametre karakterleri arası 1-2ms


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
        self._device_info: DeviceInfo | None = None
        self._on_reading: Callable[[Reading], Awaitable[None]] | None = None
        self.calibration_factor: float = 1.0

    @property
    def serial_number(self) -> str:
        return self._device_info.serial_number if self._device_info else ""

    @property
    def firmware(self) -> str:
        return self._device_info.firmware if self._device_info else ""

    @property
    def connected(self) -> bool:
        return self._connected

    def on_reading(self, callback: Callable[[Reading], Awaitable[None]]):
        """Yeni okuma geldiğinde çağrılacak async callback'i ata."""
        self._on_reading = callback

    def _flush_input(self):
        """Serial giriş buffer'ını temizle."""
        if self._serial and self._serial.is_open and self._serial.in_waiting:
            discarded = self._serial.read(self._serial.in_waiting)
            if discarded:
                logger.debug("Serial buffer temizlendi: %d byte", len(discarded))

    def _send_command(self, cmd: bytes) -> bytes:
        """Komut gönder, yanıt oku. 550ms bekleme kuralına uyar."""
        if not self._serial or not self._serial.is_open:
            return b""
        self._serial.write(cmd)
        import time
        time.sleep(CMD_DELAY)
        data = self._serial.read(self._serial.in_waiting or 256)
        return data

    @staticmethod
    def _find_port_by_vid_pid() -> str | None:
        """VID:PID ile GammaScout portunu otomatik bul."""
        for port in list_ports.comports():
            if port.vid == GAMMASCOUT_VID and port.pid == GAMMASCOUT_PID:
                return port.device
        return None

    def connect(self) -> bool:
        """Serial porta bağlan. Port yoksa VID:PID ile otomatik algıla."""
        import os
        if not os.path.exists(self.port):
            detected = self._find_port_by_vid_pid()
            if detected:
                logger.info(
                    "Port '%s' bulunamadı, otomatik algılandı: %s "
                    "(udev rule için: SUBSYSTEM==\"tty\", ATTRS{idVendor}==\"0403\", "
                    "ATTRS{idProduct}==\"d678\", SYMLINK+=\"ttyGammaScout\")",
                    self.port, detected,
                )
                self.port = detected
            else:
                logger.error("GammaScout bulunamadı (port=%s, VID:PID=%04x:%04x)", self.port, GAMMASCOUT_VID, GAMMASCOUT_PID)
                self._connected = False
                return False
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

    def _sync_time(self):
        """Cihaz saatini sistem saatiyle senkronize et (PC modunda çağrılmalı).

        Format: DDMMYYhhmmss — parametre karakterleri 1-2ms aralıkla gönderilir.
        """
        if not self._serial or not self._serial.is_open:
            return
        import time
        now = datetime.now()
        time_str = now.strftime("%d%m%y%H%M%S")
        self._send_command(CMD_SET_TIME)
        for ch in time_str.encode("ascii"):
            self._serial.write(bytes([ch]))
            time.sleep(CMD_CHAR_DELAY)
        time.sleep(CMD_DELAY)
        # Cihaz yanıtını oku — buffer'da kalıp sonraki komutları bozmasın
        if self._serial.in_waiting:
            self._serial.read(self._serial.in_waiting)
        logger.info("GammaScout saati senkronize edildi: %s", time_str)

    def _query_version(self) -> DeviceInfo | None:
        """PC moduna girip versiyon/seri no alıp, saati senkronize edip çık."""
        if not self._serial:
            return None
        try:
            self._flush_input()
            self._send_command(CMD_PC_MODE)
            # P yanıtı geç gelebilir, ekstra bekle ve buffer'ı temizle
            import time
            time.sleep(CMD_DELAY)
            self._flush_input()
            resp = self._send_command(CMD_VERSION)
            info = self._parse_version(resp)
            if not info:
                # Version yanıtı geç geldiyse tekrar oku
                time.sleep(CMD_DELAY)
                extra = self._serial.read(self._serial.in_waiting or 256) if self._serial.in_waiting else b""
                if extra:
                    info = self._parse_version(resp + extra)
            self._sync_time()
            self._send_command(CMD_EXIT)
            # Exit sonrası buffer'ı temizle
            time.sleep(CMD_DELAY)
            self._flush_input()
            return info
        except serial.SerialException as e:
            logger.warning("Version sorgusu hatası: %s", e)
            return None

    def enter_online_mode(self) -> bool:
        """Dose rate online moduna geç."""
        if not self._serial:
            return False
        try:
            self._flush_input()
            resp = self._send_command(CMD_ONLINE_DOSE_RATE)
            logger.info("Online mode yanıtı: %s", resp)
            # İlk okumayı doğrula — cihaz gerçekten online modda mı?
            if resp and b"uSv/h" in resp:
                return True
            # Yanıt boş veya beklenmedikse kısa bekle ve tekrar kontrol et
            import time
            time.sleep(2)
            check = self._serial.read(self._serial.in_waiting or 256) if self._serial.in_waiting else b""
            if check and b"uSv/h" in check:
                logger.info("Online mode doğrulandı (gecikmeli): %s", check)
                return True
            logger.warning("Online mode yanıtında doz verisi bulunamadı: resp=%s check=%s", resp, check)
            return True  # yine de dene, belki sonraki okumada gelir
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

        Gerçek format (FW >= 6.90):
        Version FW_VER SN USED_MEM DATE TIME
        Örnek: Version 7.14Lb07 085875 0030 d2.fc.cf 16:28:12
        """
        if not raw:
            return None
        try:
            text = raw.decode("ascii", errors="ignore")
            # Buffer'da kalan P yanıtı ile karışabilir; "Version" ile başlayan satırı bul
            version_line = None
            for line in text.splitlines():
                if line.strip().startswith("Version"):
                    version_line = line.strip()
                    break
            if not version_line:
                logger.warning("Version satırı bulunamadı (raw: %s)", raw)
                return None
            parts = version_line.split()
            # parts[0]="Version" parts[1]=FW parts[2]=SN parts[3]=USED_MEM parts[4]=DATE parts[5]=TIME
            return DeviceInfo(
                firmware=parts[1] if len(parts) > 1 else "unknown",
                serial_number=parts[2] if len(parts) > 2 else "unknown",
                used_memory=parts[3] if len(parts) > 3 else "unknown",
                datetime_str=" ".join(parts[4:6]) if len(parts) > 5 else "unknown",
            )
        except Exception as e:
            logger.warning("Version parse hatası: %s (raw: %s)", e, raw)
            return None

    # Tam GammaScout online format: "0,166 uSv/h" — virgüllü ondalık, en az 1 basamak
    _DOSE_RE = re.compile(r"^(\d+,\d+)\s+uSv/h\s*$")

    def parse_online_data(self, raw: bytes) -> float | None:
        """Online mod çıktısını parse edip dose rate (µSv/h) döndür.

        Gerçek cihaz formatı: "0,166 uSv/h\r\n"
        Regex ile tam format doğrulama yapılır — parçalı/bozuk satırlar reddedilir.
        """
        if not raw:
            return None
        try:
            text = raw.decode("ascii", errors="ignore").strip()
            if not text:
                return None
            for line in reversed(text.splitlines()):
                line = line.strip()
                m = self._DOSE_RE.match(line)
                if not m:
                    continue
                value = float(m.group(1).replace(",", "."))
                if 0 <= value <= 1000:
                    return value
                logger.warning("Aralık dışı değer: %.3f", value)
            return None
        except Exception as e:
            logger.warning("Online data parse hatası: %s", e)
            return None

    def read_once(self) -> float | None:
        """Serial porttan en güncel doz hızını oku.

        Cihaz ~1s aralıkla veri gönderir, biz 10-15s aralıkla okuruz.
        Buffer'daki eski satırları atıp en son satırı alır.
        """
        if not self._serial or not self._serial.is_open:
            return None
        try:
            # Buffer'daki birikmiş eski verileri at, sadece en güncelini al
            last_raw = None
            # Önce buffer'daki tüm hazır satırları oku
            while self._serial.in_waiting:
                line = self._serial.readline()
                if line:
                    last_raw = line
            # Eğer buffer boşsa, bir sonraki satırı bekle (timeout=2s)
            if last_raw is None:
                last_raw = self._serial.readline()
            if not last_raw:
                logger.debug("readline boş döndü (timeout)")
                return None
            value = self.parse_online_data(last_raw)
            if value is None:
                logger.warning("Parse edilemeyen serial veri: %s", last_raw)
            return value
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
        self._device_info = None  # yeniden bağlanınca tam init yapılsın
        logger.info("GammaScout bağlantısı kapatıldı")

    async def run(self, interval: int = 10):
        """Ana okuma döngüsü.

        1. Bağlan
        2. Online moda geç
        3. interval saniyede bir veri oku
        4. Callback ile bildir
        """
        self._running = True
        _consecutive_failures = 0
        while self._running:
            if not self._connected:
                logger.info("GammaScout'a bağlanılıyor...")
                if not self.connect():
                    await asyncio.sleep(5)
                    continue
                # Her bağlantıda cihazı tam init et (seri no + PC mode)
                loop = asyncio.get_event_loop()
                self._device_info = await loop.run_in_executor(None, self._query_version)
                if self._device_info:
                    logger.info("GammaScout FW:%s SN:%s", self._device_info.firmware, self._device_info.serial_number)
                if not self.enter_online_mode():
                    self.disconnect()
                    await asyncio.sleep(5)
                    continue
                _consecutive_failures = 0

            loop = asyncio.get_event_loop()
            dose_rate = await loop.run_in_executor(None, self.read_once)

            if dose_rate is not None:
                _consecutive_failures = 0
                dose_rate *= self.calibration_factor
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
            else:
                _consecutive_failures += 1
                logger.debug("Okuma boş döndü (ardışık: %d/3)", _consecutive_failures)
                if not self._connected or _consecutive_failures >= 3:
                    logger.warning("Okuma başarısız (%d), yeniden bağlanılıyor...", _consecutive_failures)
                    self.disconnect()
                    await asyncio.sleep(5)
                    continue

            await asyncio.sleep(interval)

    def stop(self):
        """Okuma döngüsünü durdur."""
        self._running = False
        self.disconnect()
