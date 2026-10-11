from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from categories import LEGACY_CATEGORY, PRODUCT_CATEGORIES
from database import ProductSize

from .callbacks import (
    AdminAction,
    AdminCB,
    CategoryCatalogCB,
    CatalogCB,
    MyOrdersAction,
    MyOrdersCB,
    Nav,
    NavCB,
    OrderAction,
    OrderCB,
    PickCB,
    PickKind,
)


def main_menu_kb(is_admin: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🛍 Каталог", callback_data=CatalogCB(offset=0))
    kb.button(
        text="📦 Мои заказы",
        callback_data=MyOrdersCB(action=MyOrdersAction.SHOW),
    )
    if is_admin:
        kb.button(text="⚙️ Админ-панель", callback_data=AdminCB(action=AdminAction.MENU))
    kb.adjust(1)
    return kb.as_markup()


def my_orders_kb(
    orders: list[dict[str, object]], page: int, last_page: int
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for order in orders:
        order_id = int(order["id"])
        if can_cancel_order(order):
            kb.button(
                text=f"❌ Отменить заказ #{order_id}",
                callback_data=MyOrdersCB(
                    action=MyOrdersAction.ASK_CANCEL,
                    page=page,
                    order_id=order_id,
                ),
            )
    kb.adjust(1)

    navigation: list[InlineKeyboardButton] = []
    if page > 0:
        navigation.append(
            InlineKeyboardButton(
                text="⬅️",
                callback_data=MyOrdersCB(
                    action=MyOrdersAction.SHOW, page=page - 1
                ).pack(),
            )
        )
    if page < last_page:
        navigation.append(
            InlineKeyboardButton(
                text="➡️",
                callback_data=MyOrdersCB(
                    action=MyOrdersAction.SHOW, page=page + 1
                ).pack(),
            )
        )
    if navigation:
        kb.row(*navigation)
    kb.button(text="🏠 В меню", callback_data=NavCB(target=Nav.MAIN))
    return kb.as_markup()


def can_cancel_order(order: dict[str, object]) -> bool:
    return (
        order["status"] in ("new", "confirmed", "preparing")
        and order["product_id"] is not None
        and bool(order["size"])
        and order["np_ttn_number"] is None
        and order["np_ttn_creating"] == 0
    )


def confirm_order_cancel_kb(order_id: int, page: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ Да, отменить",
        callback_data=MyOrdersCB(
            action=MyOrdersAction.CONFIRM_CANCEL,
            page=page,
            order_id=order_id,
        ),
    )
    kb.button(
        text="↩️ Назад",
        callback_data=MyOrdersCB(action=MyOrdersAction.SHOW, page=page),
    )
    kb.adjust(1)
    return kb.as_markup()


def back_to_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🏠 В меню", callback_data=NavCB(target=Nav.MAIN))
    return kb.as_markup()


def catalog_categories_kb(has_legacy: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    categories = list(PRODUCT_CATEGORIES)
    if has_legacy:
        categories.append(LEGACY_CATEGORY)
    for category, label in categories:
        kb.button(
            text=label,
            callback_data=CategoryCatalogCB(category=category, offset=0),
        )
    kb.button(text="🏠 В меню", callback_data=NavCB(target=Nav.MAIN))
    kb.adjust(*([2] * (len(categories) // 2)), *([1] if len(categories) % 2 else []), 1)
    return kb.as_markup()


def catalog_kb(
    product_id: int, offset: int, total: int, has_stock: bool, category: str
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    layout: list[int] = []

    if total > 1:
        kb.button(
            text="⬅️",
            callback_data=CategoryCatalogCB(
                category=category, offset=(offset - 1) % total
            ),
        )
        kb.button(text=f"{offset + 1}/{total}", callback_data=NavCB(target=Nav.NOOP))
        kb.button(
            text="➡️",
            callback_data=CategoryCatalogCB(
                category=category, offset=(offset + 1) % total
            ),
        )
        layout.append(3)

    if has_stock:
        kb.button(
            text="🛒 Заказать",
            callback_data=OrderCB(action=OrderAction.START, product_id=product_id),
        )
    else:
        kb.button(text="Нет размеров в наличии", callback_data=NavCB(target=Nav.NOOP))
    kb.button(text="📂 К категориям", callback_data=CatalogCB(offset=0))
    kb.button(text="🏠 В меню", callback_data=NavCB(target=Nav.MAIN))
    layout += [1, 1, 1]

    kb.adjust(*layout)
    return kb.as_markup()


def product_sizes_kb(sizes: list[ProductSize]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for index, item in enumerate(sizes):
        kb.button(
            text=f"{item.size} — осталось {item.quantity}",
            callback_data=PickCB(kind=PickKind.SIZE, index=index),
        )
    kb.button(text="❌ Отменить заказ", callback_data=OrderCB(action=OrderAction.CANCEL))
    kb.adjust(1)
    return kb.as_markup()


def order_cancel_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отменить заказ", callback_data=OrderCB(action=OrderAction.CANCEL))
    return kb.as_markup()


def city_options_kb(names: list[str]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for index, name in enumerate(names):
        kb.button(text=name, callback_data=PickCB(kind=PickKind.CITY, index=index))
    kb.button(text="❌ Отменить заказ", callback_data=OrderCB(action=OrderAction.CANCEL))
    kb.adjust(1)
    return kb.as_markup()


def warehouse_options_kb(count: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for index in range(count):
        kb.button(
            text=str(index + 1),
            callback_data=PickCB(kind=PickKind.WAREHOUSE, index=index),
        )
    kb.adjust(5)
    kb.row(InlineKeyboardButton(
        text="🏙 Другой город",
        callback_data=PickCB(kind=PickKind.CHANGE_CITY).pack(),
    ))
    kb.row(InlineKeyboardButton(
        text="❌ Отменить заказ",
        callback_data=OrderCB(action=OrderAction.CANCEL).pack(),
    ))
    return kb.as_markup()
