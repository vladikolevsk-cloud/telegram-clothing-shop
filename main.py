import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import load_config
from database import Database
from handlers import setup_routers
from middlewares import AdminFlagMiddleware
from services.nova_poshta import NovaPoshtaClient


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    config = load_config()

    db = Database(config.db_path)
    await db.connect()

    np = NovaPoshtaClient(config.np_api_key)

    bot = Bot(config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage(), config=config, db=db, np=np)
    dp.update.outer_middleware(AdminFlagMiddleware())
    dp.include_router(setup_routers())

    try:
        await dp.start_polling(bot)
    finally:
        await np.close()
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот остановлен")
