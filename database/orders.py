import asyncio
from typing import Literal

import aiosqlite

from .models import Product


class OutOfStockError(Exception):
    """The selected product size is no longer available."""


OrderCancellationResult = Literal["cancelled", "not_found", "not_cancellable"]
OrderStatusUpdateResult = Literal["updated", "not_found", "invalid"]
ORDER_STATUS_LABELS = {
    "new": "Новый",
    "confirmed": "Подтверждён",
    "preparing": "Собирается",
    "shipped": "Отправлен",
    "cancelled": "Отменён",
}
ORDER_STATUS_NEXT = {
    "new": "confirmed",
    "confirmed": "preparing",
    "preparing": "shipped",
}


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

    async def count_for_user(self, user_id: int) -> int:
        async with self._conn.execute(
            "SELECT COUNT(*) FROM orders WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return int(row[0])

    async def get_page_for_user(
        self, user_id: int, offset: int, limit: int
    ) -> list[dict[str, object]]:
        async with self._conn.execute(
            """
            SELECT id, product_id, product_name, price, size, status,
                   np_ttn_number, np_ttn_creating
            FROM orders
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (user_id, limit, offset),
        ) as cursor:
            rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_for_user(
        self, order_id: int, user_id: int
    ) -> dict[str, object] | None:
        async with self._conn.execute(
            """
            SELECT id, product_id, product_name, price, size, status,
                   np_ttn_number, np_ttn_creating
            FROM orders
            WHERE id = ? AND user_id = ?
            """,
            (order_id, user_id),
        ) as cursor:
            row = await cursor.fetchone()
        return dict(row) if row else None

    async def get_for_admin(self, order_id: int) -> dict[str, object] | None:
        async with self._conn.execute(
            """
            SELECT id, user_id, product_name, price, size, status,
                   np_ttn_number, np_ttn_creating
            FROM orders
            WHERE id = ?
            """,
            (order_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return dict(row) if row else None

    async def cancel_for_user(
        self, order_id: int, user_id: int
    ) -> OrderCancellationResult:
        async with self._transaction_lock:
            try:
                async with self._conn.execute(
                    """
                    SELECT orders.product_id, orders.size
                    FROM orders
                    JOIN products ON products.id = orders.product_id
                    WHERE orders.id = ? AND orders.user_id = ?
                      AND orders.status IN ('new', 'confirmed', 'preparing')
                      AND orders.size IS NOT NULL
                      AND orders.np_ttn_number IS NULL
                      AND orders.np_ttn_creating = 0
                    """,
                    (order_id, user_id),
                ) as cursor:
                    order = await cursor.fetchone()
                if order is None:
                    async with self._conn.execute(
                        "SELECT 1 FROM orders WHERE id = ? AND user_id = ?",
                        (order_id, user_id),
                    ) as cursor:
                        exists = await cursor.fetchone() is not None
                    await self._conn.rollback()
                    return "not_cancellable" if exists else "not_found"

                cursor = await self._conn.execute(
                    """
                    UPDATE orders SET status = 'cancelled'
                    WHERE id = ? AND user_id = ?
                      AND status IN ('new', 'confirmed', 'preparing')
                      AND product_id IS NOT NULL AND size IS NOT NULL
                      AND np_ttn_number IS NULL AND np_ttn_creating = 0
                    """,
                    (order_id, user_id),
                )
                if cursor.rowcount != 1:
                    await self._conn.rollback()
                    return "not_cancellable"

                product_id = order["product_id"]
                size = order["size"]
                if product_id is not None and size:
                    async with self._conn.execute(
                        "SELECT 1 FROM products WHERE id = ?", (product_id,)
                    ) as cursor:
                        product_exists = await cursor.fetchone() is not None
                    if product_exists:
                        await self._conn.execute(
                            """
                            INSERT INTO product_sizes (product_id, size, quantity)
                            VALUES (?, ?, 1)
                            ON CONFLICT(product_id, size)
                            DO UPDATE SET quantity = quantity + 1
                            """,
                            (product_id, size),
                        )
                await self._conn.commit()
                return "cancelled"
            except BaseException:
                await self._conn.rollback()
                raise

    async def advance_status(
        self, order_id: int, target_status: str
    ) -> tuple[OrderStatusUpdateResult, int | None]:
        async with self._transaction_lock:
            try:
                async with self._conn.execute(
                    """
                    SELECT user_id, status, np_ttn_number
                    FROM orders WHERE id = ?
                    """,
                    (order_id,),
                ) as cursor:
                    order = await cursor.fetchone()
                if order is None:
                    await self._conn.rollback()
                    return "not_found", None

                current_status = str(order["status"])
                if ORDER_STATUS_NEXT.get(current_status) != target_status:
                    await self._conn.rollback()
                    return "invalid", None
                if target_status == "shipped" and not order["np_ttn_number"]:
                    await self._conn.rollback()
                    return "invalid", None

                await self._conn.execute(
                    "UPDATE orders SET status = ? WHERE id = ? AND status = ?",
                    (target_status, order_id, current_status),
                )
                await self._conn.commit()
                return "updated", int(order["user_id"])
            except BaseException:
                await self._conn.rollback()
                raise

    async def reserve_waybill(self, order_id: int) -> dict[str, object] | None:
        async with self._transaction_lock:
            cursor = await self._conn.execute(
                """
                UPDATE orders
                SET np_ttn_creating = 1
                WHERE id = ? AND status IN ('new', 'confirmed', 'preparing')
                  AND np_ttn_number IS NULL AND np_ttn_creating = 0
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
