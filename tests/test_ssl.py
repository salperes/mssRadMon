"""SSL modülü testleri."""
import os
import tempfile
import pytest
import pytest_asyncio

from app.db import Database
from app.config import Config


@pytest_asyncio.fixture
async def ssl_deps(test_db_path):
    db = Database(test_db_path)
    await db.init()
    config = Config(db)
    await config.init()
    yield db, config
    await db.close()


@pytest.mark.asyncio
async def test_ssl_status_no_cert(ssl_deps):
    """Sertifika yokken durum doğru dönmeli."""
    from app.ssl import SslManager

    db, config = ssl_deps
    mgr = SslManager(config=config, ssl_dir="/tmp/nonexistent_ssl_dir_test")
    status = await mgr.get_status()
    assert status["has_cert"] is False
    assert status["ssl_enabled"] is False
    assert status["ca_trusted"] is False


@pytest.mark.asyncio
async def test_ssl_status_with_cert(ssl_deps):
    """Sertifika varken durum doğru dönmeli."""
    from app.ssl import SslManager

    db, config = ssl_deps
    with tempfile.TemporaryDirectory() as tmpdir:
        # Dummy sertifika ve key oluştur
        os.system(
            f'openssl req -x509 -newkey rsa:2048 -keyout {tmpdir}/server.key '
            f'-out {tmpdir}/server.crt -days 365 -nodes '
            f'-subj "/CN=test.mss.local" 2>/dev/null'
        )
        mgr = SslManager(config=config, ssl_dir=tmpdir)
        status = await mgr.get_status()
        assert status["has_cert"] is True
        assert status["subject"] is not None
        assert "test.mss.local" in status["subject"]
        assert status["expiry"] is not None
