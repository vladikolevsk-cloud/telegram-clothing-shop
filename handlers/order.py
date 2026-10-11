import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from config import Config
from database import Database
from database.orders import ORDER_STATUS_LABELS, OutOfStockError
from keyboards.callbacks import (
    MyOrdersAction,
    MyOrdersCB,
    OrderAction,
    OrderCB,
    PickCB,
    PickKind,
)
from keyboards.admin import create_waybill_kb
from keyboards.user import (
    back_to_menu_kb,
    city_options_kb,
    can_cancel_order,
    confirm_order_cancel_kb,
    main_menu_kb,
    my_orders_kb,
    order_cancel_kb,
    product_sizes_kb,
    warehouse_options_kb,
)
from services.nova_poshta import NovaPoshtaClient, NovaPoshtaError
from states import OrderForm
from utils.formatting import fmt_price, order_admin_text
from utils.messages import send_fresh
from utils.validators import normalize_phone, squash_spaces

logger = logging.getLogger(__name__)
router = Router(name="order")
MY_ORDERS_PAGE_SIZE = 5

NP_UNAVAILABLE = "Сервис Новой почты сейчас недоступен. Попробуйте ещё раз через минуту."
CITY_PROMPT = "Введите название города (или населённого пункта):"


async def _show_my_orders(
    cb: CallbackQuery, db: Database, user_id: int, page: int
) -> None:
    total = await db.orders.count_for_user(user_id)
    if total == 0:
        await send_fresh(
            cb,
            "У вас пока нет оформленных заказов.",
            back_to_menu_kb(),
        )
        return

    last_page = (total - 1) // MY_ORDERS_PAGE_SIZE
    page = max(0, min(page, last_page))
    orders = await db.orders.get_page_for_user(
        user_id, page * MY_ORDERS_PAGE_SIZE, MY_ORDERS_PAGE_SIZE
    )

    lines = ["📦 <b>Ваши заказы</b>\n"]
    for order in orders:
        order_id = int(order["id"])
        product = escape(str(order["product_name"]))
        size = escape(str(order["size"] or "не указан"))
        status = ORDER_STATUS_LABELS.get(str(order["status"]), "Статус неизвестен")
        if order["np_ttn_creating"] == 2:
            status += " · Создание накладной требует проверки, свяжитесь с администратором"
        elif order["np_ttn_creating"] == 1:
            status += " · Накладная создаётся"
        lines.append(
            f"Заказ <b>#{order_id}</b> — {product}, размер {size}, "
            f"{fmt_price(float(order['price']))}\n"
            f"Статус: {status}"
        )
        if order["np_ttn_number"]:
            lines[-1] += f"\nТТН: <code>{escape(str(order['np_ttn_number']))}</code>"
        if can_cancel_order(order):
            lines[-1] += "\nМожно отменить кнопкой ниже."

    await send_fresh(
        cb,
        "\n\n".join(lines),
        my_orders_kb(orders, page, last_page),
    )


@router.callback_query(MyOrdersCB.filter(F.action == MyOrdersAction.SHOW))
async def show_my_orders(
    cb: CallbackQuery, callback_data: MyOrdersCB, db: Database
) -> None:
    await _show_my_orders(cb, db, cb.from_user.id, callback_data.page)
    await cb.answer()


@router.callback_query(MyOrdersCB.filter(F.action == MyOrdersAction.ASK_CANCEL))
async def ask_cancel_order(
    cb: CallbackQuery, callback_data: MyOrdersCB, db: Database
) -> None:
    order = await db.orders.get_for_user(callback_data.order_id, cb.from_user.id)
    if order is None:
        await cb.answer("Заказ не найден", show_alert=True)
        return
    if not can_cancel_order(order):
        await cb.answer(
            "Этот заказ уже нельзя отменить здесь. Свяжитесь с администратором.",
            show_alert=True,
        )
        return
    await send_fresh(
        cb,
        f"Отменить заказ #{callback_data.order_id}? "
        "Выбранный размер вернётся в остаток.",
        confirm_order_cancel_kb(callback_data.order_id, callback_data.page),
    )
    await cb.answer()


@router.callback_query(
    MyOrdersCB.filter(F.action == MyOrdersAction.CONFIRM_CANCEL)
)
async def confirm_cancel_order(
    cb: CallbackQuery,
    callback_data: MyOrdersCB,
    db: Database,
    config: Config,
    bot: Bot,
) -> None:
    result = await db.orders.cancel_for_user(
        callback_data.order_id, cb.from_user.id
    )
    if result == "not_found":
        await cb.answer("Заказ не найден", show_alert=True)
        return
    if result == "not_cancellable":
        await cb.answer(
            "Заказ уже нельзя отменить в боте. Обсудите отмену с администратором.",
            show_alert=True,
        )
        return

    cancelled_order = await db.orders.get_for_user(
        callback_data.order_id, cb.from_user.id
    )
    if cancelled_order is not None:
        cancellation_notice = (
            f"❌ <b>Покупатель отменил заказ #{callback_data.order_id}</b>\n"
            f"Товар: {escape(str(cancelled_order['product_name']))}\n"
            f"Размер: {escape(str(cancelled_order['size']))}\n"
            f"Telegram ID: <code>{cb.from_user.id}</code>"
        )
        for admin_id in config.admin_ids:
            try:
                await bot.send_message(admin_id, cancellation_notice)
            except TelegramAPIError as exc:
                logger.warning(
                    "Не удалось уведомить администратора %s об отмене заказа #%s: %s",
                    admin_id,
                    callback_data.order_id,
                    exc,
                )

    await cb.answer("Заказ отменён, остаток восстановлен")
    await _show_my_orders(cb, db, cb.from_user.id, callback_data.page)


@router.callback_query(OrderCB.filter(F.action == OrderAction.START))
async def start_order(
    cb: CallbackQuery, callback_data: OrderCB, state: FSMContext, db: Database
) -> None:
    product = await db.products.get(callback_data.product_id)
    if product is None:
        await cb.answer("Этот товар уже недоступен", show_alert=True)
        return

    stock = [
        item for item in await db.products.get_sizes(product.id) if item.quantity > 0
    ]
    if not stock:
        await cb.answer("У этого товара сейчас нет размеров в наличии", show_alert=True)
        return

    await state.clear()
    await state.update_data(
        product_id=product.id,
        size_options=[item.size for item in stock],
    )
    await state.set_state(OrderForm.size)
    size_lines = "\n".join(
        f"• {escape(item.size)} — осталось {item.quantity}" for item in stock
    )
    await send_fresh(
        cb,
        f"🛒 Заказ: <b>{escape(product.name)}</b> — {fmt_price(product.price)}\n\n"
        f"Выберите размер:\n{size_lines}",
        product_sizes_kb(stock),
    )
    await cb.answer()


@router.callback_query(OrderCB.filter(F.action == OrderAction.CANCEL))
async def cancel_order(cb: CallbackQuery, state: FSMContext, is_admin: bool) -> None:
    await state.clear()
    await send_fresh(cb, "Заказ отменён. Возвращаю в меню.", main_menu_kb(is_admin))
    await cb.answer()


@router.message(OrderForm.full_name, F.text)
async def process_full_name(message: Message, state: FSMContext) -> None:
    full_name = squash_spaces(message.text)
    if len(full_name.split()) < 2 or len(full_name) > 100:
        await message.answer(
            "Введите минимум фамилию и имя (например: Патюк Дмитро):",
            reply_markup=order_cancel_kb(),
        )
        return
    await state.update_data(full_name=full_name)
    await state.set_state(OrderForm.city)
    await message.answer(CITY_PROMPT, reply_markup=order_cancel_kb())


@router.callback_query(OrderForm.size, PickCB.filter(F.kind == PickKind.SIZE))
async def pick_product_size(
    cb: CallbackQuery,
    callback_data: PickCB,
    state: FSMContext,
    db: Database,
) -> None:
    data = await state.get_data()
    options = data.get("size_options") or []
    if not 0 <= callback_data.index < len(options):
        await cb.answer("Список размеров устарел. Начните заказ заново.", show_alert=True)
        return

    size = options[callback_data.index]
    stock = await db.products.get_size(data["product_id"], size)
    if stock is None or stock.quantity < 1:
        await cb.answer(
            f"Размер {size} уже закончился. Выберите другой размер в каталоге.",
            show_alert=True,
        )
        await state.clear()
        return

    await state.update_data(size=size)
    await state.set_state(OrderForm.full_name)
    product = await db.products.get(data["product_id"])
    if product is None:
        await state.clear()
        await cb.answer("Этот товар уже недоступен", show_alert=True)
        return
    await send_fresh(
        cb,
        f"Размер: <b>{escape(size)}</b>\n\n"
        "Введите ваше ФИО полностью (например: Шевченко Тарас Григорьевич):",
        order_cancel_kb(),
    )
    await cb.answer()


@router.message(OrderForm.city, F.text)
async def process_city_query(
    message: Message, state: FSMContext, np: NovaPoshtaClient
) -> None:
    query = squash_spaces(message.text)
    if not 2 <= len(query) <= 100:
        await message.answer("Введите название города:", reply_markup=order_cancel_kb())
        return

    try:
        cities = await np.search_cities(query)
    except NovaPoshtaError as exc:
        logger.warning("Поиск города не удался: %s", exc)
        await message.answer(NP_UNAVAILABLE, reply_markup=order_cancel_kb())
        return

    if not cities:
        await message.answer(
            "Не нашёл такой город. Проверьте написание и отправьте название ещё раз:",
            reply_markup=order_cancel_kb(),
        )
        return

    await state.update_data(city_options=[{"ref": c.ref, "name": c.name} for c in cities])
    await message.answer(
        "Выберите ваш город из списка.\nНужного нет? Отправьте название ещё раз.",
        reply_markup=city_options_kb([c.name for c in cities]),
    )


@router.callback_query(OrderForm.city, PickCB.filter(F.kind == PickKind.CITY))
async def pick_city(cb: CallbackQuery, callback_data: PickCB, state: FSMContext) -> None:
    data = await state.get_data()
    options = data.get("city_options") or []
    if not 0 <= callback_data.index < len(options):
        await cb.answer("Список устарел, введите город заново", show_alert=True)
        return

    city = options[callback_data.index]
    await state.update_data(city_ref=city["ref"], city=city["name"], city_options=None)
    await state.set_state(OrderForm.branch)
    await send_fresh(
        cb,
        f"📍 Город: <b>{escape(city['name'])}</b>\n\n"
        "Введите номер отделения (например: 5) или часть адреса.\n"
        "Для почтомата можно написать «поштомат»:",
        order_cancel_kb(),
    )
    await cb.answer()


@router.message(OrderForm.branch, F.text)
async def process_branch_query(
    message: Message, state: FSMContext, np: NovaPoshtaClient
) -> None:
    data = await state.get_data()
    query = squash_spaces(message.text)
    if not 1 <= len(query) <= 100:
        await message.answer(
            "Введите номер отделения или часть адреса:", reply_markup=order_cancel_kb()
        )
        return

    try:
        warehouses = await np.search_warehouses(data["city_ref"], query)
    except NovaPoshtaError as exc:
        logger.warning("Поиск отделения не удался: %s", exc)
        await message.answer(NP_UNAVAILABLE, reply_markup=order_cancel_kb())
        return

    if not warehouses:
        await message.answer(
            "Ничего не нашёл. Уточните номер отделения или адрес и отправьте ещё раз:",
            reply_markup=warehouse_options_kb(0),
        )
        return

    await state.update_data(
        warehouse_options=[{"ref": w.ref, "description": w.description} for w in warehouses]
    )
    lines = "\n".join(f"{i}. {escape(w.description)}" for i, w in enumerate(warehouses, 1))
    await message.answer(
        f"Выберите отделение:\n\n{lines}\n\n"
        "Нужного нет в списке? Уточните запрос и отправьте ещё раз.",
        reply_markup=warehouse_options_kb(len(warehouses)),
    )


@router.callback_query(OrderForm.branch, PickCB.filter(F.kind == PickKind.WAREHOUSE))
async def pick_warehouse(
    cb: CallbackQuery, callback_data: PickCB, state: FSMContext
) -> None:
    data = await state.get_data()
    options = data.get("warehouse_options") or []
    if not 0 <= callback_data.index < len(options):
        await cb.answer("Список устарел, введите отделение заново", show_alert=True)
        return

    warehouse = options[callback_data.index]
    await state.update_data(
        warehouse_ref=warehouse["ref"],
        branch=warehouse["description"],
        warehouse_options=None,
    )
    await state.set_state(OrderForm.phone)
    await send_fresh(
        cb,
        f"📮 Отделение: <b>{escape(warehouse['description'])}</b>\n\n"
        "Введите номер телефона (например: +380501234567 или 0501234567):",
        order_cancel_kb(),
    )
    await cb.answer()


@router.callback_query(OrderForm.branch, PickCB.filter(F.kind == PickKind.CHANGE_CITY))
async def change_city(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(OrderForm.city)
    await send_fresh(cb, CITY_PROMPT, order_cancel_kb())
    await cb.answer()


@router.message(OrderForm.phone, F.text)
async def process_phone(
    message: Message,
    state: FSMContext,
    db: Database,
    config: Config,
    bot: Bot,
    is_admin: bool,
) -> None:
    phone = normalize_phone(message.text)
    if phone is None:
        await message.answer(
            "Не похоже на украинский номер. Формат: +380501674567 или 0506734567",
            reply_markup=order_cancel_kb(),
        )
        return

    data = await state.get_data()
    product = await db.products.get(data["product_id"])
    if product is None:
        await state.clear()
        await message.answer("Этот товар уже недоступен 😔", reply_markup=main_menu_kb(is_admin))
        return

    user = message.from_user
    try:
        order_id = await db.orders.create(
            product=product,
            user_id=user.id,
            username=user.username,
            full_name=data["full_name"],
            city=data["city"],
            branch=data["branch"],
            phone=phone,
            np_city_ref=data["city_ref"],
            np_warehouse_ref=data["warehouse_ref"],
            size=data["size"],
        )
    except OutOfStockError:
        await state.clear()
        await message.answer(
            f"К сожалению, размер {escape(data['size'])} только что закончился. "
            "Заказ не оформлен — выберите другой размер в каталоге.",
            reply_markup=main_menu_kb(is_admin),
        )
        return
    await state.clear()

    admin_text = order_admin_text(
        order_id=order_id,
        product=product,
        full_name=data["full_name"],
        city=data["city"],
        branch=data["branch"],
        phone=phone,
        size=data["size"],
        user=user,
    )
    for admin_id in config.admin_ids:
        try:
            await bot.send_message(
                admin_id, admin_text, reply_markup=create_waybill_kb(order_id)
            )
        except TelegramAPIError as exc:
            # например, админ ещё не запускал бота
            logger.warning("Не удалось отправить заказ #%s админу %s: %s", order_id, admin_id, exc)

    await message.answer(
        f"✅ Заказ #{order_id} оформлен!\n"
        "Мы свяжемся с вами для подтверждения и отправим заказ Новой почтой.",
        reply_markup=main_menu_kb(is_admin),
    )
