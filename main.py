from telethon import TelegramClient, events
from config import API_ID, API_HASH, BOT_TOKEN
import handlers
from user_sessions import restore_sessions
import asyncio
import logging

logging.basicConfig(level=logging.INFO)

# Инициализация классического бота
bot = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# Функция для запуска юзер-ботов
async def start_user_bots():
    # Восстанавливаем сессии и помечаем существующие диалоги как обработанные
    sessions = await restore_sessions(bot)  # Передаём классического бота для уведомлений
    for client in sessions:
        if client is not None:
            client.add_event_handler(handlers.handle_new_message, events.NewMessage(incoming=True))
            asyncio.create_task(client.run_until_disconnected())  # Запуск каждого клиента в отдельной задаче

# Запуск основного бота и юзер-ботов
async def startup():
    logging.info("Запуск сессий юзер-ботов.")
    await start_user_bots()

# Передаём объект bot в функцию register_handlers для регистрации обработчиков команд классического бота
handlers.register_handlers(bot)

# Запускаем бота
if __name__ == "__main__":
    loop = asyncio.get_event_loop()  # Получаем текущий цикл событий
    loop.run_until_complete(startup())  # Запуск юзер-ботов и выполнение других задач
    bot.run_until_disconnected()  # Запуск классического бота