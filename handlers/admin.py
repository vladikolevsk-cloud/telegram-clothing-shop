import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from categories import CATEGORY_LABELS
from database import Database
from database.orders import ORDER_STATUS_LABELS
from filters import IsAdmin
from keyboards.admin import (
    admin_menu_kb,
    add_product_categories_kb,
    after_add_kb,
    back_to_admin_kb,
    cancel_kb,
    confirm_delete_kb,
    create_waybill_kb,
    delete_list_kb,
    np_setup_options_kb,
    reset_waybill_kb,
    stock_products_kb,
)
from keyboards.callbacks import (
    AddProductCategoryCB,
    AdminAction,
    AdminCB,
    AdminOrderStatusCB,
    NPSetupCB,
    NPSetupStep,
)
from services.nova_poshta import (
    NovaPoshtaClient,
    NovaPoshtaError,
    NovaPoshtaWaybillOutcomeUnknown,
)
from states import AddProductForm, NPSetupForm, StockForm
from utils.formatting import CURRENCY
from utils.messages import send_fresh
from utils.validators import parse_price, parse_size_stock, squash_spaces

PAGE_SIZE = 8

logger = logging.getLogger(__name__)
router = Router(name="admin")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())



@router.callback_query(AdminCB.filter(F.action == AdminAction.MENU))
async def admin_menu(cb: CallbackQuery, state: FSMContext, db: Database) -> None:
    await state.clear()
    total = await db.products.count()
    await send_fresh(cb, f"⚙️ Админ-панель\nТоваров в каталоге: {total}", admin_menu_kb())
    await cb.answer()


@router.callback_query(AdminCB.filter(F.action == AdminAction.CANCEL))
async def admin_cancel(cb: CallbackQuery, state: FSMContext, db: Database) -> None:
    await admin_menu(cb, state, db)


@router.callback_query(AdminCB.filter(F.action == AdminAction.ADD))
async def add_start(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await send_fresh(
        cb,
        "Выберите категорию нового товара:",
        add_product_categories_kb(),
    )
    await cb.answer()


@router.callback_query(AddProductCategoryCB.filter())
async def add_select_category(
    cb: CallbackQuery,
    callback_data: AddProductCategoryCB,
    state: FSMContext,
) -> None:
    category = callback_data.category
    if category not in CATEGORY_LABELS or category == "uncategorized":
        await cb.answer("Неизвестная категория", show_alert=True)
        return
    await state.update_data(category=category)
    await state.set_state(AddProductForm.name)
    await send_fresh(cb, "Введите название товара:", cancel_kb())
    await cb.answer()


@router.message(AddProductForm.name, F.text)
async def add_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=squash_spaces(message.text)[:100])
    await state.set_state(AddProductForm.description)
    await message.answer(
        "Введите описание (или «-», чтобы пропустить):", reply_markup=cancel_kb()
    )


@router.message(AddProductForm.description, F.text)
async def add_description(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    await state.update_data(description=None if text == "-" else text[:500])
    await state.set_state(AddProductForm.price)
    await message.answer(
        f"Введите цену в {CURRENCY} (например, 1299):", reply_markup=cancel_kb()
    )


@router.message(AddProductForm.price, F.text)
async def add_price(message: Message, state: FSMContext) -> None:
    price = parse_price(message.text)
    if price is None:
        await message.answer(
            "Нужно положительное число, например 1299. Попробуйте ещё раз:",
            reply_markup=cancel_kb(),
        )
        return
    await state.update_data(price=price)
    await state.set_state(AddProductForm.sizes)
    category = (await state.get_data()).get("category")
    size_example = "40: 2, 41: 3, 42: 1" if category == "shoes" else "XS: 2, S: 3, M: 1"
    await message.answer(
        "Укажите размеры и количество каждого через запятую.\n"
        f"Пример: <code>{size_example}</code>",
        reply_markup=cancel_kb(),
    )


@router.message(AddProductForm.sizes, F.text)
async def add_sizes(message: Message, state: FSMContext) -> None:
    sizes = parse_size_stock(message.text)
    if sizes is None:
        await message.answer(
            "Формат неверный. Укажите уникальные размеры с положительным количеством, "
            "например, как в предыдущем сообщении.",
            reply_markup=cancel_kb(),
        )
        return
    await state.update_data(sizes=sizes)
    await state.set_state(AddProductForm.photo)
    await message.answer(
        "Отправьте фото товара (или /skip, чтобы без фото):", reply_markup=cancel_kb()
    )


async def _finish_add(
    message: Message, state: FSMContext, db: Database, photo_id: str | None
) -> None:
    data = await state.get_data()
    await state.clear()
    await db.products.add(
        data["name"],
        data.get("description"),
        data["price"],
        photo_id,
        data["category"],
        data["sizes"],
    )
    await message.answer(
        f"✅ Товар «{escape(data['name'])}» добавлен в категорию "
        f"«{escape(CATEGORY_LABELS[data['category']])}».\n"
        "Остатки: "
        + escape(", ".join(
            f"{size}: {quantity}" for size, quantity in data["sizes"].items()
        ))
        + ".",
        reply_markup=after_add_kb(),
    )


@router.message(AddProductForm.photo, F.photo)
async def add_photo(message: Message, state: FSMContext, db: Database) -> None:
    await _finish_add(message, state, db, message.photo[-1].file_id)


@router.message(AddProductForm.photo, Command("skip"))
async def add_skip_photo(message: Message, state: FSMContext, db: Database) -> None:
    await _finish_add(message, state, db, None)


async def _show_delete_list(cb: CallbackQuery, db: Database, page: int) -> None:
    total = await db.products.count()
    if total == 0:
        await send_fresh(cb, "Каталог пуст — удалять нечего.", back_to_admin_kb())
        await cb.answer()
        return

    last_page = (total - 1) // PAGE_SIZE
    page = max(0, min(page, last_page))
    products = await db.products.get_page(page * PAGE_SIZE, PAGE_SIZE)

    await send_fresh(
        cb, "Выберите товар для удаления:", delete_list_kb(products, page, last_page)
    )
    await cb.answer()


@router.callback_query(AdminCB.filter(F.action == AdminAction.LIST))
async def delete_list(cb: CallbackQuery, callback_data: AdminCB, db: Database) -> None:
    await _show_delete_list(cb, db, callback_data.page)


@router.callback_query(AdminCB.filter(F.action == AdminAction.DELETE))
async def delete_confirm(cb: CallbackQuery, callback_data: AdminCB, db: Database) -> None:
    product = await db.products.get(callback_data.product_id)
    if product is None:
        await cb.answer("Товар уже удалён", show_alert=True)
        return
    await send_fresh(
        cb, f"Удалить «{escape(product.name)}»?", confirm_delete_kb(product.id)
    )
    await cb.answer()


@router.callback_query(AdminCB.filter(F.action == AdminAction.CONFIRM_DELETE))
async def delete_product(cb: CallbackQuery, callback_data: AdminCB, db: Database) -> None:
    await db.products.delete(callback_data.product_id)
    await _show_delete_list(cb, db, 0)



async def _show_stock_products(
    cb: CallbackQuery, db: Database, page: int
) -> None:
    total = await db.products.count()
    if total == 0:
        await send_fresh(cb, "Каталог пуст — товаров нет.", back_to_admin_kb())
        await cb.answer()
        return

    last_page = (total - 1) // PAGE_SIZE
    page = max(0, min(page, last_page))
    products = await db.products.get_page(page * PAGE_SIZE, PAGE_SIZE)
    await send_fresh(
        cb,
        "Выберите товар, для которого нужно изменить остатки:",
        stock_products_kb(products, page, last_page),
    )
    await cb.answer()


@router.callback_query(AdminCB.filter(F.action == AdminAction.STOCK))
async def stock_list(
    cb: CallbackQuery, callback_data: AdminCB, db: Database
) -> None:
    await _show_stock_products(cb, db, callback_data.page)


@router.callback_query(AdminCB.filter(F.action == AdminAction.UPDATE_STOCK))
async def stock_update_start(
    cb: CallbackQuery,
    callback_data: AdminCB,
    state: FSMContext,
    db: Database,
) -> None:
    product = await db.products.get(callback_data.product_id)
    if product is None:
        await cb.answer("Товар уже удалён", show_alert=True)
        return
    current = await db.products.get_sizes(product.id)
    current_text = ", ".join(f"{item.size}: {item.quantity}" for item in current) or "не заданы"
    await state.clear()
    await state.set_state(StockForm.sizes)
    await state.update_data(stock_product_id=product.id)
    await send_fresh(
        cb,
        f"Остатки товара <b>{escape(product.name)}</b>: {escape(current_text)}\n\n"
        "Введите новый полный список размеров и остатков, например "
        "<code>XS: 2, S: 3, M: 1</code>.\n"
        "Этот список заменит текущие остатки.",
        cancel_kb(),
    )
    await cb.answer()


@router.message(StockForm.sizes, F.text)
async def stock_update_save(
    message: Message, state: FSMContext, db: Database
) -> None:
    sizes = parse_size_stock(message.text)
    if sizes is None:
        await message.answer(
            "Формат неверный. Укажите размеры и положительные количества, "
            "например: <code>XS: 2, S: 3, M: 1</code>",
            reply_markup=cancel_kb(),
        )
        return

    data = await state.get_data()
    product = await db.products.get(data["stock_product_id"])
    if product is None:
        await state.clear()
        await message.answer("Товар уже удалён; остатки не обновлены.")
        return
    updated = await db.products.set_sizes(product.id, sizes)
    if not updated:
        await state.clear()
        await message.answer("Товар уже удалён; остатки не обновлены.")
        return
    await state.clear()
    stock_text = ", ".join(f"{size}: {quantity}" for size, quantity in sizes.items())
    await message.answer(
        f"✅ Остатки товара «{escape(product.name)}» обновлены: "
        f"{escape(stock_text)}.",
        reply_markup=back_to_admin_kb(),
    )


@router.callback_query(AdminCB.filter(F.action == AdminAction.NP_SETUP))
async def np_setup_start(
    cb: CallbackQuery, state: FSMContext, np: NovaPoshtaClient
) -> None:
    try:
        senders = await np.get_senders()
    except NovaPoshtaError as exc:
        logger.warning("Не удалось получить отправителей Новой почты: %s", exc)
        await cb.answer("Не удалось загрузить отправителей Новой почты", show_alert=True)
        return

    if not senders:
        await send_fresh(
            cb,
            "В аккаунте Новой почты не найден отправитель. "
            "Проверьте API-ключ и наличие отправителя в аккаунте НП.",
            back_to_admin_kb(),
        )
        await cb.answer()
        return

    await state.clear()
    await state.set_state(NPSetupForm.sender)
    await state.update_data(
        np_sender_options=[
            {
                "ref": sender.ref,
                "name": sender.name,
                "city_name": sender.city_name,
            }
            for sender in senders
        ]
    )
    await send_fresh(
        cb,
        "Выберите отправителя из аккаунта Новой почты:",
        np_setup_options_kb(
            [
                f"{sender.name} — {sender.city_name}" if sender.city_name else sender.name
                for sender in senders
            ],
            NPSetupStep.SENDER,
        ),
    )
    await cb.answer()


@router.callback_query(
    NPSetupForm.sender,
    NPSetupCB.filter(F.step == NPSetupStep.SENDER),
)
async def np_setup_pick_sender(
    cb: CallbackQuery,
    callback_data: NPSetupCB,
    state: FSMContext,
    np: NovaPoshtaClient,
) -> None:
    data = await state.get_data()
    options = data.get("np_sender_options") or []
    if not 0 <= callback_data.index < len(options):
        await cb.answer("Список устарел, настройку нужно начать заново", show_alert=True)
        return

    sender = options[callback_data.index]
    try:
        contacts = await np.get_sender_contacts(sender["ref"])
    except NovaPoshtaError as exc:
        logger.warning("Не удалось получить контакты отправителя: %s", exc)
        await cb.answer("Не удалось загрузить контакты отправителя", show_alert=True)
        return

    if not contacts:
        await cb.answer("У отправителя нет контактных лиц в аккаунте НП", show_alert=True)
        return

    await state.update_data(
        np_sender=sender,
        np_contact_options=[
            {"ref": contact.ref, "name": contact.name, "phone": contact.phone}
            for contact in contacts
        ],
    )
    await state.set_state(NPSetupForm.contact)
    await send_fresh(
        cb,
        "Выберите контактное лицо отправителя:",
        np_setup_options_kb(
            [f"{contact.name} — {contact.phone}" for contact in contacts],
            NPSetupStep.CONTACT,
        ),
    )
    await cb.answer()


@router.callback_query(
    NPSetupForm.contact,
    NPSetupCB.filter(F.step == NPSetupStep.CONTACT),
)
async def np_setup_pick_contact(
    cb: CallbackQuery,
    callback_data: NPSetupCB,
    state: FSMContext,
    np: NovaPoshtaClient,
) -> None:
    data = await state.get_data()
    options = data.get("np_contact_options") or []
    if not 0 <= callback_data.index < len(options):
        await cb.answer("Список устарел, настройку нужно начать заново", show_alert=True)
        return

    contact = options[callback_data.index]
    sender = data["np_sender"]
    await state.update_data(np_sender_contact=contact)
    await state.set_state(NPSetupForm.sender_city)
    if not sender["city_name"]:
        await send_fresh(
            cb,
            "В профиле отправителя город не указан. Введите город, откуда будете отправлять заказы:",
            cancel_kb(),
        )
        await cb.answer()
        return

    try:
        cities = await np.search_cities(sender["city_name"])
    except NovaPoshtaError as exc:
        logger.warning("Не удалось определить город отправителя: %s", exc)
        await cb.answer("Не удалось найти город отправителя через API НП", show_alert=True)
        return

    if not cities:
        await cb.answer(
            f"Не удалось найти город «{sender['city_name']}» отправителя в справочнике НП",
            show_alert=True,
        )
        return

    await state.update_data(
        np_sender_city_options=[
            {"ref": city.ref, "name": city.name} for city in cities
        ],
    )
    await send_fresh(
        cb,
        f"Выберите город отправителя Новой почты "
        f"(в профиле отправителя: {escape(sender['city_name'])}):",
        np_setup_options_kb(
            [city.name for city in cities],
            NPSetupStep.CITY,
        ),
    )
    await cb.answer()


@router.message(NPSetupForm.sender_city, F.text)
async def np_setup_search_sender_city(
    message: Message, state: FSMContext, np: NovaPoshtaClient
) -> None:
    query = squash_spaces(message.text)
    if len(query) < 2:
        await message.answer(
            "Введите название города (минимум 2 символа):",
            reply_markup=cancel_kb(),
        )
        return

    try:
        cities = await np.search_cities(query)
    except NovaPoshtaError as exc:
        logger.warning("Не удалось найти город отправителя: %s", exc)
        await message.answer(
            "Не удалось найти город через API Новой почты. "
            "Проверьте написание и попробуйте ещё раз:",
            reply_markup=cancel_kb(),
        )
        return

    if not cities:
        await message.answer(
            "Город не найден. Введите название ещё раз:",
            reply_markup=cancel_kb(),
        )
        return

    await state.update_data(
        np_sender_city_options=[
            {"ref": city.ref, "name": city.name} for city in cities
        ]
    )
    await message.answer(
        "Выберите город отправителя:",
        reply_markup=np_setup_options_kb(
            [city.name for city in cities],
            NPSetupStep.CITY,
        ),
    )


@router.callback_query(
    NPSetupForm.sender_city,
    NPSetupCB.filter(F.step == NPSetupStep.CITY),
)
async def np_setup_pick_sender_city(
    cb: CallbackQuery,
    callback_data: NPSetupCB,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    options = data.get("np_sender_city_options") or []
    if not 0 <= callback_data.index < len(options):
        await cb.answer("Список устарел, настройку нужно начать заново", show_alert=True)
        return

    city = options[callback_data.index]
    sender = data["np_sender"]
    sender["city_ref"] = city["ref"]
    sender["city_name"] = city["name"]
    await state.update_data(np_sender=sender)
    await state.set_state(NPSetupForm.warehouse)
    await send_fresh(
        cb,
        f"Город отправителя: <b>{escape(city['name'])}</b>\n\n"
        "Введите номер или часть адреса отделения отправки:",
        cancel_kb(),
    )
    await cb.answer()


@router.message(NPSetupForm.warehouse, F.text)
async def np_setup_search_warehouse(
    message: Message, state: FSMContext, np: NovaPoshtaClient
) -> None:
    data = await state.get_data()
    query = squash_spaces(message.text)
    if not query:
        await message.answer(
            "Введите номер или адрес отделения:",
            reply_markup=cancel_kb(),
        )
        return

    try:
        warehouses = await np.search_warehouses(data["np_sender"]["city_ref"], query)
    except NovaPoshtaError as exc:
        logger.warning("Не удалось найти отделение отправителя: %s", exc)
        await message.answer(
            "Не удалось найти отделение через API Новой почты.\n"
            f"<b>Причина:</b> <code>{escape(str(exc))}</code>\n\n"
            "Проверьте, что выбран правильный город отправителя и попробуйте снова:",
            reply_markup=cancel_kb(),
        )
        return

    if not warehouses:
        await message.answer(
            "Отделение не найдено. Уточните номер или адрес и попробуйте ещё раз:",
            reply_markup=cancel_kb(),
        )
        return

    await state.update_data(
        np_warehouse_options=[
            {"ref": warehouse.ref, "description": warehouse.description}
            for warehouse in warehouses
        ]
    )
    await message.answer(
        "Выберите отделение отправки:",
        reply_markup=np_setup_options_kb(
            [warehouse.description for warehouse in warehouses],
            NPSetupStep.WAREHOUSE,
        ),
    )


@router.callback_query(
    NPSetupForm.warehouse,
    NPSetupCB.filter(F.step == NPSetupStep.WAREHOUSE),
)
async def np_setup_pick_warehouse(
    cb: CallbackQuery,
    callback_data: NPSetupCB,
    state: FSMContext,
    db: Database,
) -> None:
    data = await state.get_data()
    options = data.get("np_warehouse_options") or []
    if not 0 <= callback_data.index < len(options):
        await cb.answer("Список устарел, настройку нужно начать заново", show_alert=True)
        return

    sender = data["np_sender"]
    contact = data["np_sender_contact"]
    warehouse = options[callback_data.index]
    await db.np_settings.set_many(
        {
            "sender_ref": sender["ref"],
            "sender_city_ref": sender["city_ref"],
            "sender_city_name": sender["city_name"],
            "sender_contact_ref": contact["ref"],
            "sender_phone": contact["phone"],
            "sender_warehouse_ref": warehouse["ref"],
            "sender_warehouse_name": warehouse["description"],
        }
    )
    await state.clear()
    await send_fresh(
        cb,
        "✅ Отправитель Новой почты настроен.\n"
        f"Город: {escape(sender['city_name'])}\n"
        f"Отделение: {escape(warehouse['description'])}\n"
        f"Контакт: {escape(contact['name'])} ({escape(contact['phone'])})",
        back_to_admin_kb(),
    )
    await cb.answer()



@router.callback_query(AdminOrderStatusCB.filter())
async def update_order_status(
    cb: CallbackQuery,
    callback_data: AdminOrderStatusCB,
    db: Database,
    bot: Bot,
) -> None:
    result, user_id = await db.orders.advance_status(
        callback_data.order_id, callback_data.status
    )
    if result == "not_found":
        await cb.answer("Заказ не найден", show_alert=True)
        return
    if result == "invalid" or user_id is None:
        await cb.answer(
            "Этот статус сейчас нельзя установить. Проверьте заказ и наличие накладной.",
            show_alert=True,
        )
        return

    label = ORDER_STATUS_LABELS[callback_data.status]
    try:
        await bot.send_message(
            user_id,
            f"📦 Статус вашего заказа #{callback_data.order_id} обновлён: "
            f"<b>{label}</b>.",
        )
    except TelegramAPIError as exc:
        logger.warning(
            "Не удалось уведомить покупателя %s об изменении статуса заказа #%s: %s",
            user_id,
            callback_data.order_id,
            exc,
        )

    order = await db.orders.get_for_admin(callback_data.order_id)
    message = cb.message
    if order is not None and isinstance(message, Message):
        await message.edit_reply_markup(
            reply_markup=create_waybill_kb(
                callback_data.order_id,
                status=str(order["status"]),
                has_waybill=bool(order["np_ttn_number"]),
            )
        )
    await cb.answer(f"Статус изменён: {label}")


@router.callback_query(AdminCB.filter(F.action == AdminAction.CREATE_WAYBILL))
async def create_waybill(
    cb: CallbackQuery,
    callback_data: AdminCB,
    db: Database,
    np: NovaPoshtaClient,
) -> None:
    sender = await db.np_settings.get_all()
    required_settings = (
        "sender_ref",
        "sender_city_ref",
        "sender_contact_ref",
        "sender_phone",
        "sender_warehouse_ref",
    )
    if any(not sender.get(key) for key in required_settings):
        await cb.answer(
            "Сначала настройте отправителя в админ-панели: «Настроить отправителя НП»",
            show_alert=True,
        )
        return

    order = await db.orders.reserve_waybill(callback_data.order_id)
    if order is None:
        await cb.answer("Заказ не найден", show_alert=True)
        return
    if order.get("status") == "cancelled":
        await cb.answer("Покупатель отменил этот заказ", show_alert=True)
        return
    if order.get("np_ttn_number"):
        await cb.answer(
            f"Накладная уже создана: {order['np_ttn_number']}",
            show_alert=True,
        )
        return
    if not order.get("np_ttn_reserved"):
        await cb.answer("Накладная по этому заказу уже создаётся", show_alert=True)
        return

    try:
        waybill = await np.create_waybill(
            sender_ref=sender["sender_ref"],
            sender_city_ref=sender["sender_city_ref"],
            sender_warehouse_ref=sender["sender_warehouse_ref"],
            sender_contact_ref=sender["sender_contact_ref"],
            sender_phone=sender["sender_phone"],
            city_ref=str(order["np_city_ref"] or ""),
            warehouse_ref=str(order["np_warehouse_ref"] or ""),
            full_name=str(order["full_name"]),
            phone=str(order["phone"]),
            product_name=str(order["product_name"]),
            product_size=str(order["size"] or ""),
            price=float(order["price"]),
        )
    except NovaPoshtaWaybillOutcomeUnknown as exc:
        await db.orders.mark_waybill_unknown(callback_data.order_id)
        logger.error(
            "Неизвестен результат создания накладной для заказа #%s: %s",
            callback_data.order_id,
            exc,
        )
        await cb.answer(
            "Ответ НП не получен. Проверьте кабинет: запрос мог создать накладную. "
            "Повторная отправка заблокирована до проверки.",
            show_alert=True,
        )
        message = cb.message
        if isinstance(message, Message):
            await message.answer(
                "Если накладной в кабинете НП нет, нажмите кнопку для повторной попытки:",
                reply_markup=reset_waybill_kb(callback_data.order_id),
            )
        return
    except NovaPoshtaError as exc:
        await db.orders.release_waybill(callback_data.order_id)
        logger.warning(
            "Не удалось создать накладную для заказа #%s: %s",
            callback_data.order_id,
            exc,
        )
        await cb.answer("Новая почта не создала накладную. Проверьте данные и повторите.", show_alert=True)
        return

    await db.orders.complete_waybill(callback_data.order_id, waybill.ref, waybill.number)
    message = cb.message
    if isinstance(message, Message):
        order = await db.orders.get_for_admin(callback_data.order_id)
        if order is not None:
            await message.edit_reply_markup(
                reply_markup=create_waybill_kb(
                    callback_data.order_id,
                    status=str(order["status"]),
                    has_waybill=True,
                )
            )
        await message.answer(
            f"✅ Накладная для заказа #{callback_data.order_id} создана.\n"
            f"ТТН: <code>{escape(waybill.number)}</code>"
        )
    await cb.answer("Накладная создана")


@router.callback_query(AdminCB.filter(F.action == AdminAction.RESET_WAYBILL))
async def reset_unknown_waybill(
    cb: CallbackQuery, callback_data: AdminCB, db: Database
) -> None:
    reset = await db.orders.reset_unknown_waybill(callback_data.order_id)
    if not reset:
        await cb.answer(
            "Сбросить нельзя: заказ изменился или накладная уже есть.",
            show_alert=True,
        )
        return
    message = cb.message
    if isinstance(message, Message):
        await message.edit_reply_markup(reply_markup=None)
        order = await db.orders.get_for_admin(callback_data.order_id)
        await message.answer(
            "Проверка завершена. Можно повторить создание накладной:",
            reply_markup=create_waybill_kb(
                callback_data.order_id,
                status=str(order["status"]) if order else "new",
                has_waybill=bool(order and order["np_ttn_number"]),
            ),
        )
    await cb.answer("Повторная попытка разрешена")
