from aiogram import Router
from aiogram.types import CallbackQuery

from categories import CATEGORY_LABELS
from database import Database
from keyboards.callbacks import CategoryCatalogCB, CatalogCB
from keyboards.user import catalog_categories_kb, catalog_kb
from utils.formatting import product_text
from utils.messages import send_fresh

router = Router(name="catalog")


@router.callback_query(CatalogCB.filter())
async def show_catalog_categories(cb: CallbackQuery, db: Database) -> None:
    has_legacy = await db.products.count("uncategorized") > 0
    await send_fresh(
        cb,
        "Выберите категорию:",
        catalog_categories_kb(has_legacy),
    )
    await cb.answer()


@router.callback_query(CategoryCatalogCB.filter())
async def show_category_catalog(
    cb: CallbackQuery, callback_data: CategoryCatalogCB, db: Database
) -> None:
    category_label = CATEGORY_LABELS.get(callback_data.category)
    if category_label is None:
        await cb.answer("Эта категория больше недоступна", show_alert=True)
        return

    total = await db.products.count(callback_data.category)
    if total == 0:
        has_legacy = await db.products.count("uncategorized") > 0
        await send_fresh(
            cb,
            f"В категории «{category_label}» пока нет товаров.",
            catalog_categories_kb(has_legacy),
        )
        await cb.answer()
        return

    offset = callback_data.offset % total
    product = await db.products.get_at(offset, callback_data.category)
    if product is None:  
        await cb.answer("Каталог обновился, попробуйте ещё раз", show_alert=True)
        return

    sizes = await db.products.get_sizes(product.id)
    available_sizes = [item for item in sizes if item.quantity > 0]
    await send_fresh(
        cb,
        f"📂 <b>{category_label}</b>\n\n{product_text(product, sizes)}",
        catalog_kb(
            product.id,
            offset,
            total,
            bool(available_sizes),
            callback_data.category,
        ),
        photo=product.photo_id,
    )
    await cb.answer()
