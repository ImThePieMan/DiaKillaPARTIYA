import mysql.connector
from config import DB_CONFIG, SUPER_ADMIN_ID  # , ALLOWED_CHATS 
import handlers
import logging

def get_db_connection():
    connection = mysql.connector.connect(**DB_CONFIG)
    return connection

def mark_existing_dialogs_as_handled(bot_id, dialogs):
    """Сохраняем все диалоги юзер-бота как обработанные в базе данных"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        for dialog in dialogs:
            chat_id = dialog.id
            # if chat_id in ALLOWED_CHATS:
            #     continue
            cursor.execute(
                "INSERT INTO handled_dialogs (bot_id, chat_id) VALUES (%s, %s) "
                "ON DUPLICATE KEY UPDATE bot_id = bot_id",
                (bot_id, chat_id)
            )
        connection.commit()
        logging.info(f"Диалоги для бота {bot_id} успешно помечены как обработанные.")
    except mysql.connector.Error as e:
        logging.error(f"Ошибка при сохранении диалогов для бота {bot_id}: {e}")
    finally:
        cursor.close()
        connection.close()

# Добавление нового админа с описанием
def add_admin(admin_id, description=None):
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        cursor.execute("INSERT INTO admins (admin_id, description) VALUES (%s, %s)", (admin_id, description))
        connection.commit()
    except mysql.connector.IntegrityError:
        print("Админ с таким admin_id уже существует")
    cursor.close()
    connection.close()

# Проверка, является ли пользователь админом
def is_admin(admin_id):
    if not is_super_admin(admin_id):
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM admins WHERE admin_id = %s", (admin_id,))
        result = cursor.fetchone()
        cursor.close()
        connection.close()
        return result is not None
    else:
        return True

# Проверка, является ли пользователь супер-админом
def is_super_admin(admin_id):
    return admin_id == SUPER_ADMIN_ID

# Обновленная функция сохранения шаблона в базе данных с поддержкой requires_message
def save_templates_for_bot(admin_id, bot_id, templates):
    """
    Сохраняем новый набор шаблонов автоответчика для конкретного юзер-бота и администратора.
    Перед этим удаляем старые шаблоны.

    templates - список кортежей (message_text, delay_seconds, requires_message)
    """
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Удаляем старые шаблоны для указанного бота и администратора
        cursor.execute("DELETE FROM message_templates WHERE bot_id = %s", (bot_id,))
        connection.commit()

        # Добавляем новые шаблоны
        for message_text, delay_seconds, requires_message in templates:
            cursor.execute(
                "INSERT INTO message_templates (user_id, bot_id, message_text, delay_seconds, requires_message) "
                "VALUES (%s, %s, %s, %s, %s)",
                (admin_id, bot_id, message_text, delay_seconds, requires_message)
            )
        connection.commit()
    except mysql.connector.Error as err:
        logging.error(f"Ошибка при сохранении шаблонов для бота {bot_id}: {err}")
    finally:
        cursor.close()
        connection.close()

# Обновленная функция сохранения шаблона сигнала в базе данных
def save_signal_template_for_bot(bot_id, message_text):
    """
    Сохраняем новый шаблон сигнала для конкретного юзер-бота.
    Перед этим удаляем старый шаблон.
    """
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Удаляем старый шаблон для указанного бота
        cursor.execute("DELETE FROM signal_templates WHERE bot_id = %s", (bot_id,))
        connection.commit()

        # Добавляем новый шаблон
        cursor.execute(
            "INSERT INTO signal_templates (bot_id, template) "
            "VALUES (%s, %s)",
            (bot_id, message_text)
        )
        connection.commit()
    except mysql.connector.Error as err:
        logging.error(f"Ошибка при сохранении шаблонов для бота {bot_id}: {err}")
    finally:
        cursor.close()
        connection.close()

# Функция для получения шаблонов по bot_id с учетом requires_message
def get_templates_by_bot_id(bot_id):
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        # Извлекаем все поля, включая requires_message
        cursor.execute(
            "SELECT message_text, delay_seconds, requires_message FROM message_templates WHERE bot_id = %s",
            (bot_id,)
        )
        templates = cursor.fetchall()
        return templates  # Возвращаем все поля для обработки
    except mysql.connector.Error as err:
        logging.error(f"Ошибка при получении шаблонов для бота {bot_id}: {err}")
        return []
    finally:
        cursor.close()
        connection.close()

# Функция для получения шаблонов по bot_id
def get_signal_template_by_bot_id(bot_id):
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        # Извлекаем template
        cursor.execute(
            "SELECT template FROM signal_templates WHERE bot_id = %s",
            (bot_id,)
        )
        template = cursor.fetchall()
        return template
    except mysql.connector.Error as err:
        logging.error(f"Ошибка при получении шаблона сигнала для бота {bot_id}: {err}")
        return []
    finally:
        cursor.close()
        connection.close()

# Сохранение сессии юзер-бота с описанием
def save_user_session(phone_number, session_string, user_id, admin_id, description):
    """Сохраняем сессию юзер-бота в базу данных с описанием"""
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        cursor.execute(
            "INSERT INTO user_sessions (phone_number, session_file_path, user_id, admin_id, description) "
            "VALUES (%s, %s, %s, %s, %s)",
            (phone_number, session_string, user_id, admin_id, description)
        )
        connection.commit()
    except mysql.connector.Error as err:
        print(f"Ошибка при сохранении сессии: {err}")
    cursor.close()
    connection.close()

# Получение списка сессий юзер-ботов для администратора
def get_user_sessions_by_admin(admin_id, need_login_str=False):
    """Получаем список сессий юзер-ботов, привязанных к администратору"""
    connection = get_db_connection()
    cursor = connection.cursor()
    if not need_login_str:
        query = "SELECT phone_number, description, user_id FROM user_sessions WHERE admin_id = %s"
    else:
        query = "SELECT phone_number, session_file_path, description, user_id FROM user_sessions WHERE admin_id = %s"
    cursor.execute(query, (admin_id,))
    sessions = cursor.fetchall()
    cursor.close()
    connection.close()
    return sessions

# Получение сессии юзер-бота по номеру телефона
def get_user_session(phone_number):
    """Получаем сессию юзер-бота по номеру телефона"""
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute(
        "SELECT session_file_path FROM user_sessions WHERE phone_number = %s",
        (phone_number,)
    )
    session_string = cursor.fetchone()
    cursor.close()
    connection.close()
    return session_string[0] if session_string else None

# Сохранение актуального сигнала
def save_signal(admin_id, signal: dict) -> int:
    query = (
        "INSERT INTO current_signals (admin_id, coin, direction_text, entry_price, leverage, rm, "
        "target1_price, target2_price, target3_price, stop_loss_price, liquidation_price) VALUES "
        "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
    )
    values = (
        int(admin_id),
        str(signal['coin']), str(signal['direction_text']),
        str(signal['entry_price']), str(signal['leverage']), str(signal['rm']),
        str(signal['target1_price']),
        str(signal['target2_price']),
        str(signal['target3_price']),
        str(signal['stop_loss_price']),
        str(signal['liquidation_price'])
    )

    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("DELETE FROM current_signals")
        connection.commit()
        cursor.execute(query, values)
        connection.commit()
        return True
    except mysql.connector.Error as err:
        logging.error(f"Ошибка при сохранении сигнала: {err}")
        return False
    finally:
        cursor.close()
        connection.close()

# Получение актуального сигнала
def get_signal() -> dict:
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM current_signals")
        signal_dict = cursor.fetchone()
        return signal_dict
    except mysql.connector.Error as err:
        logging.error(f"Ошибка при получении сигнала: {err}")
    finally:
        cursor.close()
        connection.close()

# Удаление актуального сигнала
def delete_signal(admin_id) -> dict:
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("DELETE FROM current_signals")
        connection.commit()
        return True
    except mysql.connector.Error as err:
        logging.error(f"Ошибка при удалении сигнала: {err}")
        return False
    finally:
        cursor.close()
        connection.close()
