"""SSL yönetimi — CA trust, sertifika talep, durum kontrolü."""
import logging
import os
import subprocess

import httpx

from app.config import Config

logger = logging.getLogger(__name__)

CA_TRUST_PATH = "/usr/local/share/ca-certificates/mss-ca.crt"


class SslManager:
    def __init__(self, config: Config, ssl_dir: str = "data/ssl"):
        self._config = config
        self._ssl_dir = ssl_dir

    @property
    def cert_path(self) -> str:
        return os.path.join(self._ssl_dir, "server.crt")

    @property
    def key_path(self) -> str:
        return os.path.join(self._ssl_dir, "server.key")

    @property
    def ca_path(self) -> str:
        return os.path.join(self._ssl_dir, "ca.crt")

    async def get_status(self) -> dict:
        """Mevcut SSL durumunu döndür."""
        ssl_enabled = (await self._config.get("ssl_enabled")) == "true"
        ca_trusted = os.path.isfile(CA_TRUST_PATH)
        has_cert = os.path.isfile(self.cert_path) and os.path.isfile(self.key_path)

        expiry = None
        subject = None
        if has_cert:
            expiry, subject = self._parse_cert_info()

        ca_server = await self._check_ca_server()

        return {
            "ca_trusted": ca_trusted,
            "has_cert": has_cert,
            "ssl_enabled": ssl_enabled,
            "expiry": expiry,
            "subject": subject,
            "ca_server": ca_server,
        }

    def _parse_cert_info(self) -> tuple[str | None, str | None]:
        """openssl ile sertifika bilgilerini parse et."""
        try:
            info = subprocess.check_output(
                ["openssl", "x509", "-in", self.cert_path, "-noout", "-enddate", "-subject"],
                text=True,
            )
            expiry = None
            subject = None
            for line in info.strip().splitlines():
                if line.startswith("notAfter="):
                    expiry = line.split("=", 1)[1].strip()
                if line.startswith("subject="):
                    subject = line.split("=", 1)[1].strip()
            return expiry, subject
        except Exception as e:
            logger.warning("Sertifika bilgisi okunamadı: %s", e)
            return None, None

    async def _check_ca_server(self) -> dict:
        """CA sunucu erişilebilirliğini kontrol et."""
        ca_url = await self._config.get("ca_server_url")
        if not ca_url:
            return {"reachable": False, "initialized": False}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(f"{ca_url}/api/ca/status")
                data = res.json()
                return {"reachable": True, "initialized": data.get("initialized", False)}
        except Exception:
            return {"reachable": False, "initialized": False}
