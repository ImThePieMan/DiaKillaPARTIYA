from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from user_sessions import create_telegram_client, save_user_session, get_user_sessions_by_admin, restore_sessions
from db import add_admin, is_super_admin, is_admin, save_templates_for_bot, get_templates_by_bot_id, get_db_connection
from db import save_signal_template_for_bot, get_signal_template_by_bot_id, save_signal, get_signal, delete_signal
from config import API_ID, API_HASH, BOT_TOKEN, ACCOUNTS_PER_PAGE #, ALLOWED_CHATS
import asyncio
import re
from telethon.tl.custom import Button
from telethon.tl.types import User
import logging
from telethon.errors.rpcerrorlist import ChatAdminRequiredError
from telethon.tl.types import PeerUser
import mysql.connector
from telethon.errors import SessionPasswordNeededError, AuthKeyUnregisteredError
import handlers
from db import mark_existing_dialogs_as_handled
from telethon.tl.types import InputPeerEmpty
from telethon import functions, types

# Логирование
logging.basicConfig(level=logging.INFO)

# Временное хранилище для логина и установки шаблонов
temp_login_data = {}
# Словарь для отслеживания обрабатываемых диалогов
processing_dialogs = {}
# Хранение текущего индекса сообщений для каждого диалога
dialog_states = {}

# Обработчик команды /help
async def help_command(event):
    """Ответ на команду /help с инструкциями по использованию бота"""
    help_text = (
        "🤖 <b>Гайд по использованию бота!</b>\n\n"
        "<b>Доступные команды:</b>\n"
        "/login - Логин нового юзер-бота. Следуй инструкциям для авторизации юзер-бота.\n"
        "/settemplate - Установить шаблон автоответчика для юзер-бота. Следуй инструкциям для выбора юзер-бота и настройки шаблона.\n"
        "/setsignaltemplate - Установить шаблон сигнала для юзер-бота.\n"
        "/signal - Установить актуальный сигнал.\n"
        "/deletesignal - Удалить актуальный сигнал.\n"
        "/broadcastsignal - Ввести новый сигнал и разослать его ВСЕМ диалогам выбранных юзер-ботов.\n"
        "/help - Получить список доступных команд и инструкцию по использованию бота.\n\n"
        "<b>Примечания:</b>\n"
        "1. После успешного логина юзер-бота автоответчик запускается автоматически.\n"
        "2. Если юзер-бот разлогинился, пока что ты никак нахуй об этом не узнаешь, если автоответчик не работает, то чекай залогиненные устройства, этот бот это что-то вроде asfasasd. Если его нет, значит логай заново /login\n"
        "3. Не забудь после лога установить шаблон, иначе нихуя не будет\n"
        "4. Если шаблон уже был записан для выбранного аккаунта, то он перезапишется, внимательнее."
    )
    
    # Отправляем ответ с инструкциями
    await event.respond(help_text, parse_mode='html')

# Логин нового бота в новом аккаунте
async def login_command(event, bot, api_id, api_hash):
    admin_id = event.sender_id

    if not is_admin(admin_id):
        await event.respond("У вас нет прав администратора.")
        return

    await event.respond("Введите номер телефона для логина:")
    temp_login_data[admin_id] = {'step': 'phone'}

    # Создаем независимый клиент для нового бота
    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.connect()

    # Сохраняем новый клиент в временное хранилище для продолжения логина
    temp_login_data[admin_id]['client'] = client
    await event.respond("Телеграм клиент инициализирован. Ожидается ввод номера телефона.")

# Функция для обработки шагов авторизации
async def handle_login_steps(event, bot):
    admin_id = event.sender_id

    if admin_id not in temp_login_data:
        return  # Игнорируем, если шагов нет

    step = temp_login_data[admin_id].get('step')

    # Ввод номера телефона
    if step == 'phone':
        phone_number = event.raw_text.strip()

        # Проверка корректности номера телефона
        if not phone_number or not phone_number.startswith('+') or not phone_number[1:].isdigit():
            await event.respond("Введите корректный номер телефона в формате +78005553535")
            return
        
        temp_login_data[admin_id]['phone'] = phone_number
        temp_login_data[admin_id]['step'] = 'code'

        # Отправляем код на телефон
        client = temp_login_data[admin_id]['client']

        try:
            await client.send_code_request(phone_number)
            await event.respond(f"Код был отправлен на номер {phone_number}. Введите код.")
            logging.info(f"Код отправлен на номер {phone_number}.")
        except Exception as e:
            await event.respond(f"Ошибка при отправке кода: {str(e)}")
            logging.error(f"Ошибка при отправке кода на номер {phone_number}: {str(e)}")
            del temp_login_data[admin_id]

    # Ввод кода
    elif step == 'code':
        code = event.raw_text.strip()
        client = temp_login_data[admin_id]['client']
        phone_number = temp_login_data[admin_id]['phone']

        try:
            await client.sign_in(phone_number, code)
            if await client.is_user_authorized():
                await event.respond("Авторизация успешна!")
                temp_login_data[admin_id]['step'] = 'description'
                await event.respond("Введите описание для этого юзер-бота:")
            else:
                await event.respond("Ошибка авторизации. Попробуйте снова.")
        except SessionPasswordNeededError:
            await event.respond("Включена двухфакторная аутентификация. Введите пароль:")
            temp_login_data[admin_id]['step'] = 'password'
        except Exception as e:
            await event.respond(f"Ошибка авторизации: {str(e)}")
            logging.error(f"Ошибка авторизации для номера {phone_number}: {str(e)}")
            del temp_login_data[admin_id]

    # Ввод пароля для двухфакторной аутентификации
    elif step == 'password':
        password = event.raw_text.strip()
        client = temp_login_data[admin_id]['client']

        try:
            await client.sign_in(password=password)
            if await client.is_user_authorized():
                await event.respond("Авторизация с паролем успешна! Введите описание для этого юзер-бота (например имя аккаунта или название канала):")
                temp_login_data[admin_id]['step'] = 'description'
            else:
                await event.respond("Ошибка авторизации с паролем. Попробуйте снова.")
        except Exception as e:
            await event.respond(f"Ошибка авторизации с паролем: {str(e)}")
            logging.error(f"Ошибка авторизации с паролем: {str(e)}")
            del temp_login_data[admin_id]

    # Ввод описания юзер-бота
    elif step == 'description':
        description = event.raw_text.strip()
        phone_number = temp_login_data[admin_id]['phone']
        client = temp_login_data[admin_id]['client']

        try:
            # Сохраняем сессию бота и обновляем данные, если сессия уже существует
            user = await client.get_me()
            session_string = StringSession.save(client.session)
            await save_user_session(phone_number, session_string, user.id, admin_id, description)

            await event.respond(f"Сессия для {phone_number} успешно сохранена и обновлена в базе данных.")
            logging.info(f"Сессия для {phone_number} обновлена в базе.")

            # Помечаем все существующие диалоги как обработанные
            dialogs = await client.get_dialogs(limit=None, ignore_migrated=True)
            mark_existing_dialogs_as_handled(user.id, dialogs)
            logging.info(f"Диалоги для бота {user.id} успешно помечены как обработанные.")

            # Добавляем обработчик для нового юзер-бота
            client.add_event_handler(handlers.handle_new_message, events.NewMessage(incoming=True))
            asyncio.create_task(client.run_until_disconnected())  # Запуск клиента в отдельной задаче

            logging.info(f"Автоответчик для {phone_number} успешно запущен.")
            
        except Exception as e:
            await event.respond(f"Ошибка при сохранении сессии: {str(e)}")
            logging.error(f"Ошибка при сохранении сессии для номера {phone_number}: {str(e)}")
        
        del temp_login_data[admin_id]

# Функция для сохранения обработанного диалога
def save_handled_dialog(bot_id, chat_id):
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        cursor.execute(
            "INSERT INTO handled_dialogs (bot_id, chat_id) VALUES (%s, %s)",
            (bot_id, chat_id)
        )
        connection.commit()
        logging.info(f"Диалог с ботом {bot_id} и чатом {chat_id} сохранен.")
    except mysql.connector.IntegrityError:
        logging.warning(f"Диалог с ботом {bot_id} и чатом {chat_id} уже был обработан ранее.")
    except mysql.connector.Error as err:
        logging.error(f"Ошибка при сохранении диалога: {err}")
    finally:
        cursor.close()
        connection.close()

# Функция для проверки, был ли уже обработан диалог
def is_dialog_handled(bot_id, chat_id):
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute(
        "SELECT id FROM handled_dialogs WHERE bot_id = %s AND chat_id = %s",
        (bot_id, chat_id)
    )
    result = cursor.fetchone()
    cursor.close()
    connection.close()
    return result is not None

# Автоответчик на новые сообщения с поддержкой ожидания следующего сообщения при звездочке
async def handle_new_message(event):
    client_user = await event.client.get_me()
    bot_id = client_user.id  # ID юзер-бота
    chat_id = event.chat_id  # ID чата, откуда пришло сообщение

    # Проверяем, является ли это личный чат
    if not event.is_private:
        logging.warning(f"Сообщение не из личного чата, игнорируем. Чат: {chat_id}")
        return

    # Проверяем, обрабатывается ли этот диалог в данный момент
    if processing_dialogs.get((bot_id, chat_id)):
        logging.info(f"Диалог с чатом {chat_id} уже обрабатывается, пропускаем.")
        return

    # if chat_id not in ALLOWED_CHATS:
    #     logging.warning(f"Сообщение не из разрешённого чата, игнорируем. Чат: {chat_id}")
    #     return

    logging.info(f"Юзер-бот {bot_id} получил сообщение в чате {chat_id}")

    # Если диалог уже был обработан и завершен
    if is_dialog_handled(bot_id, chat_id):
        logging.info(f"Диалог с чатом {chat_id} уже был обработан ранее, пропускаем.")
        return

    # Инициализируем состояние диалога, если его нет
    if chat_id not in dialog_states:
        dialog_states[chat_id] = 0  # Начинаем с первого сообщения

    # Индекс текущего сообщения для этого чата
    current_index = dialog_states[chat_id]

    # Добавляем чат в словарь обрабатываемых диалогов
    processing_dialogs[(bot_id, chat_id)] = True

    try:
        # Попытка получить сущность пользователя
        try:
            peer = await event.client.get_entity(chat_id)
        except ValueError:
            logging.warning(f"Не удалось получить сущность для чата {chat_id}. Обновляем список диалогов.")
            try:
                await event.client.get_dialogs()  # Обновляем список диалогов
                peer = await event.client.get_entity(chat_id)  # Пробуем снова получить сущность
            except ValueError:
                logging.error(f"Все еще не удалось получить сущность для чата {chat_id}.")
                processing_dialogs.pop((bot_id, chat_id), None)
                return

        # Получаем шаблоны для бота по его ID
        templates = get_templates_by_bot_id(bot_id)

        # Начинаем последовательное выполнение шаблонов с текущего индекса
        while current_index < len(templates):
            message_text, delay, requires_message = templates[current_index]

            # Имитируем набор текста перед отправкой сообщения
            await event.client(functions.messages.SetTypingRequest(
                peer=peer,
                action=types.SendMessageTypingAction()
            ))

            await asyncio.sleep(delay)

            # Отправляем сообщение
            if current_index == 0:
                await event.reply(message_text)  # Отправляем первое сообщение как ответ
                logging.info(f"Отправлено сообщение: {message_text} (как реплай)")
            else:
                await event.client.send_message(chat_id, message_text)  # Отправляем сообщение без реплая
                logging.info(f"Отправлено сообщение: {message_text}")

            current_index += 1
            dialog_states[chat_id] = current_index  # Обновляем состояние

            # Если требуется ожидание нового сообщения, выходим из цикла и сохраняем текущее состояние
            if requires_message:
                logging.info("Ожидаем нового сообщения для продолжения диалога.")
                processing_dialogs.pop((bot_id, chat_id), None)
                return

        # Проверяем, установлен ли шаблон сигнала для бота
        signal_template = get_signal_template_by_bot_id(bot_id)
        if signal_template is not None and len(signal_template) > 0:
            signal_dict = get_signal()
            if len(signal_dict) == 12:
                desc = ['id', 'admin_id', 'coin', 'direction_text', 'entry_price', 'leverage', 'rm',
                        'target1_price', 'target2_price', 'target3_price',
                        'stop_loss_price', 'liquidation_price']
                signal_dict = {d: signal_dict[i] for i, d in enumerate(desc)}
                logging.info(f'Получен сигнал: {signal_dict}')

                signal_template = signal_template[0][0]                
                message = signal_template.format(
                                    coin=signal_dict['coin'], direction_text=signal_dict['direction_text'],
                                    entry_price=f"{signal_dict['entry_price']}", leverage=signal_dict['leverage'], rm=signal_dict['rm'],
                                    target1_price=f"{signal_dict['target1_price']}",
                                    target2_price=f"{signal_dict['target2_price']}",
                                    target3_price=f"{signal_dict['target3_price']}",
                                    stop_loss_price=f"{signal_dict['stop_loss_price']}",
                                    liquidation_price=f"{signal_dict['liquidation_price']}"
                                )
                await event.client.send_message(chat_id, message)
                logging.info(f"Отправлен шаблон сигнала для бота {bot_id}")

        # Если достигнут конец шаблона, диалог считается завершенным
        # if chat_id not in ALLOWED_CHATS:
        save_handled_dialog(bot_id, chat_id)
        logging.info(f"Диалог с чатом {chat_id} сохранен как обработанный.")
        del dialog_states[chat_id]  # Сброс состояния для завершенного диалога

    except Exception as e:
        logging.error(f"Ошибка при обработке сообщений: {str(e)}")
    finally:
        # Убираем чат из обрабатываемых
        processing_dialogs.pop((bot_id, chat_id), None)


# Регистрация обработчиков команд
def register_handlers(bot):

    @bot.on(events.NewMessage(pattern='/help'))
    async def handle_help(event):
        await help_command(event)

    @bot.on(events.NewMessage(pattern='/login'))
    async def login_handler(event):
        admin_id = event.sender_id
        await login_command(event, bot, API_ID, API_HASH)

    @bot.on(events.NewMessage)
    async def handle_login(event):
        # Добавляем обработку шагов логина
        await handle_login_steps(event, bot)

    # Обработчик команды для установки актуального сигнала
    @bot.on(events.NewMessage(pattern='/signal'))
    async def signal_handler(event):
        sender = await event.get_sender()
        admin_id = event.sender_id

        if not is_admin(admin_id):
            await event.respond("У вас нет прав администратора.")
            return

        if not event.is_private:
            await event.respond("Эта команда должна быть использована в личных сообщениях.")
            return

        async with bot.conversation(sender) as conv:
            try:
                signal_variables = ['coin', 'direction_text', 'entry_price', 'leverage', 'rm',
                                    'target1_price', 'target2_price', 'target3_price', 'stop_loss_price', 'liquidation_price']
                await conv.send_message(
                    "Введите данные для актуального сигнала в формате (значения подставьте свои):\n"
                    "\n"
                    "coin: BTC\n"
                    "direction_text: LONG\n"
                    "entry_price: 0.04383\n"
                    "leverage: 20\n"
                    "rm: 40\n"
                    "target1_price: 0.45666\n"
                    "target2_price: 0.45699\n"
                    "target3_price: 0.46999\n"
                    "stop_loss_price: 0.00999\n"
                    "liquidation_price: 0.00023\n"
                )
                conv_event = await conv.wait_event(events.NewMessage)
                signal = conv_event.raw_text.strip()
                signal_parts = signal.split("\n")
                input_dict = {x.split(':', maxsplit=1)[0]: x.split(':', maxsplit=1)[1].strip() for x in signal_parts}

                # Проверяем корректность заполнения сигнала.
                # Проверяем, прислал ли пользователь ВСЕ переменные, указанные в формате, и не прислал ли он ничего лишнего.
                # Нужно 10 строк, вообще говоря в произвольной последовательности, но с указанием всех переменных из signal_variables
                is_format_wrong = False
                if len(signal_parts) != 10:
                    is_format_wrong = True
                else:
                    if set(input_dict) != set(signal_variables):
                        is_format_wrong = True
                if is_format_wrong:
                    await conv_event.respond("Данные введены в неверном формате!\n"
                                             "Вызовите /signal снова, и попробуйте ещё раз.")
                    return

                # Записываем сигнал в базу.
                logging.info(f"Записываем сигнал в базу:\n{input_dict}")
                signal_saved = save_signal(admin_id, input_dict)
                await conv_event.respond("Сигнал успешно сохранён!" if signal_saved else "Не получилось сохранить сигнал!")
                return

            except Exception as e:
                logging.error(f'Ошибка при установке сигнала в /signal: {str(e)}')
                return

    # Обработчик команды для удаления актуального сигнала
    @bot.on(events.NewMessage(pattern='/deletesignal'))
    async def signal_handler(event):
        admin_id = event.sender_id

        if not is_admin(admin_id):
            await event.respond("У вас нет прав администратора.")
            return

        if not event.is_private:
            await event.respond("Эта команда должна быть использована в личных сообщениях.")
            return

        is_signal_deleted = delete_signal(admin_id)
        await event.respond("Сигнал успешно удалён!" if is_signal_deleted else "Не получилось удалить сигнал!")

    # Обработчик команды для установки шаблона автоответчика с кнопками и пагинацией
    @bot.on(events.NewMessage(pattern='/broadcastsignal'))
    async def broadcast_signal_handler(event):
        sender = await event.get_sender()
        admin_id = event.sender_id
        sessions = get_user_sessions_by_admin(admin_id, need_login_str=True)

        if not is_admin(admin_id):
            await event.respond("У вас нет прав администратора.")
            return

        if not sessions:
            await event.respond("У вас нет авторизованных юзер-ботов.")
            return

        async with bot.conversation(sender) as conv:

            # Get the list of sessions available to the user
            selected_sessions = []

            while True:
                # Update buttons to show selected channels with a check mark
                session_buttons = []
                session_buttons.append([Button.inline("Выбрать все", "choose_all")])
                session_buttons.extend([[Button.inline(text=f"{session[2]}{' ✅' if str(session[2]) in selected_sessions else ''}",
                                                       data=f"session:{session[2]}")]
                                         for session in sessions])
                session_buttons.append([Button.inline("Готово", "done")])
                session_buttons.append([Button.inline("Отмена", b"cancel")])
                msg = await conv.send_message("Выберите ботов для отправки сигнала:", buttons=session_buttons)

                conv_event = await conv.wait_event(events.CallbackQuery)
                data = conv_event.data.decode('utf-8')
                await conv_event.answer()

                if data == 'choose_all':
                    for session in sessions:
                        selected_sessions.append(session[2])
                    await msg.delete()

                if data == 'done':
                    await msg.delete()
                    break

                if data == 'cancel':
                    await conv.send_message("Команда отменена.")
                    return

                if data.startswith('session:'):
                    session_desc = data.split(':')[1]
                    if session_desc in selected_sessions:
                        selected_sessions.remove(session_desc)
                    else:
                        selected_sessions.append(session_desc)
                    await msg.delete()

            if not selected_sessions:
                await conv.send_message("Отправка сигнала отменена. Вы не выбрали ни одного канала.")
                return

            ####
            ## Запрашиваем сообщение с сигналом и проверяем его формат
            ####
            await conv.send_message("Введите данные сигнала для броадкастинга в формате (значения подставьте свои):\n"
                                    "\n"
                                    "coin: BTC\n"
                                    "direction_text: LONG\n"
                                    "entry_price: 0.04383\n"
                                    "leverage: 20\n"
                                    "rm: 40\n"
                                    "target1_price: 0.45666\n"
                                    "target2_price: 0.45699\n"
                                    "target3_price: 0.46999\n"
                                    "stop_loss_price: 0.00999\n"
                                    "liquidation_price: 0.00023\n")

            signal = (await conv.get_response()).text
            signal_parts = signal.split("\n")
            signal_dict = {x.split(':', maxsplit=1)[0]: x.split(':', maxsplit=1)[1].strip() for x in signal_parts}

            # Проверяем корректность заполнения сигнала.
            # Проверяем, прислал ли пользователь ВСЕ переменные, указанные в формате, и не прислал ли он ничего лишнего.
            signal_variables = ['coin', 'direction_text', 'entry_price', 'leverage', 'rm',
                                'target1_price', 'target2_price', 'target3_price', 'stop_loss_price', 'liquidation_price']
            is_format_wrong = False
            if len(signal_parts) != 10:
                is_format_wrong = True
            else:
                if set(signal_dict) != set(signal_variables):
                    is_format_wrong = True
            if is_format_wrong:
                await conv_event.respond("Данные введены в неверном формате!\n"
                                         "Вызовите /signal снова, и попробуйте ещё раз.")
                return

            ####
            ## Рассылка по выбранным сессиям
            ####
            selected_sessions = [s for s in sessions if s[2] in selected_sessions]
            logging.info(f'Выбранные сессии: {selected_sessions}')

            for session in selected_sessions:
                try:
                    bot_id = session[3]
                    client = TelegramClient(StringSession(session[1]), API_ID, API_HASH)
                    await client.connect()
                    dialogs = await client.get_dialogs()
                    for dialog in dialogs:
                        chat_id = dialog.id
                        chat_type = dialog.entity
                        # Пропускаем группы и каналы в диалогах, спамим только в лички.
                        if type(chat_type) is not User:
                            continue
                        # if chat_id in ALLOWED_CHATS:  
                        signal_template = get_signal_template_by_bot_id(bot_id)
                        if len(signal_template) > 0:
                            signal_template = signal_template[0][0]
                            message = signal_template.format(coin=signal_dict['coin'], direction_text=signal_dict['direction_text'],
                                                            entry_price=f"{signal_dict['entry_price']}", leverage=signal_dict['leverage'], rm=signal_dict['rm'],
                                                            target1_price=f"{signal_dict['target1_price']}",
                                                            target2_price=f"{signal_dict['target2_price']}",
                                                            target3_price=f"{signal_dict['target3_price']}",
                                                            stop_loss_price=f"{signal_dict['stop_loss_price']}",
                                                            liquidation_price=f"{signal_dict['liquidation_price']}")
                            await client.send_message(chat_id, message)
                            logging.info(f'Броадкаст для бота {bot_id} в диалог {chat_id}')
                    client.add_event_handler(handlers.handle_new_message, events.NewMessage(incoming=True))
                    asyncio.create_task(client.run_until_disconnected())
                except Exception as e:
                    logging.error(f'Что-то пошло не так при броадкасте для сессии {session[2]}. Ошибка: {str(e)}')

    # Обработчик команды для установки шаблона автоответчика с кнопками и пагинацией
    @bot.on(events.NewMessage(pattern='/settemplate'))
    async def set_template_handler(event):
        admin_id = event.sender_id
        sessions = get_user_sessions_by_admin(admin_id)

        if not sessions:
            await event.respond("У вас нет авторизованных юзер-ботов.")
            return

        # Показать первую страницу
        await show_bot_page(event, sessions, page=0, template_type='select_bot')

    # Обработчик команды для установки шаблона сигнала автоответчика с кнопками и пагинацией
    @bot.on(events.NewMessage(pattern='/setsignaltemplate'))
    async def set_signal_template_handler(event):
        admin_id = event.sender_id
        sessions = get_user_sessions_by_admin(admin_id)

        if not sessions:
            await event.respond("У вас нет авторизованных юзер-ботов.")
            return

        # Показать первую страницу
        await show_bot_page(event, sessions, page=0, template_type='select_bot_signal')

    async def show_bot_page(event, sessions, page, template_type):
        # Рассчитываем индексы начального и конечного аккаунта на текущей странице
        start = page * ACCOUNTS_PER_PAGE
        end = start + ACCOUNTS_PER_PAGE
        page_sessions = sessions[start:end]

        # Создаем кнопки для текущей страницы аккаунтов
        buttons = [
            [Button.inline(f"{bot_label.strip()} ({phone_number.strip()})", data=f"{template_type}:{user_id}")]
            for phone_number, bot_label, user_id in page_sessions
        ]

        # Добавляем кнопки пагинации, если аккаунты на нескольких страницах
        pagination_buttons = []
        if page > 0:
            pagination_buttons.append(Button.inline("⬅️ Предыдущая", data=f"prev_page:{page - 1}:{template_type}"))
        if end < len(sessions):
            pagination_buttons.append(Button.inline("Следующая ➡️", data=f"next_page:{page + 1}:{template_type}"))

        if pagination_buttons:
            buttons.append(pagination_buttons)

        # Отправляем сообщение с кнопками или обновляем, если оно уже есть
        await event.respond("Выберите бота для установки шаблона:", buttons=buttons)

    # Обработчик для нажатий на кнопки пагинации
    @bot.on(events.CallbackQuery(pattern=r'prev_page|next_page'))
    async def handle_pagination(event):
        _, page, template_type = event.data.decode('utf-8').split(':')
        page = int(page)

        # Получаем все сессии для администратора
        admin_id = event.sender_id
        sessions = get_user_sessions_by_admin(admin_id)

        # Переходим к нужной странице
        await show_bot_page(event, sessions, page, template_type)

    # Обработчик нажатий на кнопки выбора бота
    @bot.on(events.CallbackQuery(pattern=b'select_bot:'))
    async def select_bot_callback(event):
        admin_id = event.sender_id
        data = event.data.decode('utf-8')
        bot_id = int(data.split(":")[1])

        # Получаем бота по ID
        sessions = get_user_sessions_by_admin(admin_id)
        bot_label = next((bot_label for pn, bot_label, uid in sessions if uid == bot_id), None)

        if bot_label:
            # Сохраняем выбранного бота в хранилище
            temp_login_data[admin_id] = {
                'selected_bot': bot_label,
                'bot_id': bot_id,
                'step': 'template'
            }
            # Предлагаем ввести шаблон для автоответов с моноширинным шрифтом
            await event.edit(
                f"Вы выбрали бота: {bot_label}. Введите шаблон сообщений в формате:\n"
                "\n"
                "[сообщение1]{задержка в секундах}\n"
                "[сообщение2]{задержка в секундах}*\n"
                "[сообщение3]{задержка в секундах}\n"
                "\n"
                "Знак * означает, что после сообщения 2 бот ждет ответа, прежде чем продолжить. "
                "Звездочек в шаблоне может быть несколько."
            )
        else:
            await event.edit("Ошибка выбора бота, попробуйте еще раз.")

    # Обработчик нажатий на кнопки выбора бота
    @bot.on(events.CallbackQuery(pattern=b'select_bot_signal:'))
    async def select_bot_signal_callback(event):
        admin_id = event.sender_id
        data = event.data.decode('utf-8')
        bot_id = int(data.split(":")[1])

        # Получаем бота по ID
        sessions = get_user_sessions_by_admin(admin_id)
        bot_label = next((bot_label for pn, bot_label, uid in sessions if uid == bot_id), None)

        if bot_label:
            # Сохраняем выбранного бота в хранилище
            temp_login_data[admin_id] = {
                'selected_bot': bot_label,
                'bot_id': bot_id,
                'step': 'template_signal'
            }
            # Предлагаем ввести шаблон для автоответов с моноширинным шрифтом
            await event.edit(
                f"Вы выбрали бота: {bot_label}. Введите шаблон сигнала:\n"
                "\n"
                "Доступные переменные:\n"
                "\n"
                "{coin} - Название монеты (рекомендуется дописывать USDT для пары)\n"
                "{direction_text} - Направление сигнала\n"
                "{entry_price} - Цена входа\n"
                "{leverage} - Плечо (Рекомендуется спереди поставить x)\n"
                "{rm} - Риск менеджмент (после пишется например % от депозита)\n"
                "{target1_price} - Цена первой цели\n"
                "{target2_price} - Цена второй цели\n"
                "{target3_price} - Цена третьей цели\n"
                "{stop_loss_price} - Цена стоп-лосса\n"
                "{liquidation_price} - Цена ликвидации\n"
                "\n"
            )
        else:
            await event.edit("Ошибка выбора бота, попробуйте еще раз.")

    # Обработчик команды для ввода шаблона с поддержкой звездочки
    @bot.on(events.NewMessage)
    async def template_input_handler(event):
        admin_id = event.sender_id

        if admin_id in temp_login_data and temp_login_data[admin_id]['step'] == 'template':
            template_text = event.raw_text.strip()
            bot_id = temp_login_data[admin_id]['bot_id']

            # Регулярное выражение для парсинга шаблона с поддержкой звездочки
            pattern = re.compile(r'\[(.*?)\]\{(\d+)\}(\*)?')
            matches = pattern.findall(template_text)

            if not matches:
                await event.respond("Шаблон введён в неверном формате. Попробуйте еще раз.")
                return

            # Формируем список шаблонов с учетом параметра requires_message
            templates = [
                (message_text.strip(), int(delay), bool(star))
                for message_text, delay, star in matches
            ]

            try:
                # Сохраняем новые шаблоны
                save_templates_for_bot(admin_id, bot_id, templates)

                # Уведомляем пользователя об успешном сохранении
                selected_bot = temp_login_data[admin_id]['selected_bot']
                await event.respond(f"Шаблон для бота '{selected_bot}' успешно сохранен!")
                
                # Завершаем процесс и удаляем временные данные
                del temp_login_data[admin_id]

            except Exception as e:
                logging.error(f"Ошибка при сохранении шаблона для бота {bot_id}: {e}")
                await event.respond("Произошла ошибка при сохранении шаблона. Попробуйте еще раз.")
    
    # Обработчик команды для ввода шаблона сигнала
    @bot.on(events.NewMessage)
    async def template_signal_input_handler(event):
        admin_id = event.sender_id

        if admin_id in temp_login_data and temp_login_data[admin_id]['step'] == 'template_signal':
            template_text = event.raw_text.strip()
            bot_id = temp_login_data[admin_id]['bot_id']

            try:
                # Сохраняем новый шаблон
                save_signal_template_for_bot(bot_id, template_text)

                # Уведомляем пользователя об успешном сохранении
                selected_bot = temp_login_data[admin_id]['selected_bot']
                await event.respond(f"Шаблон сигнала для бота '{selected_bot}' успешно сохранен!")
                
                # Завершаем процесс и удаляем временные данные
                del temp_login_data[admin_id]

            except Exception as e:
                logging.error(f"Ошибка при сохранении шаблона сигнала для бота {bot_id}: {e}")
                await event.respond("Произошла ошибка при сохранении шаблона сигнала. Попробуйте еще раз.")