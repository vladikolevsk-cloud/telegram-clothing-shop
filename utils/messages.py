from contextlib import suppress

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message


async def send_fresh(
    cb: CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup,
    photo: str | None = None,
) -> None:
    """Удаляет сообщение с кнопкой и шлёт новое.

    Текстовое сообщение нельзя отредактировать в фото (и наоборот),
    поэтому для единообразия всегда пересоздаём сообщение.
    """
    message = cb.message
    if not isinstance(message, Message):
        return

    with suppress(TelegramBadRequest):
        await message.delete()

    if photo:
        await message.answer_photo(photo, caption=text, reply_markup=reply_markup)
    else:
        await message.answer(text, reply_markup=reply_markup)
