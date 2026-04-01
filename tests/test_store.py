from __future__ import annotations

import pytest

from app.database.store import fetch_last_price, init_db, insert_snapshot


@pytest.mark.asyncio
async def test_init_insert_fetch_roundtrip(settings) -> None:
    db_path = settings.database_path
    await init_db(db_path)
    assert await fetch_last_price(db_path, "bitcoin") is None

    await insert_snapshot(db_path, "bitcoin", 100.0)
    assert await fetch_last_price(db_path, "bitcoin") == 100.0

    await insert_snapshot(db_path, "bitcoin", 101.5)
    assert await fetch_last_price(db_path, "bitcoin") == 101.5
