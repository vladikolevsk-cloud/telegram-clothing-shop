from aiogram import Router

from . import admin, catalog, order, start


def setup_routers() -> Router:
    root = Router(name="root")
    root.include_routers(start.router, admin.router, catalog.router, order.router)
    return root
