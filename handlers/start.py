from html import escape
from pathlib import Path

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from keyboards.callbacks import Nav, NavCB
from keyboards.user import main_menu_kb
from utils.messages import send_fresh

router = Router(name="start")
WELCOME_PHOTO = Path(__file__).resolve().parent.parent / "assets" / "welcome.jpg"


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, is_admin: bool) -> None:
    await state.clear()
    name = escape(message.from_user.first_name) if message.from_user else "друг"
    await message.answer_photo(
        FSInputFile(WELCOME_PHOTO),
        caption=(
            f"Привет, {name}! 👋\n"
            "Добро пожаловать в магазин одежды dota2 shop.\n"
            "Доставляем по всей Украине Новой почтой 📦"
        ),
        reply_markup=main_menu_kb(is_admin),
    )


@router.callback_query(NavCB.filter(F.target == Nav.MAIN))
async def to_main_menu(cb: CallbackQuery, state: FSMContext, is_admin: bool) -> None:
    await state.clear()
    await send_fresh(cb, "Главное меню:", main_menu_kb(is_admin))
    await cb.answer()


@router.callback_query(NavCB.filter(F.target == Nav.NOOP))
async def noop(cb: CallbackQuery) -> None:
    await cb.answer()
