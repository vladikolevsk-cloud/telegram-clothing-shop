from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User

from config import Config


class AdminFlagMiddleware(BaseMiddleware):

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        config: Config = data["config"]
        user: User | None = data.get("event_from_user")
        data["is_admin"] = user is not None and user.id in config.admin_ids
        return await handler(event, data)
