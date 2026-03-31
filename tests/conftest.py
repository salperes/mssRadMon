import asyncio
import os
import tempfile
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def test_db_path():
    """Her test için geçici SQLite DB dosyası."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    os.unlink(path)


@pytest_asyncio.fixture
async def test_client(test_db_path):
    """FastAPI test client. DB path'i override eder."""
    os.environ["MSSRADMON_DB_PATH"] = test_db_path
    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    os.environ.pop("MSSRADMON_DB_PATH", None)
