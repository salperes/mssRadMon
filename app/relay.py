"""Waveshare RPi Relay Board (3 kanal) sürücüsü.

Donanım: 3 röle kartı, active-LOW (GPIO LOW = röle çeker, NO kapanır).
Boot anında pinler HIGH'a sürülür → röleler bırakır (initial_value=False
+ active_high=False bunu sağlar; gpiozero pin'i deaktif yani HIGH başlatır).

Her kanalın Relay_JMP jumper'ı kart üzerinde takılı olmalı.
"""
import logging

logger = logging.getLogger(__name__)

# Kart üzerindeki kanal → BCM pin eşlemesi (CH1/CH2/CH3)
DEFAULT_PINS: dict[str, int] = {"buzzer": 26, "light": 20, "emergency": 21}

# Kanal → settings tablosundaki ayar anahtarı
GPIO_PIN_KEYS: dict[str, str] = {
    "buzzer": "gpio_buzzer_pin",
    "light": "gpio_light_pin",
    "emergency": "gpio_emergency_pin",
}

try:
    from gpiozero import OutputDevice
    _GPIO_AVAILABLE = True
except ImportError:
    _GPIO_AVAILABLE = False

    class OutputDevice:  # type: ignore[no-redef]
        def __init__(self, pin, **kwargs):
            self.pin = pin
            self._value = False
        def on(self): self._value = True
        def off(self): self._value = False
        @property
        def value(self): return 1 if self._value else 0
        def close(self): pass


async def resolve_channels(config) -> dict[str, int]:
    """Kanal → pin eşlemesini ayarlardan çöz; geçersiz/boş değerde varsayılana düş."""
    channels: dict[str, int] = {}
    for name, key in GPIO_PIN_KEYS.items():
        raw = await config.get(key)
        try:
            channels[name] = DEFAULT_PINS[name] if raw in (None, "") else int(raw)
        except (TypeError, ValueError):
            logger.warning(
                "Geçersiz %s değeri (%r) — varsayılan BCM%s kullanılıyor",
                key, raw, DEFAULT_PINS[name],
            )
            channels[name] = DEFAULT_PINS[name]
    return channels


class RelayBoard:
    """İsimli kanallarla active-low röle kartı arayüzü."""

    def __init__(self, channels: dict[str, int]):
        self._devices: dict[str, OutputDevice] = {}
        self._pins: dict[str, int] = {}
        self._open(channels)
        if not _GPIO_AVAILABLE:
            logger.info("gpiozero bulunamadı — röleler mock modda")

    def _open(self, channels: dict[str, int]) -> None:
        for name, pin in channels.items():
            if pin is None:
                continue
            try:
                self._devices[name] = OutputDevice(
                    int(pin), active_high=False, initial_value=False
                )
                self._pins[name] = int(pin)
                logger.info("Röle kanalı '%s' → BCM%s (active-low)", name, pin)
            except Exception as e:
                logger.warning("Röle '%s' (pin %s) başlatılamadı: %s", name, pin, e)

    def pins(self) -> dict[str, int]:
        """Süreç şu anda hangi pinleri sürüyor — DB'deki ayar değil, canlı durum."""
        return dict(self._pins)

    def reconfigure(self, channels: dict[str, int]) -> bool:
        """Pinleri yeniden kur (ayar değişiminde). Değişiklik yoksa dokunmaz.

        Çekili kanallar yeni pinler üzerinde geri çekilir; böylece aktif alarm
        sırasında pin değişse bile çıkışlar düşmez. Değişiklik yapıldıysa True.
        """
        desired = {n: int(p) for n, p in channels.items() if p is not None}
        if desired == self._pins:
            return False
        active = [name for name in self._devices if self.is_on(name)]
        self.close()
        self._open(channels)
        for name in active:
            self.set(name, True)
        logger.info("Röle pinleri yeniden yapılandırıldı: %s", self._pins)
        return True

    def has(self, name: str) -> bool:
        return name in self._devices

    def set(self, name: str, on: bool) -> None:
        dev = self._devices.get(name)
        if dev is None:
            return
        if on:
            dev.on()
        else:
            dev.off()

    def is_on(self, name: str) -> bool:
        dev = self._devices.get(name)
        return bool(dev and dev.value)

    def all_off(self) -> None:
        for dev in self._devices.values():
            dev.off()

    def close(self) -> None:
        for dev in self._devices.values():
            try:
                dev.off()
                dev.close()
            except Exception:
                pass
        self._devices.clear()
        self._pins.clear()
