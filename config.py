import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Config:
    bot_token: str
    admin_ids: frozenset[int]
    np_api_key: str
    db_path: str = "shop.db"


def load_config() -> Config:
    load_dotenv()

    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN не задан: добавьте его в файл .env")

    try:
        admin_ids = frozenset(
            int(item) for item in os.getenv("ADMIN_IDS", "").split(",") if item.strip()
        )
    except ValueError as exc:
        raise RuntimeError("ADMIN_IDS должен быть списком чисел через запятую") from exc

    if not admin_ids:
        raise RuntimeError("ADMIN_IDS не задан: без админа некому принимать заказы")

    np_api_key = os.getenv("NOVA_POSHTA_API_KEY", "").strip()
    if not np_api_key:
        raise RuntimeError(
            "NOVA_POSHTA_API_KEY не задан: добавьте ключ API Новой почты в файл .env"
        )

    return Config(
        bot_token=token,
        admin_ids=admin_ids,
        np_api_key=np_api_key,
        db_path=os.getenv("DB_PATH", "shop.db"),
    )
