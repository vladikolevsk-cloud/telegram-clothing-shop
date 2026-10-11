import asyncio

import aiosqlite


class NPSettingsRepository:
    def __init__(
        self, conn: aiosqlite.Connection, transaction_lock: asyncio.Lock
    ) -> None:
        self._conn = conn
        self._transaction_lock = transaction_lock

    async def get_all(self) -> dict[str, str]:
        async with self._conn.execute("SELECT key, value FROM np_settings") as cursor:
            return {row["key"]: row["value"] for row in await cursor.fetchall()}

    async def set_many(self, settings: dict[str, str]) -> None:
        async with self._transaction_lock:
            await self._conn.executemany(
                "INSERT OR REPLACE INTO np_settings (key, value) VALUES (?, ?)",
                settings.items(),
            )
            await self._conn.commit()
