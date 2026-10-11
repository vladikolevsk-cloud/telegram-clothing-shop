from html import escape

from aiogram.types import User

from database import Product, ProductSize

CURRENCY = "грн"


def fmt_price(value: float) -> str:
    """2490 -> '2 490 грн', 1999.5 -> '1 999.50 грн'."""
    if float(value).is_integer():
        amount = f"{int(value):,}"
    else:
        amount = f"{value:,.2f}"
    return f"{amount.replace(',', ' ')} {CURRENCY}"


def product_text(product: Product, sizes: list[ProductSize]) -> str:
    parts = [f"<b>{escape(product.name)}</b>"]
    if product.description:
        parts.append(escape(product.description))
    parts.append(f"💰 {fmt_price(product.price)}")
    if sizes:
        sizes_text = ", ".join(
            f"{escape(item.size)} ({item.quantity})"
            if item.quantity > 0
            else f"{escape(item.size)} (нет в наличии)"
            for item in sizes
        )
        parts.append(f"📏 Размеры: {sizes_text}")
    else:
        parts.append("📏 Размеры пока не добавлены")
    return "\n\n".join(parts)


def order_admin_text(
    order_id: int,
    product: Product,
    full_name: str,
    city: str,
    branch: str,
    phone: str,
    size: str,
    user: User,
) -> str:
    if user.username:
        buyer = f"@{escape(user.username)}"
    else:
        buyer = f'<a href="tg://user?id={user.id}">профиль</a>'

    return (
        f"🆕 <b>Новый заказ #{order_id}</b>\n\n"
        f"🛍 Товар: <b>{escape(product.name)}</b>\n"
        f"📏 Размер: <b>{escape(size)}</b>\n"
        f"💰 Цена: {fmt_price(product.price)}\n\n"
        f"👤 ФИО: {escape(full_name)}\n"
        f"🏙 Город: {escape(city)}\n"
        f"📮 Новая почта: {escape(branch)}\n"
        f"📞 Телефон: {escape(phone)}\n\n"
        "Оплата: наложенный платёж на стоимость товара; доставку оплачивает получатель.\n\n"
        f"💬 Покупатель в Telegram: {buyer}\n"
        f"🆔 ID: <code>{user.id}</code>"
    )
