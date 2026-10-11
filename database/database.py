import asyncio

import aiosqlite

from .orders import OrderRepository
from .np_settings import NPSettingsRepository
from .products import ProductRepository

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    description TEXT,
    price       REAL NOT NULL,
    photo_id    TEXT,
    category    TEXT NOT NULL DEFAULT 'uncategorized',
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS product_sizes (
    product_id INTEGER NOT NULL,
    size       TEXT NOT NULL,
    quantity   INTEGER NOT NULL CHECK (quantity >= 0),
    PRIMARY KEY (product_id, size)
);

CREATE TABLE IF NOT EXISTS orders (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id   INTEGER,
    product_name TEXT NOT NULL,
    price        REAL NOT NULL,
    user_id      INTEGER NOT NULL,
    username     TEXT,
    full_name    TEXT NOT NULL,
    city         TEXT NOT NULL,
    branch       TEXT NOT NULL,
    phone        TEXT NOT NULL,
    np_city_ref      TEXT,
    np_warehouse_ref TEXT,
    np_ttn_number    TEXT,
    np_document_ref  TEXT,
    np_ttn_creating  INTEGER NOT NULL DEFAULT 0,
    size         TEXT,
    status       TEXT DEFAULT 'new',
    created_at   TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS np_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class Database:

    products: ProductRepository
    orders: OrderRepository
    np_settings: NPSettingsRepository

    def __init__(self, path: str) -> None:
        self._path = path
        self._conn: aiosqlite.Connection | None = None
        self._transaction_lock = asyncio.Lock()

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA)
        await self._migrate()
        await self._conn.commit()

        self.products = ProductRepository(self._conn, self._transaction_lock)
        self.orders = OrderRepository(self._conn, self._transaction_lock)
        self.np_settings = NPSettingsRepository(self._conn, self._transaction_lock)

    async def _migrate(self) -> None:
        async with self._conn.execute("PRAGMA table_info(products)") as cursor:
            product_columns = {row["name"] for row in await cursor.fetchall()}
        if "category" not in product_columns:
            await self._conn.execute(
                "ALTER TABLE products ADD COLUMN category TEXT NOT NULL "
                "DEFAULT 'uncategorized'"
            )

        async with self._conn.execute("PRAGMA table_info(orders)") as cursor:
            existing = {row["name"] for row in await cursor.fetchall()}

        for column in ("np_city_ref", "np_warehouse_ref"):
            if column not in existing:
                await self._conn.execute(f"ALTER TABLE orders ADD COLUMN {column} TEXT")
        for column, declaration in (
            ("np_ttn_number", "TEXT"),
            ("np_document_ref", "TEXT"),
            ("np_ttn_creating", "INTEGER NOT NULL DEFAULT 0"),
            ("size", "TEXT"),
        ):
            if column not in existing:
                await self._conn.execute(
                    f"ALTER TABLE orders ADD COLUMN {column} {declaration}"
                )

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
