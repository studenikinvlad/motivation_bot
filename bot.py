import logging
import asyncio
from telegram.error import BadRequest
from datetime import datetime, timedelta
from telegram_bot_calendar import DetailedTelegramCalendar, LSTEP
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    CallbackContext,
    CallbackQueryHandler
)
from db import db
from config import BOT_TOKEN, ADMINS, ADMIN_INFO, USM_SCORES, CONSULTANT_SCORES, price_text, rules_text, SUPERADMINS
from calendar import monthrange, month_name
import locale
# Состояния ConversationHandler
(
    MAIN_MENU, CHOOSE_ACTION, ENTER_DESCRIPTION, SELECT_USER,
    SELECT_REASON, CONFIRM_POINTS, SELECT_EMPLOYEE_FOR_HISTORY, SELECT_ACTION,
    ENTER_CUSTOM_POINTS, ENTER_DEDUCT_POINTS, REGISTRATION_FIO, REGISTRATION_ROLE, EDIT_TEXT_INPUT,
    SELECT_USAGE_TYPE, SELECT_DATE, CONFIRM_REQUEST   # Добавленные состояния
) = range(16)

locale.setlocale(locale.LC_TIME, 'ru_RU.UTF-8')

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def ensure_registered(update: Update) -> bool:
    """Проверка регистрации пользователя."""
    user_id = update.effective_user.id
    if user_id in ADMINS or user_id in SUPERADMINS:
        return True
    if not await db.get_user(user_id):
        await update.message.reply_text("Вы не зарегистрированы. Напишите /start.")
        return False
    return True

async def start(update: Update, context: CallbackContext):
    """Обработчик команды /start."""
    user_id = update.effective_user.id
    
    if user_id in ADMINS or user_id in SUPERADMINS:
        await show_main_menu(update)
        return MAIN_MENU

    user = await db.get_user(user_id)
    if user is None:
        await update.message.reply_text(
            "Добро пожаловать! Пожалуйста, введите ваше ФИО для регистрации:"
        )
        return REGISTRATION_FIO
    else:
        await show_main_menu(update)
        return MAIN_MENU

async def show_main_menu(update: Update):
    """Отображение главного меню."""
    user_id = update.effective_user.id
    if user_id in ADMINS:
        buttons = [
            [KeyboardButton("Начислить/Списать баллы")],
            [KeyboardButton("Очередь использования баллов")],
            [KeyboardButton("Проверка заявок на использование")],
            [KeyboardButton("История сотрудника")],
            [KeyboardButton("Сотрудники")],
            [KeyboardButton("Изменения")],
        ]
    elif user_id in SUPERADMINS:
        buttons = [
            [KeyboardButton("Начислить/Списать баллы")],
            [KeyboardButton("Начислить/Списать баллы (silent)")],
            [KeyboardButton("Очередь использования баллов")],
            [KeyboardButton("Проверка заявок на использование")],
            [KeyboardButton("История сотрудника")],
            [KeyboardButton("Сотрудники")],
            [KeyboardButton("Изменения")],
        ]
    else:
        buttons = [
            [KeyboardButton("Мой баланс")],
            [KeyboardButton("История")],
            [KeyboardButton("Использовать баллы")],
            [KeyboardButton("Сотрудники")],
            [KeyboardButton("Прайс-лист")],
            [KeyboardButton("Правила")],
        ]
    markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    await update.message.reply_text("Выберите действие:", reply_markup=markup)

async def send_price(update: Update, context: CallbackContext):
    """Отправка прайс-листа."""
    await update.message.reply_text(price_text)

async def send_rules(update: Update, context: CallbackContext):
    """Отправка правил."""
    await update.message.reply_text(rules_text)

async def registration_fio(update: Update, context: CallbackContext):
    """Регистрация ФИО пользователя."""
    fio = update.message.text.strip()
    if not fio:
        await update.message.reply_text("ФИО не может быть пустым. Введите снова:")
        return REGISTRATION_FIO
    context.user_data['fio'] = fio
    buttons = [[KeyboardButton("Консультант")], [KeyboardButton("УСМ")]]
    markup = ReplyKeyboardMarkup(buttons, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Выберите вашу роль:", reply_markup=markup)
    return REGISTRATION_ROLE

async def registration_role(update: Update, context: CallbackContext):
    """Регистрация роли пользователя."""
    role = update.message.text.strip()
    if role not in ["Консультант", "УСМ"]:
        await update.message.reply_text("Пожалуйста, выберите роль из кнопок.")
        return REGISTRATION_ROLE
    fio = context.user_data['fio']
    user_id = update.effective_user.id
    await db.add_user(user_id, fio, role)
    await update.message.reply_text(f"Регистрация завершена! Добро пожаловать, {fio} ({role}) 🎉")
    await show_main_menu(update)
    return MAIN_MENU


#------------------------------SUPERADMIN---------------------------------#


#-------------------------------------------------------------------------#

async def show_admin_changes_menu(update: Update, context: CallbackContext):
    """Меню изменений для администратора."""
    buttons = [
        [KeyboardButton("Удаление сотрудника")],
        [KeyboardButton("Изменить правила")],
        [KeyboardButton("Изменить прайс-лист")],
        [KeyboardButton("Назад")],
    ]
    markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text("Меню изменений:", reply_markup=markup)

async def edit_rules(update: Update, context: CallbackContext):
    """Редактирование правил."""
    context.user_data['edit_mode'] = 'rules'
    await update.message.reply_text("Введите новый текст правил:")
    return EDIT_TEXT_INPUT

async def edit_price(update: Update, context: CallbackContext):
    """Редактирование прайс-листа."""
    context.user_data['edit_mode'] = 'price'
    await update.message.reply_text("Введите новый прайс-лист:")
    return EDIT_TEXT_INPUT

async def edit_text_input(update: Update, context: CallbackContext):
    """Сохранение изменений текста."""
    mode = context.user_data.get('edit_mode')
    new_text = update.message.text.strip()

    if mode == 'rules':
        global rules_text
        rules_text = new_text
        await update.message.reply_text("✅ Правила обновлены.")
    elif mode == 'price':
        global price_text
        price_text = new_text
        await update.message.reply_text("✅ Прайс-лист обновлён.")
    else:
        await update.message.reply_text("⚠️ Неизвестный режим редактирования.")

    context.user_data['edit_mode'] = None
    await show_main_menu(update)
    return MAIN_MENU

async def show_employees_for_admin(update, context):
    """Показать список сотрудников для админа."""
    users = await db.get_all_users()
    keyboard = []
    for user in users:
        text = f"{user[1]} ({user[2]})"
        callback_data = f"delete_user_{user[0]}"
        keyboard.append([
            InlineKeyboardButton(text=text, callback_data="noop"),
            InlineKeyboardButton(text="Удалить", callback_data=callback_data)
        ])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Список сотрудников:", reply_markup=reply_markup)

async def handle_delete_user(update, context):
    """Обработка удаления пользователя."""
    query = update.callback_query
    await query.answer()

    if query.from_user.id not in ADMINS and query.from_user.id not in SUPERADMINS:
        await query.edit_message_text("⛔️ У вас нет прав для удаления сотрудников.")
        return
    
    user_id = int(query.data.split("_")[-1])
    await db.delete_user(user_id)
    await query.edit_message_text(f"Сотрудник с ID {user_id} удалён.")
    await show_employees_for_admin(update, context)

async def choose_role(update: Update, context: CallbackContext):
    """Выбор роли для отображения сотрудников."""
    keyboard = [
        [
            InlineKeyboardButton("УСМ", callback_data="role_УСМ"),
            InlineKeyboardButton("Консультант", callback_data="role_Консультант"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите роль для отображения:", reply_markup=reply_markup)

async def show_employees_by_role(update: Update, context: CallbackContext):
    """Показать сотрудников по выбранной роли."""
    query = update.callback_query
    await query.answer()

    role = query.data.split("_")[1]
    users = await db.get_all_users()
    filtered = [u for u in users if u[2] == role]

    if not filtered:
        await query.edit_message_text(f"Сотрудники с ролью {role} не найдены.")
        return

    msg = f"Сотрудники с ролью {role}:\n\n"
    for user in filtered:
        msg += f"{user[1]} — Баллы: {user[3]}\n"

    await query.edit_message_text(msg)

async def notify_user_points_change(context: CallbackContext, user_id: int, points: int, reason: str):
    """Уведомление пользователя об изменении баллов."""
    user = await db.get_user(user_id)
    if not user:
        return
    sign = '+' if points > 0 else ''
    text = (
        f"{user[1]}, вам {'начислено' if points > 0 else 'списано'} {sign}{points} баллов за: {reason}.\n"
        f"Текущий баланс: {user[3]} баллов."
    )
    try:
        await context.bot.send_message(chat_id=user_id, text=text)
    except Exception as e:
        logger.error(f"Не удалось отправить уведомление пользователю {user_id}: {e}")

async def begin_employee_history(update: Update, context: CallbackContext):
    """Начало просмотра истории сотрудника."""
    users = await db.get_all_users()
    buttons = [[KeyboardButton(f"{u[1]} ({u[0]})")] for u in users]
    markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text("Выберите сотрудника для просмотра истории:", reply_markup=markup)
    return SELECT_EMPLOYEE_FOR_HISTORY

async def show_employee_history(update: Update, context: CallbackContext):
    selected = update.message.text
    try:
        fio, uid = selected.rsplit('(', 1)
        user_id = int(uid[:-1])
    except Exception:
        await update.message.reply_text("Неверный формат. Попробуйте снова.")
        return SELECT_EMPLOYEE_FOR_HISTORY

    history = await db.get_employee_history(user_id)
    user = await db.get_user(user_id)
    if not user:
        await update.message.reply_text("Сотрудник не найден.")
        return SELECT_EMPLOYEE_FOR_HISTORY

    if not history:
        text = f"История операций для {user[1]} пуста.\nТекущий баланс: {user[3]} баллов."
    else:
        text = f"Последние операции для {user[1]} (текущий баланс: {user[3]} баллов):\n\n"
        for record in history:
            admin_id = record['admin_id']
            points = record['points']
            reason = record['reason']
            timestamp = datetime.strptime(record['timestamp'], "%Y-%m-%d %H:%M:%S")
            timestamp = timestamp.strftime("%Y-%m-%d %H:%M")
            admin_name = ADMIN_INFO.get(admin_id, ("Неизвестный",))[0]
            sign = "+" if points > 0 else ""
            text += f"{timestamp}: {sign}{points} за {reason} (от {admin_name})\n"

    await update.message.reply_text(text)
    await show_main_menu(update)
    return MAIN_MENU


async def handle_balance(update: Update, context: CallbackContext):
    """Показать баланс пользователя."""
    user = await db.get_user(update.effective_user.id)
    if user:
        await update.message.reply_text(f"{user[1]}, ваш баланс: {user[3]} баллов")
    else:
        await update.message.reply_text("Вы не зарегистрированы в системе.")

async def handle_history(update: Update, context: CallbackContext):
    history = await db.get_employee_history(update.effective_user.id)
    if not history:
        await update.message.reply_text("История пуста.")
        return

    text = "История операций:\n"
    for record in history:
        admin_id = record['admin_id']
        points = record['points']
        reason = record['reason']
        timestamp = datetime.strptime(record['timestamp'], "%Y-%m-%d %H:%M:%S")
        timestamp = timestamp.strftime("%Y-%m-%d %H:%M")
        admin_name = ADMIN_INFO.get(admin_id, ("Неизвестный",))[0]
        sign = "+" if points > 0 else ""
        text += f"{timestamp}: {sign}{points} за {reason} (от {admin_name})\n"

    await update.message.reply_text(text)



async def entry_points_handler(update: Update, context: CallbackContext):
    text = update.message.text
    if text == "Начислить/Списать баллы":
        context.user_data['silent'] = False
    elif text == "Начислить/Списать баллы (silent)":
        context.user_data['silent'] = True
    else:
        await update.message.reply_text("Неверный выбор.")
        return ConversationHandler.END
    
    return await begin_point_change(update, context)


async def begin_point_change(update: Update, context: CallbackContext):
    """Начало изменения баллов."""
    buttons = [
        [KeyboardButton("Начислить баллы")],
        [KeyboardButton("Списать баллы")]
    ]
    markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text("Выберите действие:", reply_markup=markup)
    return SELECT_ACTION

async def select_action(update: Update, context: CallbackContext):
    action = update.message.text
    if action not in ["Начислить баллы", "Списать баллы"]:
        await update.message.reply_text("Пожалуйста, выберите из вариантов.")
        return SELECT_ACTION

    context.user_data['action'] = action
    users = await db.get_all_users()
    buttons = [[KeyboardButton(f"{u[1]} ({u[0]})")] for u in users]
    markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text("Выберите сотрудника:", reply_markup=markup)
    return SELECT_USER


async def select_user(update: Update, context: CallbackContext):
    selected = update.message.text
    try:
        name, uid = selected.rsplit('(', 1)
        user_id = int(uid[:-1])
    except Exception:
        await update.message.reply_text("Неверный формат. Попробуйте снова.")
        return SELECT_USER

    context.user_data['selected_user_id'] = user_id
    action = context.user_data['action']

    if action == "Списать баллы":
        await update.message.reply_text(
            "Введите количество баллов для списания и причину через точку с запятой (;).\n"
            "Например: 50; Ошибка в учёте"
        )
        return ENTER_DEDUCT_POINTS
    else:
        user = await db.get_user(user_id)
        if not user:
            await update.message.reply_text("Сотрудник не найден.")
            return SELECT_USER

        score_table = USM_SCORES if user[2] == "УСМ" else CONSULTANT_SCORES
        context.user_data['score_table'] = score_table

        buttons = [[KeyboardButton(reason)] for reason in score_table.keys()]
        buttons.append([KeyboardButton("Другое")])
        markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text("Выберите причину:", reply_markup=markup)
        return SELECT_REASON


async def enter_deduct_points(update: Update, context: CallbackContext):
    text = update.message.text
    try:
        points_str, reason = text.split(';', 1)
        points = int(points_str.strip())
        reason = reason.strip()
        if points <= 0 or not reason:
            raise ValueError
    except Exception:
        await update.message.reply_text(
            "Неверный формат. Введите количество баллов и причину через точку с запятой (;), например:\n"
            "50; Ошибка в учёте"
        )
        return ENTER_DEDUCT_POINTS

    points = -abs(points)
    admin_id = update.effective_user.id
    user_id = context.user_data['selected_user_id']
    silent = context.user_data.get('silent', False)

    await db.add_points(admin_id, user_id, points, reason, silent=silent)
    await notify_user_points_change(context, user_id, points, reason)
    await update.message.reply_text(f"Списано {abs(points)} баллов за '{reason}'.")
    await show_main_menu(update)
    return MAIN_MENU


async def select_reason(update: Update, context: CallbackContext):
    reason = update.message.text
    score_table = context.user_data.get('score_table', {})
    action = context.user_data.get('action', 'Начислить баллы')
    user_id = context.user_data['selected_user_id']

    if reason == "Другое":
        await update.message.reply_text("Введите количество баллов (целое число):")
        return ENTER_CUSTOM_POINTS

    if reason not in score_table:
        await update.message.reply_text("Неверная причина. Попробуйте снова.")
        return SELECT_REASON

    points = score_table[reason]
    if action == "Списать баллы":
        points = -abs(points)

    admin_id = update.effective_user.id
    silent = context.user_data.get('silent', False)

    await db.add_points(admin_id, user_id, points, reason, silent=silent)
    await notify_user_points_change(context, user_id, points, reason)
    await update.message.reply_text(f"{'Начислено' if points > 0 else 'Списано'} {abs(points)} баллов за '{reason}'")
    await show_main_menu(update)
    return MAIN_MENU


async def enter_custom_points(update: Update, context: CallbackContext):
    try:
        points = int(update.message.text)
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите целое число.")
        return ENTER_CUSTOM_POINTS

    action = context.user_data.get('action', 'Начислить баллы')
    if action == "Списать баллы":
        points = -abs(points)

    admin_id = update.effective_user.id
    user_id = context.user_data['selected_user_id']
    reason = "Другое (вручную)"
    silent = context.user_data.get('silent', False)

    await db.add_points(admin_id, user_id, points, reason, silent=silent)
    await notify_user_points_change(context, user_id, points, reason)
    await update.message.reply_text(f"{'Начислено' if points > 0 else 'Списано'} {abs(points)} баллов.")
    await show_main_menu(update)
    return MAIN_MENU


async def check_usage_requests(update: Update, context: CallbackContext):
    """Проверка заявок на использование баллов."""
    user_id = update.effective_user.id
    if user_id not in ADMINS and user_id not in SUPERADMINS:
        await update.message.reply_text("⛔️ У вас нет доступа к этой функции.")
        return

    requests = await db.get_pending_requests()
    if not requests:
        await update.message.reply_text("📭 Нет заявок на рассмотрение.")
        return

    for req_id, fio, desc, ts in requests:
        msg = f"📩 Заявка #{req_id}\n👤 Сотрудник: {fio}\n📌 Цель: {desc}\n🕒 Время: {ts}"
        buttons = [
            [
                InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{req_id}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{req_id}")
            ]
        ]
        markup = InlineKeyboardMarkup(buttons)
        await context.bot.send_message(chat_id=user_id, text=msg, reply_markup=markup)

async def show_approved_requests(update, context):
    """Показать одобренные заявки."""
    requests = await db.get_latest_approved_requests()
    if not requests:
        await update.message.reply_text("Очередь пуста.")
        return

    text_lines = ["✅Одобренные заявки\n"]
    for req_id, fio, desc, date in requests:
        text_lines.append(f" {fio} — {desc} ({date})")
    text = "\n".join(text_lines)

    keyboard = [
        [InlineKeyboardButton("Очистить очередь", callback_data="clear_queue")],
        [InlineKeyboardButton("Назад", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, reply_markup=reply_markup)

async def handle_queue_buttons(update, context):
    """Обработка кнопок очереди."""
    query = update.callback_query
    await query.answer()

    if query.data == "clear_queue":
        await db.clear_approved_requests()
        await query.edit_message_text("Очередь успешно очищена.")
    elif query.data == "back_to_menu":
        await query.edit_message_text("Вы вернулись в главное меню.")

async def handle_admin_action(update: Update, context: CallbackContext):
    """Обработка действий администратора."""
    query = update.callback_query
    await query.answer()
    action, req_id = query.data.split("_")
    req_id = int(req_id)

    request_data = await db.get_request(req_id)
    if not request_data:
        await query.edit_message_text("❌ Заявка не найдена.")
        return

    user_id, desc, status, ts = request_data

    if status != "pending":
        await query.edit_message_text(f"⚠️ Заявка уже была обработана ({status}).")
        return

    if action == "approve":
        await db.approve_request(req_id)
        await context.bot.send_message(chat_id=user_id, text="✅ Ваша заявка была одобрена!")
        await query.edit_message_text("✅ Заявка одобрена.")
    elif action == "reject":
        await db.reject_request(req_id)
        await context.bot.send_message(chat_id=user_id, text="❌ Ваша заявка была отклонена.")
        await query.edit_message_text("❌ Заявка отклонена.")

#-------------------------------------------------------------------------------------------------------------#



async def use_points(update: Update, context: CallbackContext):
    """Использование баллов."""
    user_id = update.effective_user.id
    user = await db.get_user(user_id)
    if not user:
        await update.message.reply_text("Вы не зарегистрированы.")
        return MAIN_MENU

    if user[3] <= 0:
        await update.message.reply_text(f"Заявка не может быть отправлена. \nВаш баланс: {user[3]}")
        return MAIN_MENU

    # Перенаправляем в новое состояние выбора типа использования
    buttons = [
        [KeyboardButton("Уйти на 1 час раньше")],
        [KeyboardButton("Уйти на 2 часа раньше")],
        [KeyboardButton("Уйти на 3 часа раньше")],
        [KeyboardButton("Другое использование")],
    ]
    markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text("Выберите как вы хотите использовать баллы:", reply_markup=markup)
    return SELECT_USAGE_TYPE  

#--------------------------ебучий календарь------------------------------------------------#

def generate_calendar_keyboard(year: int, month: int, min_date: datetime = None) -> InlineKeyboardMarkup:
    """
    Генерирует инлайн-клавиатуру календаря для указанного месяца и года.
    min_date - минимальная доступная дата (сегодня или позже)
    """
    # Если min_date не указана, используем сегодня
    if min_date is None:
        min_date = datetime.now().date()
    
    # Определяем первый день месяца и количество дней в месяце
    _, num_days = monthrange(year, month)
    first_weekday, _ = monthrange(year, month)  # День недели первого дня (0-понедельник, 6-воскресенье)
    
    # Создаем заголовок с названием месяца и года
    month_title = f"{month_name[month].capitalize()} {year}"
    
    # Создаем строки для клавиатуры
    keyboard = []
    
    # Кнопки навигации
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1
    
    nav_buttons = [
        InlineKeyboardButton("◀️", callback_data=f"nav_{prev_year}-{prev_month}"),
        InlineKeyboardButton(month_title, callback_data="ignore"),
        InlineKeyboardButton("▶️", callback_data=f"nav_{next_year}-{next_month}")
    ]
    keyboard.append(nav_buttons)
    
    # Заголовки дней недели
    days_of_week = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    keyboard.append([InlineKeyboardButton(day, callback_data="ignore") for day in days_of_week])
    
    # Генерируем дни месяца
    day_buttons = []
    current_row = []
    
    # Пустые кнопки для дней предыдущего месяца
    for _ in range(first_weekday):
        current_row.append(InlineKeyboardButton(" ", callback_data="ignore"))
    
    # Добавляем кнопки для каждого дня месяца
    for day in range(1, num_days + 1):
        date_obj = datetime(year, month, day).date()
        
        # Проверяем, можно ли выбрать эту дату
        if date_obj < min_date:
            # Прошедшие даты - неактивны
            current_row.append(InlineKeyboardButton(" ", callback_data="ignore"))
        else:
            # Активные даты
            current_row.append(InlineKeyboardButton(str(day), callback_data=f"date_{year}-{month}-{day}"))
        
        # Переход на новую строку после субботы (6-й день)
        if len(current_row) == 7:
            day_buttons.append(current_row)
            current_row = []
    
    # Добавляем оставшиеся дни
    if current_row:
        # Заполняем пустые места
        while len(current_row) < 7:
            current_row.append(InlineKeyboardButton(" ", callback_data="ignore"))
        day_buttons.append(current_row)
    
    keyboard.extend(day_buttons)
    
    # Кнопка отмены
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel_calendar")])
    
    return InlineKeyboardMarkup(keyboard)

async def select_usage_type(update: Update, context: CallbackContext):
    """Обработка выбора типа использования баллов."""
    choice = update.message.text
    context.user_data['usage_type'] = choice
    
    if choice.startswith("Уйти на"):
        hours = int(choice.split()[2])
        context.user_data['hours'] = hours
        
        # Получаем текущую дату
        today = datetime.now().date()
        
        # Генерируем календарь на текущий месяц
        keyboard = generate_calendar_keyboard(today.year, today.month, min_date=today)
        
        await update.message.reply_text(
            "Выберите дату для ухода:",
            reply_markup=keyboard
        )
        return SELECT_DATE
    
    else:  # Другое использование
        await update.message.reply_text("Опишите, как вы хотите использовать баллы:")
        return ENTER_DESCRIPTION

async def handle_calendar(update: Update, context: CallbackContext):
    """Обработка выбора даты в календаре."""
    query = update.callback_query
    await query.answer()
    
    # Обработка навигации (переключение месяцев)
    if query.data.startswith("nav_"):
        # Извлекаем год и месяц из callback_data
        year, month = map(int, query.data.split("_")[1].split("-"))
        
        # Получаем минимальную доступную дату (сегодня)
        min_date = datetime.now().date()
        
        # Генерируем новый календарь
        keyboard = generate_calendar_keyboard(year, month, min_date=min_date)
        
        # Обновляем сообщение
        try:
            await query.edit_message_text(
                "Выберите дату для ухода:",
                reply_markup=keyboard
            )
        except BadRequest:
            pass  # Игнорируем ошибку, если сообщение не изменилось
        return SELECT_DATE
    
    # Обработка выбора даты
    elif query.data.startswith("date_"):
        # Извлекаем дату из callback_data
        year, month, day = map(int, query.data.split("_")[1].split("-"))
        selected_date = datetime(year, month, day).date()
        
        # Проверяем доступность даты
        date_str = selected_date.strftime("%Y-%m-%d")
        if not await db.is_date_available(date_str):
            await query.answer("Эта дата уже занята. Выберите другую.", show_alert=True)
            return SELECT_DATE
        
        # Сохраняем выбранную дату
        context.user_data['date'] = selected_date
        hours = context.user_data['hours']
        cost = 150 * hours
        date_display = selected_date.strftime("%d.%m.%Y")
        description = f"Уйти на {hours} часа раньше {date_display} (стоимость: {cost} баллов)"
        context.user_data['description'] = description
        
        # Запрашиваем подтверждение с inline-кнопками
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_request"),
                InlineKeyboardButton("❌ Отмена", callback_data="cancel_request")
            ]
        ])
        
        await query.edit_message_text(
            f"Вы выбрали дату: {date_display}\n"
            f"Описание: {description}\n\n"
            f"Отправить заявку?",
            reply_markup=keyboard
        )
        return CONFIRM_REQUEST
    
    # Обработка отмены
    elif query.data == "cancel_calendar":
        try:
            await query.message.delete()
        except BadRequest:
            pass
        
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Выбор даты отменен."
        )
        await show_main_menu_for_chat(context, query.message.chat_id, query.from_user.id)
        return MAIN_MENU
    
    # Игнорируем другие нажатия
    return SELECT_DATE

async def cancel_date_selection(update: Update, context: CallbackContext):
    """Обработка отмены выбора даты."""
    await update.message.reply_text("Выбор даты отменен.")
    await show_main_menu(update)
    return MAIN_MENU

async def show_main_menu_for_chat(context: CallbackContext, chat_id: int, user_id: int):
    """Отправка главного меню по chat_id."""
    if user_id in ADMINS:
        buttons = [
            [KeyboardButton("Начислить/Списать баллы")],
            [KeyboardButton("Очередь использования баллов")],
            [KeyboardButton("Проверка заявок на использование")],
            [KeyboardButton("История сотрудника")],
            [KeyboardButton("Сотрудники")],
            [KeyboardButton("Изменения")],
        ]
    elif user_id in SUPERADMINS:
        buttons = [
            [KeyboardButton("Начислить/Списать баллы")],
            [KeyboardButton("Начислить/Списать баллы (silent)")],
            [KeyboardButton("Очередь использования баллов")],
            [KeyboardButton("Проверка заявок на использование")],
            [KeyboardButton("История сотрудника")],
            [KeyboardButton("Сотрудники")],
            [KeyboardButton("Изменения")],
        ]
    else:
        buttons = [
            [KeyboardButton("Мой баланс")],
            [KeyboardButton("История")],
            [KeyboardButton("Использовать баллы")],
            [KeyboardButton("Сотрудники")],
            [KeyboardButton("Прайс-лист")],
            [KeyboardButton("Правила")],
        ]
    
    markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    await context.bot.send_message(chat_id=chat_id, text="Выберите действие:", reply_markup=markup)
    
async def handle_date_selection(update: Update, context: CallbackContext):
    """Обработка выбора дня"""
    date_str = update.message.text
    
    if date_str == "Отмена":
        await show_main_menu(update)
        return MAIN_MENU
    
    try:
        # Парсим дату
        day, month, year = map(int, date_str.split('.'))
        selected_date = datetime(year, month, day).date()
        
        # Проверяем, что дата не в прошлом
        today = datetime.now().date()
        if selected_date < today:
            await update.message.reply_text("Нельзя выбрать прошедшую дату. Выберите другую дату.")
            return SELECT_DATE
        
        # Проверяем доступность даты
        date_db_format = selected_date.strftime("%Y-%m-%d")
        if not await db.is_date_available(date_db_format):
            await update.message.reply_text("Эта дата больше не доступна. Выберите другую.")
            return SELECT_DATE
        
        hours = context.user_data['hours']
        cost = 150 * hours
        date_display = selected_date.strftime("%d.%m.%Y")
        description = f"Уйти на {hours} часа раньше {date_display} (стоимость: {cost} баллов)"
        
        # Сохраняем данные для подтверждения
        context.user_data['description'] = description
        context.user_data['date'] = selected_date
        
        # Запрашиваем подтверждение
        await update.message.reply_text(
            f"Вы выбрали дату: {date_display}\n"
            f"Описание: {description}\n\n"
            f"Отправить заявку?",
            reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton("✅ Подтвердить"), KeyboardButton("❌ Отмена")]
            ], resize_keyboard=True)
        )
        return CONFIRM_REQUEST
        
    except Exception as e:
        logger.error(f"Ошибка обработки даты: {e}")
        await update.message.reply_text("Неверный формат даты. Попробуйте снова.")
        return SELECT_DATE


async def handle_confirmation(update: Update, context: CallbackContext):
    """Обработка подтверждения заявки"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "confirm_request":
        description = context.user_data.get('description', '')
        user_id = query.from_user.id
        hours = context.user_data.get('hours', 1)
        cost = 150 * hours
        
        # Проверяем баланс
        user = await db.get_user(user_id)
        if not user:
            await query.edit_message_text("❌ Ошибка: пользователь не найден.")
            return ConversationHandler.END
            
        if user[3] < cost:
            await query.edit_message_text(f"❌ Недостаточно баллов. Ваш баланс: {user[3]}, требуется: {cost}")
            return ConversationHandler.END
        
        # Отправляем заявку
        req_id = await db.add_usage_request(user_id, description)
        
        # Обновляем сообщение с подтверждением
        await query.edit_message_text(
            f"✅ Заявка отправлена!\n\n"
            f"Описание: {description}\n"
            f"Администраторы получили уведомление."
        )
        
        # Уведомляем админов
        for admin_id in ADMINS:
            try:
                buttons = [
                    [
                        InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{req_id}"),
                        InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{req_id}")
                    ]
                ]
                markup = InlineKeyboardMarkup(buttons)
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=f"📩 Новая заявка на использование баллов\n\n"
                         f"👤 Сотрудник: {user[1]}\n"
                         f"📌 Описание: {description}\n"
                         f"💰 Баланс: {user[3]} баллов",
                    reply_markup=markup
                )
            except Exception as e:
                logging.error(f"Не удалось отправить сообщение админу {admin_id}: {e}")
        
        await show_main_menu_for_chat(context, query.message.chat_id, user_id)
        return MAIN_MENU
    
    elif query.data == "cancel_request":
        # Обновляем сообщение с подтверждением
        await query.edit_message_text("❌ Заявка отменена.")
        
        await show_main_menu_for_chat(context, query.message.chat_id, query.from_user.id)
        return MAIN_MENU
    
    return CONFIRM_REQUEST

async def ignore_callback(update: Update, context: CallbackContext):
    """Игнорирует нажатия на недоступные даты"""
    query = update.callback_query
    await query.answer()



async def use_points_description(update: Update, context: CallbackContext):
    """Отправка заявки на использование баллов."""
    desc = update.message.text.strip()
    user_id = update.effective_user.id
    req_id = await db.add_usage_request(user_id, desc)
    
    await update.message.reply_text("Заявка отправлена администраторам.")

    user = await db.get_user(user_id)
    if not user:
        await update.message.reply_text("Вы не зарегистрированы.")
        return MAIN_MENU

    msg = f"Новая заявка на использование баллов от {user[1]} (баланс: {user[3]} баллов):\n\n{desc}"

    for admin_id in ADMINS:
        try:
            buttons = [
                [
                    InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{req_id}"),
                    InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{req_id}")
                ]
            ]
            markup = InlineKeyboardMarkup(buttons)
            await context.bot.send_message(chat_id=admin_id, text=msg, reply_markup=markup)
        except Exception as e:
            logging.error(f"Не удалось отправить сообщение админу: {e}")

    await show_main_menu(update)
    return MAIN_MENU


async def fallback(update: Update, context: CallbackContext):
    """Обработчик неизвестных команд."""
    await update.message.reply_text("Неизвестная команда. Возвращаюсь в главное меню.")
    await show_main_menu(update)
    return MAIN_MENU

async def main():
    """Основная функция запуска бота."""
    await db.connect()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Обработчики inline-кнопок
    app.add_handler(CallbackQueryHandler(handle_admin_action, pattern="^(approve|reject)_\\d+$"))
    app.add_handler(CallbackQueryHandler(handle_queue_buttons, pattern="^(clear_queue|back_to_menu)$"))
    app.add_handler(CallbackQueryHandler(show_employees_by_role, pattern="^role_"))
    app.add_handler(CallbackQueryHandler(handle_delete_user, pattern=r"^delete_user_\d+$"))
    # Добавьте этот обработчик в main()
    app.add_handler(CallbackQueryHandler(ignore_callback, pattern="^ignore$"))
    app.add_handler(CallbackQueryHandler(handle_calendar, pattern=r"^(nav|date|cancel)_"))
    app.add_handler(CallbackQueryHandler(handle_confirmation, pattern="^(confirm_request|cancel_request)$"))
    # Основной обработчик диалогов
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN_MENU: [
                MessageHandler(filters.Regex("^Мой баланс$"), handle_balance),
                MessageHandler(filters.Regex("^История$"), handle_history),
                MessageHandler(filters.Regex("^(Начислить/Списать баллы|Начислить/Списать баллы \\(silent\\))$"), entry_points_handler),
                MessageHandler(filters.Regex("^Проверка заявок на использование$"), check_usage_requests),
                MessageHandler(filters.Regex("^Использовать баллы$"), use_points),
                MessageHandler(filters.Regex("^Очередь использования баллов$"), show_approved_requests),
                MessageHandler(filters.Regex("^История сотрудника$"), begin_employee_history),
                MessageHandler(filters.Regex("^Сотрудники$"), choose_role),
                MessageHandler(filters.Regex("^Удаление сотрудника$"), show_employees_for_admin),
                MessageHandler(filters.Regex("^Прайс-лист$"), send_price),
                MessageHandler(filters.Regex("^Правила$"), send_rules),
                MessageHandler(filters.Regex("^Изменения$"), show_admin_changes_menu),
                MessageHandler(filters.Regex("^Изменить правила$"), edit_rules),
                MessageHandler(filters.Regex("^Изменить прайс-лист$"), edit_price),
                MessageHandler(filters.ALL, fallback)
            ],
            SELECT_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_user)],
            SELECT_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_reason)],
            ENTER_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, use_points_description)],
            SELECT_USAGE_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_usage_type)],
            SELECT_DATE: [CallbackQueryHandler(handle_calendar, pattern=r"^calendar"),
                MessageHandler(filters.Regex("^Отмена$"), cancel_date_selection)],
            SELECT_EMPLOYEE_FOR_HISTORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, show_employee_history)],
            SELECT_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_action)],
            ENTER_CUSTOM_POINTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_custom_points)],
            ENTER_DEDUCT_POINTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_deduct_points)],
            REGISTRATION_FIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, registration_fio)],
            REGISTRATION_ROLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, registration_role)],
            EDIT_TEXT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_text_input)],
        },
        fallbacks=[MessageHandler(filters.ALL, fallback)]
    )

    app.add_handler(conv_handler)
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
        
        # Бесконечный цикл работы бота
    while True:
        await asyncio.sleep(3600)

if __name__ == '__main__':
    asyncio.run(main())