from enum import Enum

from aiogram.filters.callback_data import CallbackData


class Nav(str, Enum):
    MAIN = "main"
    NOOP = "noop"


class NavCB(CallbackData, prefix="nav"):
    target: Nav


class CatalogCB(CallbackData, prefix="cat"):
    offset: int = 0


class CategoryCatalogCB(CallbackData, prefix="catitem"):
    category: str = ""
    offset: int = 0


class AddProductCategoryCB(CallbackData, prefix="addcat"):
    category: str


class OrderAction(str, Enum):
    START = "start"
    CANCEL = "cancel"


class OrderCB(CallbackData, prefix="order"):
    action: OrderAction
    product_id: int = 0


class MyOrdersAction(str, Enum):
    SHOW = "show"
    ASK_CANCEL = "ask"
    CONFIRM_CANCEL = "cancel"


class MyOrdersCB(CallbackData, prefix="myord"):
    action: MyOrdersAction
    page: int = 0
    order_id: int = 0


class AdminAction(str, Enum):
    MENU = "menu"
    ADD = "add"
    CANCEL = "cancel"
    LIST = "list"
    DELETE = "del"
    CONFIRM_DELETE = "delok"
    NP_SETUP = "npsetup"
    CREATE_WAYBILL = "waybill"
    RESET_WAYBILL = "wayreset"
    STOCK = "stock"
    UPDATE_STOCK = "stockset"


class AdminCB(CallbackData, prefix="adm"):
    action: AdminAction
    page: int = 0
    product_id: int = 0
    order_id: int = 0


class AdminOrderStatusCB(CallbackData, prefix="admst"):
    order_id: int
    status: str


class NPSetupStep(str, Enum):
    SENDER = "sender"
    CONTACT = "contact"
    CITY = "city"
    WAREHOUSE = "warehouse"


class NPSetupCB(CallbackData, prefix="npsetup"):
    step: NPSetupStep
    index: int = 0


class PickKind(str, Enum):
    SIZE = "size"
    CITY = "city"
    WAREHOUSE = "wh"
    CHANGE_CITY = "chg"


class PickCB(CallbackData, prefix="pick"):
    """Выбор варианта из списка, найденного через API Новой почты (по индексу в списке)."""

    kind: PickKind
    index: int = 0
