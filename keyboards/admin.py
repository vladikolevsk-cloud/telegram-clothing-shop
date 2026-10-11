from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from categories import PRODUCT_CATEGORIES
from database import Product
from utils.formatting import fmt_price

from .callbacks import (
    AddProductCategoryCB,
    AdminAction,
    AdminCB,
    NPSetupCB,
    NPSetupStep,
    Nav,
    NavCB,
)


def admin_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить товар", callback_data=AdminCB(action=AdminAction.ADD))
    kb.button(text="📏 Остатки по размерам", callback_data=AdminCB(action=AdminAction.STOCK))
    kb.button(text="🗑 Удалить товар", callback_data=AdminCB(action=AdminAction.LIST, page=0))
    kb.button(text="📦 Настроить отправителя НП", callback_data=AdminCB(action=AdminAction.NP_SETUP))
    kb.button(text="🏠 В меню", callback_data=NavCB(target=Nav.MAIN))
    kb.adjust(1)
    return kb.as_markup()


def cancel_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отмена", callback_data=AdminCB(action=AdminAction.CANCEL))
    return kb.as_markup()


def back_to_admin_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Назад", callback_data=AdminCB(action=AdminAction.MENU))
    return kb.as_markup()


def after_add_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить ещё", callback_data=AdminCB(action=AdminAction.ADD))
    kb.button(text="⚙️ Админ-панель", callback_data=AdminCB(action=AdminAction.MENU))
    kb.adjust(1)
    return kb.as_markup()


def add_product_categories_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for category, label in PRODUCT_CATEGORIES:
        kb.button(
            text=label,
            callback_data=AddProductCategoryCB(category=category),
        )
    kb.button(text="❌ Отмена", callback_data=AdminCB(action=AdminAction.CANCEL))
    kb.adjust(2, 2, 2, 2, 1)
    return kb.as_markup()


def delete_list_kb(products: list[Product], page: int, last_page: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for product in products:
        kb.button(
            text=f"🗑 {product.name} — {fmt_price(product.price)}",
            callback_data=AdminCB(action=AdminAction.DELETE, product_id=product.id),
        )
    kb.adjust(1)

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(
            text="⬅️",
            callback_data=AdminCB(action=AdminAction.LIST, page=page - 1).pack(),
        ))
    if page < last_page:
        nav.append(InlineKeyboardButton(
            text="➡️",
            callback_data=AdminCB(action=AdminAction.LIST, page=page + 1).pack(),
        ))
    nav.append(InlineKeyboardButton(
        text="⬅️ Назад",
        callback_data=AdminCB(action=AdminAction.MENU).pack(),
    ))
    kb.row(*nav)
    return kb.as_markup()


def stock_products_kb(
    products: list[Product], page: int, last_page: int
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for product in products:
        kb.button(
            text=f"📏 {product.name}",
            callback_data=AdminCB(
                action=AdminAction.UPDATE_STOCK, product_id=product.id
            ),
        )
    kb.adjust(1)

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                text="⬅️",
                callback_data=AdminCB(action=AdminAction.STOCK, page=page - 1).pack(),
            )
        )
    if page < last_page:
        nav.append(
            InlineKeyboardButton(
                text="➡️",
                callback_data=AdminCB(action=AdminAction.STOCK, page=page + 1).pack(),
            )
        )
    nav.append(
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=AdminCB(action=AdminAction.MENU).pack(),
        )
    )
    kb.row(*nav)
    return kb.as_markup()


def confirm_delete_kb(product_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ Да, удалить",
        callback_data=AdminCB(action=AdminAction.CONFIRM_DELETE, product_id=product_id),
    )
    kb.button(text="❌ Нет", callback_data=AdminCB(action=AdminAction.LIST, page=0))
    kb.adjust(2)
    return kb.as_markup()


def np_setup_options_kb(
    options: list[str], step: NPSetupStep
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for index, option in enumerate(options):
        kb.button(
            text=option[:60],
            callback_data=NPSetupCB(step=step, index=index),
        )
    kb.button(text="❌ Отмена", callback_data=AdminCB(action=AdminAction.MENU))
    kb.adjust(1)
    return kb.as_markup()


def create_waybill_kb(order_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="📦 Создать накладную",
        callback_data=AdminCB(action=AdminAction.CREATE_WAYBILL, order_id=order_id),
    )
    return kb.as_markup()


def reset_waybill_kb(order_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="⚠️ Я проверил НП — повторить создание",
        callback_data=AdminCB(action=AdminAction.RESET_WAYBILL, order_id=order_id),
    )
    return kb.as_markup()
