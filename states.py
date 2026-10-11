from aiogram.fsm.state import State, StatesGroup


class OrderForm(StatesGroup):
    size = State()
    full_name = State()
    city = State()
    branch = State()
    phone = State()


class NPSetupForm(StatesGroup):
    sender = State()
    contact = State()
    sender_city = State()
    warehouse = State()


class AddProductForm(StatesGroup):
    name = State()
    description = State()
    price = State()
    sizes = State()
    photo = State()


class StockForm(StatesGroup):
    sizes = State()
