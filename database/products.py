import asyncio

import aiosqlite

from .models import Product, ProductSize


class ProductRepository:
    def __init__(
        self, conn: aiosqlite.Connection, transaction_lock: asyncio.Lock
    ) -> None:
        self._conn = conn
        self._transaction_lock = transaction_lock

    async def add(
        self,
        name: str,
        description: str | None,
        price: float,
        photo_id: str | None,
        category: str,
        sizes: dict[str, int],
    ) -> int:
        async with self._transaction_lock:
            try:
                cursor = await self._conn.execute(
                    "INSERT INTO products (name, description, price, photo_id, category) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (name, description, price, photo_id, category),
                )
                product_id = cursor.lastrowid
                await self._conn.executemany(
                    "INSERT INTO product_sizes (product_id, size, quantity) VALUES (?, ?, ?)",
                    [
                        (product_id, size, quantity)
                        for size, quantity in sizes.items()
                    ],
                )
                await self._conn.commit()
            except BaseException:
                await self._conn.rollback()
                raise
        return product_id

    async def delete(self, product_id: int) -> None:
        async with self._transaction_lock:
            await self._conn.execute(
                "DELETE FROM product_sizes WHERE product_id = ?", (product_id,)
            )
            await self._conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
            await self._conn.commit()

    async def get_sizes(self, product_id: int) -> list[ProductSize]:
        async with self._conn.execute(
            """
            SELECT size, quantity FROM product_sizes
            WHERE product_id = ? ORDER BY size COLLATE NOCASE
            """,
            (product_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [ProductSize(size=row["size"], quantity=row["quantity"]) for row in rows]

    async def get_size(self, product_id: int, size: str) -> ProductSize | None:
        async with self._conn.execute(
            """
            SELECT size, quantity FROM product_sizes
            WHERE product_id = ? AND size = ?
            """,
            (product_id, size),
        ) as cursor:
            row = await cursor.fetchone()
        return ProductSize(size=row["size"], quantity=row["quantity"]) if row else None

    async def set_sizes(self, product_id: int, sizes: dict[str, int]) -> bool:
        async with self._transaction_lock:
            async with self._conn.execute(
                "SELECT 1 FROM products WHERE id = ?", (product_id,)
            ) as cursor:
                product_exists = await cursor.fetchone() is not None
            if not product_exists:
                return False

            try:
                await self._conn.execute(
                    "DELETE FROM product_sizes WHERE product_id = ?", (product_id,)
                )
                await self._conn.executemany(
                    "INSERT INTO product_sizes (product_id, size, quantity) VALUES (?, ?, ?)",
                    [(product_id, size, quantity) for size, quantity in sizes.items()],
                )
                await self._conn.commit()
                return True
            except BaseException:
                await self._conn.rollback()
                raise

    async def count(self, category: str | None = None) -> int:
        if category is None:
            query = "SELECT COUNT(*) FROM products"
            params: tuple[str, ...] = ()
        else:
            query = "SELECT COUNT(*) FROM products WHERE category = ?"
            params = (category,)
        async with self._conn.execute(query, params) as cursor:
            row = await cursor.fetchone()
        return row[0]

    async def get(self, product_id: int) -> Product | None:
        async with self._conn.execute(
            "SELECT * FROM products WHERE id = ?", (product_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return Product.from_row(row) if row else None

    async def get_at(self, offset: int, category: str | None = None) -> Product | None:
        if category is None:
            query = "SELECT * FROM products ORDER BY id LIMIT 1 OFFSET ?"
            params: tuple[int | str, ...] = (offset,)
        else:
            query = (
                "SELECT * FROM products WHERE category = ? "
                "ORDER BY id LIMIT 1 OFFSET ?"
            )
            params = (category, offset)
        async with self._conn.execute(query, params) as cursor:
            row = await cursor.fetchone()
        return Product.from_row(row) if row else None

    async def get_page(self, offset: int, limit: int) -> list[Product]:
        async with self._conn.execute(
            "SELECT * FROM products ORDER BY id LIMIT ? OFFSET ?", (limit, offset)
        ) as cursor:
            rows = await cursor.fetchall()
        return [Product.from_row(row) for row in rows]
