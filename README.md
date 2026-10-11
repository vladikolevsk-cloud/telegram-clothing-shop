# Telegram Clothing Shop Bot 👕

An asynchronous Telegram bot for managing an online clothing store, built with Python and aiogram 3.

The bot allows customers to browse products, choose sizes, place orders, and arrange delivery via Nova Poshta. Administrators can manage the product catalog, inventory, and delivery settings directly through Telegram.

## ✨ Features

### Customer Features
- Browse products by category.
- View product details, prices, photos, and available sizes.
- Check product availability before placing an order.
- Place orders with recipient and Nova Poshta delivery information.
- Receive order-related feedback through Telegram.

### Admin Features
- Restricted admin panel with Telegram ID-based access control.
- Add and remove products.
- Manage product information, prices, sizes, and inventory.
- Configure Nova Poshta sender and shipping details.
- Create shipping waybills through the Nova Poshta API.
- Handle API errors and uncertain waybill creation results.

## 🛠 Tech Stack

- **Python** — application logic
- **aiogram 3** — asynchronous Telegram Bot API framework
- **SQLite** — database storage
- **aiosqlite** — asynchronous database operations
- **aiohttp** — asynchronous HTTP requests
- **python-dotenv** — environment variable management
- **Nova Poshta API** — shipping integration

## 📁 Project Structure

```text
telegram-clothing-shop/
├── assets/          # Static assets
├── database/        # Database operations and repositories
├── handlers/       # Telegram message and callback handlers
├── keyboards/      # Telegram keyboards
├── services/       # External API integrations
├── utils/          # Helper functions
├── categories.py   # Product categories
├── config.py       # Application configuration
├── filters.py      # Custom filters and access control
├── main.py         # Application entry point
├── middlewares.py  # Middleware
├── states.py       # FSM states
├── requirements.txt
└── .gitignore
```

## 🚀 Getting Started

### Prerequisites

- Python 3.10 or newer
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- A Nova Poshta API key for shipping functionality

### 1. Clone the Repository

```bash
git clone https://github.com/vladikolevsk-cloud/telegram-clothing-shop.git
cd telegram-clothing-shop
```

### 2. Create a Virtual Environment

**Windows:**

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Linux / macOS:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file in the project root:

```dotenv
BOT_TOKEN=your_telegram_bot_token
ADMIN_IDS=123456789
NOVA_POSHTA_API_KEY=your_nova_poshta_api_key
```

Replace the example values with your actual credentials.

- `BOT_TOKEN` — Telegram bot token.
- `ADMIN_IDS` — comma-separated Telegram user IDs authorized to access the admin panel.
- `NOVA_POSHTA_API_KEY` — API key for Nova Poshta integration.
- `DB_PATH` - Path to your db

Make sure `.env` is excluded from version control. **Never publish your bot token or API keys.**

### 5. Run the Bot

```bash
python main.py
```

Open your bot in Telegram and send `/start`.

## 🔒 Security

- Admin access is restricted by Telegram user ID.
- Secrets are loaded from environment variables.
- Environment files and local database files should remain outside the public repository.

## ⚠️ Notes

- FSM states use in-memory storage, so unfinished conversations are lost when the bot restarts.
- Inventory management and order cancellation should be tested carefully before production use.
- Nova Poshta API errors may leave the result of a waybill request uncertain. Verify the result before retrying to avoid duplicate records.
- Back up the SQLite database regularly when using real order data.

## 📌 Project Status

This project is under active development. Additional testing and improvements may be required before production deployment.

## 👨‍💻 Author

**vladikolevsk-cloud**

[GitHub Profile](https://github.com/vladikolevsk-cloud)
