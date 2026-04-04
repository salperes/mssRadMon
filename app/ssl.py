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

    async def trust_ca(self) -> dict:
        """CA sertifikasını indir ve sisteme güvenilir olarak ekle."""
        ca_url = await self._config.get("ca_server_url")
        if not ca_url:
            return {"ok": False, "message": "CA sunucu URL ayarlanmamış"}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(f"{ca_url}/api/ca/certificate")
                res.raise_for_status()
                pem_data = res.text
        except Exception as e:
            return {"ok": False, "message": f"CA sertifikası indirilemedi: {e}"}

        os.makedirs(self._ssl_dir, exist_ok=True)
        with open(self.ca_path, "w") as f:
            f.write(pem_data)

        try:
            subprocess.run(
                ["sudo", "cp", self.ca_path, CA_TRUST_PATH],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["sudo", "update-ca-certificates"],
                check=True, capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            return {"ok": False, "message": f"Sistem trust hatası: {e.stderr.decode().strip()}"}

        logger.info("CA sertifikası sisteme güvenilir olarak eklendi")
        return {"ok": True, "message": "CA sertifikası güvenilir olarak eklendi"}

    async def request_cert(self, hostname: str) -> dict:
        """CA sunucudan sertifika talep et, kaydet, servisi SSL ile restart et."""
        ca_url = await self._config.get("ca_server_url")
        if not ca_url:
            return {"ok": False, "message": "CA sunucu URL ayarlanmamış"}

        ca_api_key = await self._config.get("ca_api_key")
        if not ca_api_key:
            return {"ok": False, "message": "CA API key ayarlanmamış"}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.post(
                    f"{ca_url}/api/certificates/request",
                    json={
                        "hostname": hostname,
                        "ipAddress": "",
                        "appName": "mssradmon",
                    },
                    headers={"X-API-Key": ca_api_key},
                )
                res.raise_for_status()
                data = res.json()
        except Exception as e:
            return {"ok": False, "message": f"Sertifika talebi başarısız: {e}"}

        os.makedirs(self._ssl_dir, exist_ok=True)

        key_path = self.key_path
        with open(key_path, "w") as f:
            f.write(data["key"])
        os.chmod(key_path, 0o600)

        with open(self.cert_path, "w") as f:
            f.write(data["cert"])

        with open(self.ca_path, "w") as f:
            f.write(data["caCert"])

        await self._config.set("ssl_enabled", "true")

        restart_ok = self._restart_service()

        expiry = data.get("expiresAt", "")
        logger.info("SSL sertifikası yüklendi: %s (expiry: %s)", hostname, expiry)

        if not restart_ok:
            return {
                "ok": True,
                "message": "Sertifika kaydedildi ancak servis yeniden başlatılamadı — manuel restart gerekli",
                "expiry": expiry,
            }

        return {
            "ok": True,
            "message": "Sertifika yüklendi, HTTPS aktif — sayfa birkaç saniye içinde yeniden yüklenecek",
            "expiry": expiry,
        }

    def _restart_service(self) -> bool:
        """Systemd servisini SSL parametreleriyle restart et."""
        service_src = os.path.join(os.path.dirname(__file__), "..", "systemd", "mssradmon-ssl.service")
        service_src = os.path.abspath(service_src)
        try:
            subprocess.run(
                ["sudo", "cp", service_src, "/etc/systemd/system/mssradmon.service"],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["sudo", "systemctl", "daemon-reload"],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["sudo", "systemctl", "restart", "mssradmon"],
                check=True, capture_output=True,
            )
            return True
        except subprocess.CalledProcessError as e:
            logger.error("Servis restart hatası: %s", e.stderr.decode().strip())
            return False

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
