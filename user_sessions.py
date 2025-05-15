import mysql.connector
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from db import get_db_connection, get_user_sessions_by_admin
from config import API_ID, API_HASH, SUPER_ADMIN_ID
from telethon.errors import UserDeactivatedBanError, AuthKeyUnregisteredError
from telethon.errors.rpcerrorlist import AuthKeyUnregisteredError
import logging
import asyncio
import handlers
from db import mark_existing_dialogs_as_handled

# Сохранение сессии юзер-бота
async def save_user_session(phone_number, session_string, user_id, admin_id, description):
    """Сохраняем или обновляем сессию юзер-бота в базе данных с описанием"""
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        cursor.execute("SELECT id FROM user_sessions WHERE phone_number = %s", (phone_number,))
        result = cursor.fetchone()

        if result:
            cursor.execute(
                "UPDATE user_sessions SET session_file_path = %s, user_id = %s, admin_id = %s, description = %s "
                "WHERE phone_number = %s",
                (session_string, user_id, admin_id, description, phone_number)
            )
            logging.info(f"Сессия для {phone_number} обновлена в базе данных.")
        else:
            cursor.execute(
                "INSERT INTO user_sessions (phone_number, session_file_path, user_id, admin_id, description) "
                "VALUES (%s, %s, %s, %s, %s)",
                (phone_number, session_string, user_id, admin_id, description)
            )
            logging.info(f"Сессия для {phone_number} успешно сохранена в базе данных.")
        
        connection.commit()

    except mysql.connector.Error as err:
        logging.error(f"Ошибка при сохранении сессии для номера {phone_number}: {err}")
    finally:
        cursor.close()
        connection.close()

# Функция для отправки уведомления администратору
async def send_admin_notification(bot, admin_id, description):
    """Отправляем уведомление администратору о разлоге юзер-бота"""
    message = f"Аккаунт с описанием '{description}' разлогинился. Пожалуйста, залогиньте его снова с помощью команды /login."
    try:
        # Убедитесь, что admin_id — это integer, а не строка
        admin_id = int(admin_id)
        await bot.send_message(admin_id, message)  # Отправляем уведомление админу через классического бота
        logging.info(f"Уведомление админу {admin_id} отправлено: {message}")
    except Exception as e:
        logging.error(f"Ошибка при отправке уведомления админу {admin_id}: {str(e)}")

# Создание клиента Telegram
def create_telegram_client(api_id, api_hash, session_string=None):
    if session_string:
        client = TelegramClient(StringSession(session_string), api_id, api_hash)
    else:
        client = TelegramClient('anon', api_id, api_hash)
    return client

# Функция для удаления сессии из базы данных при разлоге
def delete_user_session(phone_number):
    """Удаляем сессию юзер-бота из базы данных при разлоге"""
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        cursor.execute("DELETE FROM user_sessions WHERE phone_number = %s", (phone_number,))
        connection.commit()
        logging.info(f"Сессия для {phone_number} удалена из базы данных.")
    except mysql.connector.Error as err:
        logging.error(f"Ошибка при удалении сессии для номера {phone_number}: {err}")
    finally:
        cursor.close()
        connection.close()

# Функция для мониторинга авторизации юзер-бота
async def monitor_user_bot(client, bot, description, phone_number):
    """Мониторинг авторизации юзер-бота и отправка уведомления при разлоге"""
    while True:
        try:
            # Проверяем авторизован ли бот
            if not await client.is_user_authorized():
                logging.info(f"Аккаунт {phone_number} разлогинился.")
                await send_admin_notification(bot, SUPER_ADMIN_ID, description)
                delete_user_session(phone_number)  # Удаляем сессию из базы данных
                break  # Останавливаем мониторинг этого бота
        except Exception as e:
            logging.error(f"Ошибка при проверке авторизации для {phone_number}: {e}")

        await asyncio.sleep(60)  # Проверяем каждые 60 секунд

# Восстановление сессий юзер-ботов
async def restore_sessions(bot):
    """Восстанавливаем сессии всех юзер-ботов из базы данных и помечаем существующие диалоги как обработанные"""
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("SELECT phone_number, session_file_path, description FROM user_sessions")
    sessions = cursor.fetchall()

    user_bots = []  # Список подключённых юзер-ботов

    for phone_number, session_string, description in sessions:
        if session_string:
            client = TelegramClient(StringSession(session_string), API_ID, API_HASH)

            try:
                await client.connect()

                if not await client.is_user_authorized():
                    logging.warning(f"Сессия для {phone_number} не авторизована.")
                    raise AuthKeyUnregisteredError("Ошибка авторизации")

                logging.info(f"Сессия для {phone_number} восстановлена!")
                user_bots.append(client)

                # Получаем все существующие диалоги и сохраняем их как обработанные
                dialogs = await client.get_dialogs()
                user = await client.get_me()
                mark_existing_dialogs_as_handled(user.id, dialogs)

                # Добавляем событие на попытку переподключения
                @client.on(events.Disconnected)
                async def handle_disconnect(event):
                    """Обработка отключения клиента"""
                    logging.info(f"Аккаунт с номером {phone_number} отключился.")
                    await send_admin_notification(bot, SUPER_ADMIN_ID, description)

                # Добавляем событие на разлогин
                @client.on(events.Raw)
                async def handle_raw_update(event):
                    try:
                        pass
                    except AuthKeyUnregisteredError:
                        logging.error(f"Аккаунт с номером {phone_number} разлогинился.")
                        await send_admin_notification(bot, SUPER_ADMIN_ID, description)
                        await client.disconnect()

                client.add_event_handler(handlers.handle_new_message, events.NewMessage(incoming=True))
                asyncio.create_task(client.run_until_disconnected())

            except (AuthKeyUnregisteredError, UserDeactivatedBanError) as e:
                logging.error(f"Ошибка при авторизации бота для {phone_number}: {e}")
                await send_admin_notification(bot, SUPER_ADMIN_ID, description)
            except Exception as e:
                logging.error(f"Ошибка при авторизации бота для {phone_number}: {str(e)}")

    cursor.close()
    connection.close()

    return user_bots