"""users tablosu şema testi."""
import pytest
import pytest_asyncio

from app.db import Database


@pytest_asyncio.fixture
async def db(test_db_path):
    database = Database(test_db_path)
    await database.init()
    yield database
    await database.close()


@pytest.mark.asyncio
async def test_users_table_exists(db):
    """users tablosuna insert yapabilmeli."""
    await db.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
        ("testuser", "hash123", "admin"),
    )
    row = await db.fetch_one("SELECT username, role FROM users WHERE username = ?", ("testuser",))
    assert row["username"] == "testuser"
    assert row["role"] == "admin"


@pytest.mark.asyncio
async def test_users_role_constraint(db):
    """Geçersiz rol reddedilmeli."""
    with pytest.raises(Exception):
        await db.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("testuser", "hash123", "superuser"),
        )
