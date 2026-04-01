from __future__ import annotations

from datetime import datetime, timezone

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS price_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    coin_id TEXT NOT NULL,
    price REAL NOT NULL
);
"""


async def init_db(db_path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(SCHEMA)
        await db.commit()


async def fetch_last_price(db_path, coin_id: str) -> float | None:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT price FROM price_snapshots
            WHERE coin_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (coin_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            return float(row["price"])


async def insert_snapshot(db_path, coin_id: str, price: float) -> None:
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO price_snapshots (created_at, coin_id, price)
            VALUES (?, ?, ?)
            """,
            (now, coin_id, price),
        )
        await db.commit()
