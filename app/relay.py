"""Waveshare RPi Relay Board (3 kanal) sürücüsü.

Donanım: 3 röle kartı, active-LOW (GPIO LOW = röle çeker, NO kapanır).
Boot anında pinler HIGH'a sürülür → röleler bırakır (initial_value=False
+ active_high=False bunu sağlar; gpiozero pin'i deaktif yani HIGH başlatır).

Her kanalın Relay_JMP jumper'ı kart üzerinde takılı olmalı.
"""
import logging

logger = logging.getLogger(__name__)

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


class RelayBoard:
    """İsimli kanallarla active-low röle kartı arayüzü."""

    def __init__(self, channels: dict[str, int]):
        self._devices: dict[str, OutputDevice] = {}
        for name, pin in channels.items():
            if pin is None:
                continue
            try:
                self._devices[name] = OutputDevice(
                    int(pin), active_high=False, initial_value=False
                )
                logger.info("Röle kanalı '%s' → BCM%s (active-low)", name, pin)
            except Exception as e:
                logger.warning("Röle '%s' (pin %s) başlatılamadı: %s", name, pin, e)
        if not _GPIO_AVAILABLE:
            logger.info("gpiozero bulunamadı — röleler mock modda")

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
