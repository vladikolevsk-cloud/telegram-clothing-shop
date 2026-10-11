from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject


class IsAdmin(BaseFilter):
    """Пропускает событие, только если его автор — админ (флаг ставит AdminFlagMiddleware)."""

    async def __call__(self, event: TelegramObject, is_admin: bool) -> bool:
        return is_admin
