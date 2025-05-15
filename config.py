# config.py
import os
from dotenv import load_dotenv
load_dotenv(".env")


# Настройки API Telegram
API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
BOT_TOKEN = os.getenv('BOT_TOKEN')

DB_HOST = os.getenv('DB_HOST')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_NAME = os.getenv('DB_NAME')
BINANCE_API_KEY = os.getenv('BINANCE_API_KEY')
BINANCE_API_SECRET = os.getenv('BINANCE_API_SECRET')

# Админ
SUPER_ADMIN_ID = int(os.getenv('SUPER_ADMIN_ID'))
ACCOUNTS_PER_PAGE = int(os.getenv('ACCOUNTS_PER_PAGE', 10))

# Разрешённые чаты
# ALLOWED_CHATS = []

# Настройки базы данных MySQL
DB_CONFIG = {
    'user': DB_USER,
    'password': DB_PASSWORD,
    'host': DB_HOST,
    'database': DB_NAME
}