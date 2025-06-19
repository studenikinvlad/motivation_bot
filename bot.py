import logging
import re
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup

from telegram.ext import (ApplicationBuilder, CommandHandler, MessageHandler, filters,
                          ConversationHandler, CallbackContext)
import db
from config import BOT_TOKEN, ADMINS, ADMIN_INFO, USM_SCORES, CONSULTANT_SCORES

# Стейты ConversationHandler
(MAIN_MENU, CHOOSE_ACTION, ENTER_DESCRIPTION, SELECT_USER,
 SELECT_REASON, CONFIRM_POINTS, SELECT_EMPLOYEE_FOR_HISTORY, SELECT_ACTION,
 ENTER_CUSTOM_POINTS, ENTER_DEDUCT_POINTS, REGISTRATION_FIO, REGISTRATION_ROLE, EDIT_TEXT_INPUT ) = range(13)


logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Универсальная проверка регистрации
async def ensure_registered(update: Update) -> bool:
    user_id = update.effective_user.id
    if user_id in ADMINS:
        return True
    if not db.get_user(user_id):
        await update.message.reply_text("Вы не зарегистрированы. Напишите /start.")
        return False
    return True

# Главное меню
async def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if user_id in ADMINS:
        # Админы сразу в меню, регистрация не нужна
        await show_main_menu(update)
        return MAIN_MENU

    user = db.get_user(user_id)
    if user is None:
        await update.message.reply_text(
            "Добро пожаловать! Похоже, вы здесь впервые. Пожалуйста, введите ваше ФИО для регистрации:"
        )
        return REGISTRATION_FIO
    else:
        await show_main_menu(update)
        return MAIN_MENU


# Обновлённое главное меню
async def show_main_menu(update: Update):
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
    if update.message:
        await update.message.reply_text("Выберите действие:", reply_markup=markup)
    elif update.callback_query:
        await update.callback_query.message.reply_text("Выберите действие:", reply_markup=markup)


#Базовые кнопки правила и прайс-лист
def load_price():
    try:
        with open("price.txt", "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "⚠️ Прайс-лист не найден."


def load_rules():
    try:
        with open("rules.txt", "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "⚠️ Правила не найдены."


async def send_price(update: Update, context: CallbackContext):
    await update.message.reply_text(load_price())

async def send_rules(update: Update, context: CallbackContext):
    await update.message.reply_text(load_rules())


# Регистрация ФИО
async def registration_fio(update: Update, context: CallbackContext):
    fio = update.message.text.strip()
    if not fio:
        await update.message.reply_text("ФИО не может быть пустым. Введите снова:")
        return REGISTRATION_FIO
    context.user_data['fio'] = fio
    buttons = [[KeyboardButton("Консультант")], [KeyboardButton("УСМ")]]
    markup = ReplyKeyboardMarkup(buttons, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Выберите вашу роль:", reply_markup=markup)
    return REGISTRATION_ROLE

# Регистрация роли
async def registration_role(update: Update, context: CallbackContext):
    role = update.message.text.strip()
    if role not in ["Консультант", "УСМ"]:
        await update.message.reply_text("Пожалуйста, выберите роль из кнопок.")
        return REGISTRATION_ROLE
    fio = context.user_data['fio']
    user_id = update.effective_user.id
    db.add_user(user_id, fio, role)
    await update.message.reply_text(f"Регистрация завершена! Добро пожаловать, {fio} ({role}) 🎉")
    await show_main_menu(update)
    return MAIN_MENU

# Меню изменений для админа
async def show_admin_changes_menu(update: Update, context: CallbackContext):
    buttons = [
        [KeyboardButton("Удаление сотрудника")],
        [KeyboardButton("Изменить правила")],
        [KeyboardButton("Изменить прайс-лист")],
        [KeyboardButton("Назад")],
    ]
    markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text("Меню изменений:", reply_markup=markup)

async def edit_rules(update: Update, context: CallbackContext):
    context.user_data['edit_mode'] = 'rules'
    await update.message.reply_text("Введите новый текст правил:")
    return EDIT_TEXT_INPUT


async def edit_price(update: Update, context: CallbackContext):
    context.user_data['edit_mode'] = 'price'
    await update.message.reply_text("Введите новый прайс-лист:")
    return EDIT_TEXT_INPUT


async def edit_text_input(update: Update, context: CallbackContext):
    mode = context.user_data.get('edit_mode')
    new_text = update.message.text.strip()

    try:
        if mode == 'rules':
            with open("rules.txt", "w", encoding="utf-8") as f:
                f.write(new_text)
            await update.message.reply_text("✅ Правила обновлены.")
        elif mode == 'price':
            with open("price.txt", "w", encoding="utf-8") as f:
                f.write(new_text)
            await update.message.reply_text("✅ Прайс-лист обновлён.")
        else:
            await update.message.reply_text("⚠️ Неизвестный режим редактирования.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при сохранении: {e}")

    context.user_data['edit_mode'] = None
    await show_main_menu(update)
    return MAIN_MENU


#Удаление сотрудника
async def show_employees_for_admin(update, context):
    users = db.get_all_users()  # Возвращает [(user_id, fio, role), ...]

    keyboard = []
    for user_id, fio, role in users:
        text = f"{fio} ({role})"
        callback_data = f"delete_user_{user_id}"
        keyboard.append([InlineKeyboardButton(text=text, callback_data="noop"),  # просто текст кнопки без действия
                         InlineKeyboardButton(text="Удалить", callback_data=callback_data)])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Список сотрудников:", reply_markup=reply_markup)

async def handle_delete_user(update, context):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    if user_id not in ADMINS:
        await query.edit_message_text("⛔️ У вас нет прав для удаления сотрудников.")
        return
    
    data = query.data  # пример: "delete_user_123456"
    user_id = int(data.split("_")[-1])

    # Удаляем пользователя из базы
    db.delete_user(user_id)

    await query.edit_message_text(f"Сотрудник с ID {user_id} удалён.")
    await show_employees_for_admin(update, context)


    # Обновляем список сотрудников после удаления (по желанию)
    # Можно вызвать функцию вывода списка заново, например:
    # await show_employees_for_admin(update, context)

#Отображение всех сотрудников и их баллов

async def choose_role(update: Update, context: CallbackContext):
    keyboard = [
        [
            InlineKeyboardButton("УСМ", callback_data="role_УСМ"),
            InlineKeyboardButton("Консультант", callback_data="role_Консультант"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text("Выберите роль для отображения:", reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text("Выберите роль для отображения:", reply_markup=reply_markup)


async def show_employees_by_role(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    role = query.data.split("_")[1]  # Получаем 'УСМ' или 'Консультант'

    users = db.get_all_users()
    filtered = [u for u in users if u[2] == role]  # u[2] — роль

    if not filtered:
        await query.edit_message_text(f"Сотрудники с ролью {role} не найдены.")
        return

    msg = f"Сотрудники с ролью {role}:\n\n"
    for user_id, fio, _ in filtered:
        user_data = db.get_user(user_id)
        points = user_data[3] if user_data else 0
        msg += f"{fio} — Баллы: {points}\n"

    await query.edit_message_text(msg)



#хендлер уведомления сотрудника
async def notify_user_points_change(context: CallbackContext, user_id: int, points: int, reason: str):
    user = db.get_user(user_id)
    if not user:
        return
    fio = user[1]
    current_points = user[3]
    sign = '+' if points > 0 else ''
    text = f"{fio}, вам {'начислено' if points > 0 else 'списано'} {sign}{points} баллов за: {reason}.\nТекущий баланс: {current_points} баллов."
    try:
        await context.bot.send_message(chat_id=user_id, text=text)
    except Exception as e:
        logger.error(f"Не удалось отправить уведомление пользователю {user_id}: {e}")

# --- Новый хендлер для кнопки "История сотрудника" ---
async def begin_employee_history(update: Update, context: CallbackContext):
    users = db.get_all_users()
    buttons = [[KeyboardButton(f"{u[1]} ({u[0]})")] for u in users]  # [ ["Иванов (123)"], ... ]
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

    history = db.get_points_history(user_id)
    user = db.get_user(user_id)
    if not user:
        await update.message.reply_text("Сотрудник не найден.")
        return SELECT_EMPLOYEE_FOR_HISTORY

    _, fio_full, _, points = user

    if not history:
        text = f"История операций для {fio_full} пуста.\nТекущий баланс: {points} баллов."
    else:
        text = f"Последние 10 операций для {fio_full} (текущий баланс: {points} баллов):\n\n"
        # Выводим только последние 10 записей
        for admin_id, pts, reason, ts in history[:10]:
            admin_name = ADMIN_INFO.get(admin_id, ("Неизвестный",))[0]
            sign = "+" if pts > 0 else ""
            text += f"{ts}: {sign}{pts} за {reason} (от {admin_name})\n"

    await update.message.reply_text(text)
    await show_main_menu(update)
    return MAIN_MENU

# Просмотр баланса
async def handle_balance(update: Update, context: CallbackContext):
    user = db.get_user(update.effective_user.id)
    if user:
        _, fio, _, points = user
        await update.message.reply_text(f"{fio}, ваш баланс: {points} баллов")
    else:
        await update.message.reply_text("Вы не зарегистрированы в системе.")

# Просмотр истории
async def handle_history(update: Update, context: CallbackContext):
    history = db.get_points_history(update.effective_user.id)
    if not history:
        await update.message.reply_text("История пуста.")
        return

    text = "История операций:\n"
    for admin_id, points, reason, ts in history:
        admin_name = ADMIN_INFO.get(admin_id, ("Неизвестный",))[0]
        text += f"{ts}: {'+' if points > 0 else ''}{points} за {reason} (от {admin_name})\n"
    await update.message.reply_text(text)

# Начисление/Списание баллов
async def begin_point_change(update: Update, context: CallbackContext):
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
    users = db.get_all_users()
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
        # Логика для начисления — как было
        role = db.get_user(user_id)[2]
        score_table = USM_SCORES if "УСМ" in role else CONSULTANT_SCORES
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

    points = -abs(points)  # Списание — отрицательное значение
    admin_id = update.effective_user.id
    user_id = context.user_data['selected_user_id']

    db.add_points(admin_id, user_id, points, reason)
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
    # Если списываем, делаем отрицательным количеством
    if action == "Списать баллы":
        points = -abs(points)

    admin_id = update.effective_user.id
    db.add_points(admin_id, user_id, points, reason)
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

    db.add_points(admin_id, user_id, points, reason)
    await notify_user_points_change(context, user_id, points, reason)
    await update.message.reply_text(f"{'Начислено' if points > 0 else 'Списано'} {abs(points)} баллов.")

    await show_main_menu(update)
    return MAIN_MENU

# Очередь использования (заявки)
# Очередь использования (заявки в ожидании)
async def check_usage_requests(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in ADMINS:
        await update.message.reply_text("⛔️ У вас нет доступа к этой функции.")
        return

    requests = db.get_pending_requests()
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



# Показываем одобренные заявки

async def show_approved_requests(update, context):
    requests = db.get_latest_approved_requests()
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
    query = update.callback_query
    await query.answer()

    if query.data == "clear_queue":
        db.clear_approved_requests()
        await query.edit_message_text("Очередь успешно очищена.")
    elif query.data == "back_to_menu":
        # Вернуть пользователя в главное меню (пример)
        await query.edit_message_text("Вы вернулись в главное меню.")
        # Можно вызвать функцию показа главного меню или отправить соответствующее сообщение


# Обработка одобрения/отклонения заявок
async def handle_admin_action(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    action, req_id = query.data.split("_")
    req_id = int(req_id)

    request_data = db.get_request(req_id)
    if not request_data:
        await query.edit_message_text("❌ Заявка не найдена.")
        return

    user_id, desc, status, ts = request_data

    if status != "pending":
        await query.edit_message_text(f"⚠️ Заявка уже была обработана ({status}).")
        return

    if action == "approve":
        db.approve_request(req_id)
        await context.bot.send_message(chat_id=user_id, text="✅ Ваша заявка была одобрена!")
        await query.edit_message_text("✅ Заявка одобрена.")
    elif action == "reject":
        db.reject_request(req_id)
        await context.bot.send_message(chat_id=user_id, text="❌ Ваша заявка была отклонена.")
        await query.edit_message_text("❌ Заявка отклонена.")



# Использовать баллы (подача заявки)
async def use_points(update: Update, context: CallbackContext):
    
    user_id = update.effective_user.id
    user_points = db.get_user(user_id)[3]
    if user_points > 0:
        await update.message.reply_text("Опишите, как вы хотите использовать баллы:")
        return ENTER_DESCRIPTION
    else:
        await update.message.reply_text(f"Заявка не может быть отправлена. \nВаш баланс: {user_points}")
        return MAIN_MENU
        
    
    

async def use_points_description(update: Update, context: CallbackContext):
    desc = update.message.text.strip()
    user_id = update.effective_user.id
    req_id = db.add_usage_request(user_id, desc)
    
    await update.message.reply_text("Заявка отправлена администраторам.")

    fio = db.get_user(user_id)[1]
    user_points = db.get_user(user_id)[3]  # Текущий баланс

    msg = (
        f"Новая заявка на использование баллов от {fio} (баланс: {user_points} баллов):\n\n{desc}"
    )

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


# Хендлер для fallback
async def fallback(update: Update, context: CallbackContext):
    await update.message.reply_text("Неизвестная команда. Возвращаюсь в главное меню.")
    await show_main_menu(update)
    return MAIN_MENU

from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, filters

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Обработчик inline-кнопок админа (approve/reject)
    app.add_handler(CallbackQueryHandler(handle_admin_action, pattern="^(approve|reject)_\\d+$"))

    # Команда /check_requests (альтернативный запуск проверки заявок)
    app.add_handler(CommandHandler("check_requests", check_usage_requests))

    app.add_handler(CallbackQueryHandler(handle_queue_buttons, pattern="^(clear_queue|back_to_menu)$"))

    app.add_handler(MessageHandler(filters.Regex("^Сотрудники$"), choose_role))
    app.add_handler(CallbackQueryHandler(show_employees_by_role, pattern="^role_"))

    app.add_handler(CallbackQueryHandler(handle_delete_user, pattern=r"^delete_user_\d+$"))
    app.add_handler(MessageHandler(filters.Regex("^Удаление сотрудника$"), show_employees_for_admin))



    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN_MENU: [
                MessageHandler(filters.Regex("^Мой баланс$"), handle_balance),
                MessageHandler(filters.Regex("^История$"), handle_history),
                MessageHandler(filters.Regex("^Начислить/Списать баллы$"), begin_point_change),
                # Добавляем обработчик кнопки "Проверка заявок на использование"
                MessageHandler(filters.Regex("^Проверка заявок на использование$"), check_usage_requests),
                MessageHandler(filters.Regex("^Использовать баллы$"), use_points),
                MessageHandler(filters.Regex("^Очередь использования баллов$"), show_approved_requests),
                MessageHandler(filters.Regex("^История сотрудника$"), begin_employee_history),
                MessageHandler(filters.Regex("^Сотрудники$"), show_employees_by_role),
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

    app.run_polling()



if __name__ == '__main__':
    main()
