import asyncio

import aiosqlite

from .models import Product


class OutOfStockError(Exception):
    """The selected product size is no longer available."""


class OrderRepository:
    def __init__(
        self, conn: aiosqlite.Connection, transaction_lock: asyncio.Lock
    ) -> None:
        self._conn = conn
        self._transaction_lock = transaction_lock

    async def create(
        self,
        product: Product,
        user_id: int,
        username: str | None,
        full_name: str,
        city: str,
        branch: str,
        phone: str,
        np_city_ref: str,
        np_warehouse_ref: str,
        size: str,
    ) -> int:
        async with self._transaction_lock:
            try:
                stock = await self._conn.execute(
                    """
                    UPDATE product_sizes SET quantity = quantity - 1
                    WHERE product_id = ? AND size = ? AND quantity > 0
                    """,
                    (product.id, size),
                )
                if stock.rowcount != 1:
                    raise OutOfStockError(size)

                cursor = await self._conn.execute(
                    """
                    INSERT INTO orders
                        (product_id, product_name, price, user_id, username,
                         full_name, city, branch, phone, np_city_ref, np_warehouse_ref, size)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        product.id, product.name, product.price, user_id, username,
                        full_name, city, branch, phone, np_city_ref, np_warehouse_ref,
                        size,
                    ),
                )
                await self._conn.commit()
            except BaseException:
                await self._conn.rollback()
                raise
        return cursor.lastrowid

    async def reserve_waybill(self, order_id: int) -> dict[str, object] | None:
        async with self._transaction_lock:
            cursor = await self._conn.execute(
                """
                UPDATE orders
                SET np_ttn_creating = 1
                WHERE id = ? AND np_ttn_number IS NULL AND np_ttn_creating = 0
                """,
                (order_id,),
            )
            reserved = cursor.rowcount == 1
            await self._conn.commit()

        async with self._conn.execute(
            "SELECT * FROM orders WHERE id = ?", (order_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        result = dict(row)
        result["np_ttn_reserved"] = reserved
        return result

    async def complete_waybill(
        self, order_id: int, document_ref: str, number: str
    ) -> None:
        async with self._transaction_lock:
            await self._conn.execute(
                """
                UPDATE orders
                SET np_document_ref = ?, np_ttn_number = ?, np_ttn_creating = 0
                WHERE id = ?
                """,
                (document_ref, number, order_id),
            )
            await self._conn.commit()

    async def release_waybill(self, order_id: int) -> None:
        async with self._transaction_lock:
            await self._conn.execute(
                "UPDATE orders SET np_ttn_creating = 0 WHERE id = ? AND np_ttn_number IS NULL",
                (order_id,),
            )
            await self._conn.commit()

    async def mark_waybill_unknown(self, order_id: int) -> None:
        async with self._transaction_lock:
            await self._conn.execute(
                """
                UPDATE orders SET np_ttn_creating = 2
                WHERE id = ? AND np_ttn_number IS NULL
                """,
                (order_id,),
            )
            await self._conn.commit()

    async def reset_unknown_waybill(self, order_id: int) -> bool:
        async with self._transaction_lock:
            cursor = await self._conn.execute(
                """
                UPDATE orders SET np_ttn_creating = 0
                WHERE id = ? AND np_ttn_number IS NULL AND np_ttn_creating = 2
                """,
                (order_id,),
            )
            await self._conn.commit()
        return cursor.rowcount == 1
