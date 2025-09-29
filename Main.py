import asyncio
import logging
import json
import re
import os
import sqlite3
import shutil
import pytz
from typing import Union
from telegram import CallbackQuery
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters
)
from datetime import datetime, timedelta
from telegram import (
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
# Состояния для ConversationHandler
REFERRAL_DEBUG = True  # Установите False в продакшене
WAIT_INVEST_AMOUNT = 10
WAIT_CALC_AMOUNT = 1
MIN_INVEST_AMOUNT = 10  # Минимальная сумма инвестиций
# Состояния должны быть определены в начале файла
# Состояния для ConversationHandler
WAIT_TOPUP_AMOUNT, WAIT_WITHDRAW_AMOUNT, WAIT_REQUISITES, WAIT_PAYMENT_METHOD, WAIT_INVEST_AMOUNT, WAIT_WITHDRAW_METHOD, WAIT_CRYPTO_AMOUNT = range(
    7)
# Конфигурация
ADMINS = [-1002562283915]  # ID админов
NEW_CHAT_ID = -1002562283915
DATA_FILE = "users.json"
users = {}
pending_topups = {}
pending_withdrawals = {}

# Клавиатуры
main_keyboard = ReplyKeyboardMarkup(
    [["📈 Депозит", "💼 Кошелёк"], ["🔢 Калькулятор", "ℹ️ О проекте"]],
    resize_keyboard=True,
    one_time_keyboard=False
)

wallet_keyboard = ReplyKeyboardMarkup(
    [["💳 Пополнить", "💸 Вывести"], ["🔙 на главную"]],
    resize_keyboard=True,
    one_time_keyboard=False
)
payment_method_keyboard = ReplyKeyboardMarkup(
    [["💳 Банковская карта", "📱 СБП"], ["₿ Криптовалюта", "🔙 на главную"]],
    resize_keyboard=True,
    one_time_keyboard=True
)
back_to_main_keyboard = ReplyKeyboardMarkup(
    [["🔙 на главную"]],
    resize_keyboard=True,
    one_time_keyboard=True
)
deposit_keyboard = ReplyKeyboardMarkup(
    [["📥 Инвестировать", "📤 Собрать прибыль"], ["🔙 на главную"]],
    resize_keyboard=True
)


def init_db():
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    # Удаляем старую таблицу (только для разработки!)

    # Создаем новую таблицу с правильной структурой
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            balance REAL DEFAULT 0.0,
            deposits TEXT DEFAULT '[]',
            created_at TEXT,
            referrer_id INTEGER DEFAULT NULL,
            referral_level INTEGER DEFAULT 1,
            referrals_count INTEGER DEFAULT 0,
            last_updated TEXT
        )
    """)
    conn.commit()
    conn.close()

    # conn = sqlite3.connect("users.db")
    # cursor = conn.cursor()
    #
    # # Удаляем комментарии из SQL-запроса
    # cursor.execute("""
    #                CREATE TABLE IF NOT EXISTS users
    #                (
    #                    id
    #                    INTEGER
    #                    PRIMARY
    #                    KEY,
    #                    username
    #                    TEXT,
    #                    balance
    #                    REAL
    #                    DEFAULT
    #                    0.0,
    #                    deposits
    #                    TEXT
    #                    DEFAULT
    #                    '[]',
    #                    created_at
    #                    TEXT,
    #                    referrer_id
    #                    INTEGER
    #                    DEFAULT
    #                    NULL,
    #                    referral_level
    #                    INTEGER
    #                    DEFAULT
    #                    1,
    #                    referrals
    #                    INTEGER
    #                    DEFAULT
    #                    NULL
    #                )
    #                """)


def get_referrals_by_levels(user_id):
    """Возвращает рефералов по уровням для указанного пользователя"""
    level1 = []  # Прямые рефералы (пользователи Б)
    level2 = []  # Рефералы рефералов (пользователи В)
    level3 = []  # Рефералы 3-го уровня (пользователи Г)

    # Получаем прямых рефералов (level1)
    if user_id in users:
        for uid, user_data in users.items():
            if user_data.get('referrer_id') == user_id:
                level1.append(uid)

    # Получаем рефералов второго уровня (level2)
    for ref1_id in level1:
        if ref1_id in users:
            for uid, user_data in users.items():
                if user_data.get('referrer_id') == ref1_id:
                    level2.append(uid)

    # Получаем рефералов третьего уровня (level3)
    for ref2_id in level2:
        if ref2_id in users:
            for uid, user_data in users.items():
                if user_data.get('referrer_id') == ref2_id:
                    level3.append(uid)

    return {
        'level1': level1,
        'level2': level2,
        'level3': level3
    }


async def help_command(update: Union[Update, CallbackQuery], context: ContextTypes.DEFAULT_TYPE):
    if isinstance(update, CallbackQuery):
        message = update.message
    else:
        message = update.message

    photo = "https://keephere.ru/get/J7FNEF714fc7YyM/o/photo_5_2025-07-25_12-14-28.jpg"

    text = """
📚 Обучающий гайд по TON STOCKER

1. Приглашаете друзей
2. Пополняете баланс
3. Все получают прибыль каждый час

Читайте более подробную инструкцию:
    """

    # Создаем кнопку с ссылкой на Telegraph
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📖 Открыть инструкцию",
                              url="https://telegra.ph/Obuchayushchij-gajd-po-TON-STOCKER-07-23")]
    ])

    if isinstance(update, CallbackQuery):
        await message.reply_photo(photo=photo, caption=text, parse_mode="HTML", reply_markup=keyboard)
    else:
        await update.message.reply_photo(photo=photo, caption=text, parse_mode="HTML", reply_markup=keyboard)


async def referral_stats(update: Union[Update, CallbackQuery], context: ContextTypes.DEFAULT_TYPE):
    if isinstance(update, CallbackQuery):
        user_id = update.from_user.id
        message = update.message
    else:
        user_id = update.effective_user.id
        message = update.message

        # Получаем рефералов по уровням
    referrals = get_referrals_by_levels(user_id)

    ref_link = f"https://t.me/{(await context.bot.get_me()).username}?start=ref_{user_id}"

    photo = "https://keephere.ru/get/tMtNEF71zrQnZPD/o/photo_4_2025-07-25_12-14-28.jpg"

    text = (
        f"👥 <b>Реферальная система</b>\n\n"
        f"🔗 Ваша ссылка: <code>{ref_link}</code>\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"1️⃣ Уровень: {len(referrals['level1'])} чел. (20 % )\n"
        f"2️⃣ Уровень: {len(referrals['level2'])} чел. (3%)\n"
        f"3️⃣ Уровень: {len(referrals['level3'])} чел. (1%)\n\n"
        f"💸 <b>Вы получаете:</b>\n"
        f"- 20% от инвестиций прямых рефералов\n"
        f"- 3% от инвестиций рефералов 2-го уровня\n"
        f"- 1% от инвестиций рефералов 3-го уровня"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Поделиться ссылкой", url=f"https://t.me/share/url?url={ref_link}")]
    ])
    if isinstance(update, CallbackQuery):
        await message.reply_photo(photo=photo,
                                  caption=text, parse_mode="HTML", reply_markup=keyboard)
    else:
        await update.message.reply_photo(
            photo=photo, caption=text,
            parse_mode="HTML", reply_markup=keyboard)


def calculate_current_profit(deposits):
    total_profit = 0
    now = datetime.now()

    for deposit in deposits:
        # Обычная прибыль (4% в день)
        if 'start' in deposit:
            start_time = datetime.strptime(deposit['start'], "%Y-%m-%d %H:%M:%S")
            elapsed = now - start_time
            elapsed_hours = elapsed.total_seconds() / 3600
            hourly_profit = deposit['amount'] * 0.00166
            total_profit += hourly_profit * elapsed_hours

            if 'collected_profit' in deposit:
                total_profit -= deposit['collected_profit']

        # Реферальные бонусы
        referral_profit = deposit.get('referral_profit', 0)
        collected_referral = deposit.get('collected_referral', 0)
        total_profit += (referral_profit - collected_referral)

    return max(0, total_profit)


async def update_deposit_message(context: ContextTypes.DEFAULT_TYPE, user_id):
    if user_id not in users:
        return

    user = users[user_id]
    if "last_deposit_msg_id" not in user:
        return

    deposits = user.get("deposits", [])
    total_invested = sum(d["amount"] for d in deposits)
    current_profit = calculate_current_profit(deposits)

    try:
        await context.bot.edit_message_text(
            chat_id=user_id,
            message_id=user["last_deposit_msg_id"],
            text=f"📠 <b>Процент:</b> 4% в день\n"
                 f"⏱️ <b>Доход:</b> начисляется ежечасно\n"
                 f"📆 <b>Срок:</b> 60 дней\n\n"
                 f"💳 <b>Общий вклад:</b> {total_invested:.2f}₽\n"
                 f"💵 <b>Накоплено:</b> {current_profit:.2f}₽\n\n"
                 f"ℹ️ Прибыль начисляется непрерывно и доступна для вывода в любое время",
            reply_markup=deposit_keyboard,
            parse_mode="HTML"
        )
    except:
        if f"deposit_update_{user_id}" in context.job_queue.jobs():
            context.job_queue.jobs()[f"deposit_update_{user_id}"].schedule_removal()


def load_users():
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    users.clear()

    try:
        cursor.execute("""
            SELECT id, username, balance, deposits, created_at, referrer_id, referral_level, referrals_count 
            FROM users
        """)

        for row in cursor.fetchall():
            try:
                users[row[0]] = {
                    "username": row[1],
                    "balance": float(row[2]),
                    "deposits": json.loads(row[3] or "[]"),
                    "created_at": row[4],
                    "referrer_id": row[5],
                    "referral_level": row[6] if row[6] else 1,
                    "referrals_count": row[7] if row[7] else 0  # Загружаем количество
                }
            except json.JSONDecodeError:
                logger.error(f"Ошибка загрузки депозитов пользователя {row[0]}")
                users[row[0]] = {
                    "username": row[1],
                    "balance": float(row[2]),
                    "deposits": [],
                    "created_at": row[4],
                    "referrer_id": row[5],
                    "referral_level": row[6] if row[6] else 1,
                    "referrals_count": row[7] if row[7] else 0
                }
    except Exception as e:
        logger.error(f"Ошибка загрузки пользователей: {e}")
    finally:
        conn.close()


async def show_ref_tree(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    tree = build_ref_tree(user_id)
    await update.message.reply_text(f"🌳 Ваша реферальная структура:\n{tree}")


def build_ref_tree(user_id, level=1, max_level=3):
    if level > max_level:
        return ""
    result = ""
    for uid, data in users.items():
        if data.get('referrer_id') == user_id:
            result += "  " * level + f"└─ {data['username']} (Ур. {level})\n"
            result += build_ref_tree(uid, level + 1)
    return result


def save_user(user_id):
    user = users.get(user_id)
    if not user:
        return

    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO users (id, username, balance, deposits, created_at, referrer_id, referral_level, referrals_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                username = excluded.username,
                balance = excluded.balance,
                deposits = excluded.deposits,
                created_at = excluded.created_at,
                referrer_id = excluded.referrer_id,
                referral_level = excluded.referral_level,
                referrals_count = excluded.referrals_count
        """, (
            user_id,
            user.get("username"),
            user.get("balance", 0.0),
            json.dumps(user.get("deposits", [])),
            user.get("created_at"),
            user.get("referrer_id"),
            user.get("referral_level", 1),
            user.get("referrals_count", 0)  # Важное поле - сохраняем количество
        ))
        conn.commit()
    except Exception as e:
        logger.error(f"Ошибка сохранения пользователя {user_id}: {e}")
    finally:
        conn.close()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id

    moscow_tz = pytz.timezone('Europe/Moscow')
    current_date_moscow = datetime.now(moscow_tz)
    formatted_date = current_date_moscow.strftime("%d.%m.%Y")

    # 1. Проверяем, зарегистрирован ли пользователь
    if chat_id not in users:
        # Создаем нового пользователя
        users[chat_id] = {
            'username': user.username or user.full_name,
            'balance': 0.0,
            'deposits': [],
            'created_at': formatted_date,
            'referrer_id': None,
            'referral_level': 1,
            'referrals_count': 0,
            'is_ref_used': False  # Флаг использования рефссылки
        }
    else:
        # Если пользователь уже зарегистрирован
        if users[chat_id].get('is_ref_used', False):
            if context.args and len(context.args) > 0 and context.args[0].startswith('ref_'):
                await update.message.reply_text(
                    "⚠ Вы уже зарегистрированы по реферальной ссылке",
                    reply_markup=main_keyboard
                )
            return await show_main_menu(update)

    save_user(chat_id)

    # 2. Обработка реферальной ссылки
    if context.args and len(context.args) > 0 and context.args[0].startswith('ref_'):
        try:
            referrer_id = int(context.args[0][4:])

            # Проверки
            if referrer_id == chat_id:
                await update.message.reply_text(
                    "❌ Нельзя использовать собственную реферальную ссылку",
                    reply_markup=main_keyboard
                )
            elif users[chat_id].get('referrer_id'):
                await update.message.reply_text(
                    "❌ Реферер может быть указан только один раз",
                    reply_markup=main_keyboard
                )
            else:
                # Загружаем реферера если его нет в памяти
                if referrer_id not in users:
                    load_user_from_db(referrer_id)

                if referrer_id in users:
                    # Фиксируем реферера
                    users[chat_id]['referrer_id'] = referrer_id
                    users[chat_id]['is_ref_used'] = True
                    users[referrer_id]['referrals_count'] += 1

                    # Сохраняем в базу данных
                    save_user(chat_id)
                    save_user(referrer_id)

                    # Уведомление рефереру
                    try:
                        await context.bot.send_message(
                            chat_id=referrer_id,
                            text=f"🎉 Новый реферал!\n"
                                 f"👤 @{user.username or user.full_name}\n"
                                 f"🆔 ID: {chat_id}\n"
                                 f"Всего рефералов: {users[referrer_id]['referrals_count']}"
                        )
                    except Exception as e:
                        logger.error(f"Ошибка уведомления: {e}")
                else:
                    await update.message.reply_text(
                        "⚠ Реферер не найден в системе",
                        reply_markup=main_keyboard
                    )
        except (ValueError, IndexError) as e:
            logger.error(f"Ошибка обработки рефссылки: {e}")

    # 3. Отправляем главное меню
    await show_main_menu(update)


async def show_main_menu(update: Update):
    await update.message.reply_text(
        """
🌐 TON STOCKER — инвестиции нового уровня

Добро пожаловать в мир финансовой синергии, где каждый вклад работает на тебя и твоё окружение.
🔗 Здесь ты не просто инвестируешь — ты запускаешь цепную реакцию роста.
    
📈 Почему TON STOCKER?
🔹 Доходность от 4% ежедневно — стабильный, предсказуемый доход с первого дня
🔹 Интеллектуальная партнерская программа 3 уровня — получай вознаграждение, помогая другим выйти на путь финансовой свободы
🔹 Прозрачная система начислений — каждый час, каждую минуту, твои средства работают
🔹 Без границ — инвестиции доступны от 10 ₽

🧬 Как это работает?
1. Вносишь сумму — начинаешь получать доход
2. Делишься своей реферальной ссылкой — создаешь команду
3. Получаешь бонусы до 24% от действий приглашённых
4. Чем больше команда — тем выше твой пассивный доход

🥇 Твоя сила — в твоём круге
В этом сообществе ты не один.
Ты — лидер. Ты — вдохновитель.
Ты — часть растущей экосистемы, в которой выигрывают все.

⚡ Присоединяйся. Начни рост уже сегодня.
«Не жди чуда. Создай его.»
        """,

        reply_markup=main_keyboard,
        parse_mode="HTML"
    )


async def wallet_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_data = users.get(chat_id, {})

    # Проверяем и инициализируем пользователя, если его нет
    if chat_id not in users:
        users[chat_id] = {
            "username": update.effective_user.username or update.effective_user.full_name or str(chat_id),
            "balance": 0.0,
            "deposits": [],
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        save_user(chat_id)
        user_data = users[chat_id]

    # Форматируем username
    username = user_data.get('username', '')
    if username and not username.startswith('@'):
        username = f"@{username}"

    # Проверяем и форматируем баланс
    balance = user_data.get("balance", 0.0)
    if not isinstance(balance, (int, float)):
        try:
            balance = float(balance)
        except (ValueError, TypeError):
            balance = 0.0
            users[chat_id]["balance"] = 0.0
            save_user(chat_id)

    await update.message.reply_photo(
        photo="https://keephere.ru/get/nRRNEF71RHjvt4s/o/photo_6_2025-07-25_12-14-28.jpg",
        caption=f"""
💎 <b>Ваш инвестиционный портфель</b> 💎

<b>🆔 ID:</b> <code>{chat_id}</code>
<b>👤 Профиль:</b> {username}
<b>📅 С нами с:</b> {user_data.get("created_at", "неизвестно")}

<b>💰 Текущий баланс:</b>
<b>➤ {balance:.2f} ₽</b> 

<i>Ваши средства всегда под защитой</i>

✨ <i>Каждый рубль работает на вас!</i>
    """,
        parse_mode=ParseMode.HTML,
        reply_markup=wallet_keyboard
    )


async def topup_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Если уже есть активная операция - предлагаем отменить
    if user_id in pending_topups:
        await update.message.reply_text(
            "❗ У вас есть незавершенная операция пополнения.\n"
            "❌ Для начала новой операции сначала отмените текущую.",
            reply_markup=ReplyKeyboardMarkup([["❌ Отменить операцию"], ["🔙 На главную"]], resize_keyboard=True)
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "💳 Выберите способ пополнения:",
        reply_markup=payment_method_keyboard
    )
    return WAIT_PAYMENT_METHOD


async def topup_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    cancel_keyboard = ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True)

    if text == "❌ Отмена":
        return await cancel_operation(update, context)

    try:
        amount = float(text.replace(",", "."))
        if amount <= 0:
            raise ValueError("Сумма должна быть положительной")

        payment_method = context.user_data.get('payment_method', '')

        # Проверка минимальных сумм
        if "крипт" in payment_method.lower() and amount < 500:
            await update.message.reply_text(
                "❌ Минимальная сумма пополнения криптовалютой: 500 RUB\n"
                "Введите сумму заново:",
                reply_markup=cancel_keyboard
            )
            return WAIT_CRYPTO_AMOUNT

        elif amount < 100:
            await update.message.reply_text(
                "❌ Минимальная сумма пополнения: 100 RUB\n"
                "Введите сумму заново:",
                reply_markup=cancel_keyboard
            )
            return WAIT_TOPUP_AMOUNT

    except (ValueError, TypeError):
        await update.message.reply_text(
            "❌ Неверная сумма. Введите положительное число (например: 100 или 50.5):",
            reply_markup=cancel_keyboard
        )
        return WAIT_TOPUP_AMOUNT if "крипт" not in payment_method.lower() else WAIT_CRYPTO_AMOUNT

    # Создаем заявку
    pending_topups[user_id] = {
        'amount': amount,
        'timestamp': datetime.now().isoformat(),
        'username': update.effective_user.username or update.effective_user.full_name or str(user_id),
        'payment_method': payment_method
    }

    # Уведомление админам
    for admin in ADMINS:
        try:
            await context.bot.send_message(
                chat_id=admin,
                text=(
                    f"🟢 <b>Новая заявка на пополнение</b>\n"
                    f"💳 Метод: <b>{payment_method}</b>\n"
                    f"👤 Пользователь: {update.effective_user.full_name}\n"
                    f"🔗 @{update.effective_user.username}\n"
                    f"🆔 ID: <code>{user_id}</code>\n"
                    f"💰 Сумма: <b>{amount:.2f} RUB</b>"
                ),
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ Подтвердить", callback_data=f"topup_confirm:{user_id}"),
                        InlineKeyboardButton("❌ Отклонить", callback_data=f"topup_cancel:{user_id}")
                    ]
                ]),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления админу {admin}: {e}")

    # Сообщение пользователю
    await update.message.reply_text(
        f"✅ Заявка на пополнение на {amount:.2f} RUB создана!\n\n"
        f"Способ оплаты: <b>{payment_method}</b>\n\n"
        "⏳ <b>Заявка будет рассмотрена администрацией в течение 30 минут</b>\n\n"
        "ℹ️ После оплаты ожидайте подтверждения.",
        reply_markup=main_keyboard,
        parse_mode="HTML"
    )

    return ConversationHandler.END


async def crypto_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Просто перенаправляем в topup_amount, так как логика теперь единая
    return await topup_amount(update, context)


async def withdraw_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Проверка активных заявок
    active_withdrawals = any(req['user_id'] == user_id for req in pending_withdrawals.values())
    if active_withdrawals:
        await update.message.reply_text(
            "❗ У вас уже есть активная заявка на вывод.",
            reply_markup=main_keyboard
        )
        return ConversationHandler.END

    # Устанавливаем начальное состояние
    context.user_data['withdraw_state'] = WAIT_WITHDRAW_METHOD

    await update.message.reply_text(
        "💸 Выберите способ вывода:\n\n"
        "💳 Банковская карта (мин. 100 RUB)\n"
        "📱 СБП (мин. 100 RUB)\n"
        "₿ Криптовалюта (мин. 500 RUB)",
        reply_markup=ReplyKeyboardMarkup(
            [
                ["💳 Банковская карта", "📱 СБП"],
                ["₿ Криптовалюта", "❌ Отмена"]
            ],
            resize_keyboard=True
        )
    )
    return WAIT_WITHDRAW_METHOD


async def select_withdraw_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if text == "❌ Отмена":
        return await cancel_operation(update, context)

    if text not in ["💳 Банковская карта", "📱 СБП", "₿ Криптовалюта"]:
        await update.message.reply_text(
            "Пожалуйста, выберите способ вывода из предложенных кнопок",
            reply_markup=ReplyKeyboardMarkup(
                [["💳 Банковская карта", "📱 СБП"],
                 ["₿ Криптовалюта", "❌ Отмена"]],
                resize_keyboard=True
            )
        )
        return WAIT_WITHDRAW_METHOD

    context.user_data["withdraw_method"] = text
    context.user_data['withdrawal_state'] = WAIT_WITHDRAW_AMOUNT

    await update.message.reply_text(
        f"💸 Введите сумму для вывода ({text}):",
        reply_markup=ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True)
    )
    return WAIT_WITHDRAW_AMOUNT


async def withdraw_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip() == "❌ Отмена":
        await cancel_operation(update, context)
        return ConversationHandler.END

    try:
        amount = float(update.message.text.replace(",", "."))
        if amount <= 0:
            raise ValueError("Сумма должна быть положительной")

        # Проверка минимальной суммы для выбранного метода
        method = context.user_data.get("withdraw_method", "").lower()
        if "карт" in method and amount < 100:
            raise ValueError("Минимальная сумма для карты: 100 RUB")
        if "сбп" in method and amount < 100:
            raise ValueError("Минимальная сумма для СБП: 100 RUB")
        if "крипт" in method and amount < 500:
            raise ValueError("Минимальная сумма для крипты: 500 RUB")

        if amount > users[update.effective_user.id]["balance"]:
            raise ValueError(f"Недостаточно средств. Баланс: {users[update.effective_user.id]['balance']:.2f} RUB")

    except ValueError as e:
        await update.message.reply_text(
            f"❌ {str(e)}\n\nВведите сумму заново или нажмите '❌ Отмена':",
            reply_markup=ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True)
        )
        return WAIT_WITHDRAW_AMOUNT

    context.user_data["withdraw_amount"] = amount
    await update.message.reply_text(
        "📝 Введите реквизиты для получения (номер карты/телефона/крипто-кошелька):",
        reply_markup=ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True)
    )
    return WAIT_REQUISITES


async def select_payment_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    cancel_keyboard = ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True)
    if text == "❌ Отмена":
        return await cancel_operation(update, context)
    elif text == "🔙 на главную":
        return await cancel_operation(update, context)
    context.user_data['payment_method'] = text

    if text == "💳 Банковская карта":
        await update.message.reply_text(
            "💳 <b>Реквизиты для оплаты картой</b>:\n\n"
            "🏦 Банк: Тинькофф\n"
            "📤 Номер карты: <code>5536 9137 2845 9012</code>\n"
            "👤 Получатель: Алексей Петров\n\n"
            "✅ После оплаты ожидайте подтверждения.\n"
            "Обычно это занимает до 15 минут.\n\n"
            "💸 Теперь введите сумму пополнения в RUB:",
            reply_markup=cancel_keyboard,
            parse_mode="HTML"
        )
        return WAIT_TOPUP_AMOUNT

    elif text == "📱 СБП":
        await update.message.reply_text(
            "📱 <b>Реквизиты для оплаты по СБП</b>:\n\n"
            "📱 Номер телефона: <code>+79123456789</code>\n"
            "👤 Получатель: Иван Иванов\n\n"
            "✅ После оплаты ожидайте подтверждения.\n"
            "Обычно это занимает до 5 минут.\n\n"
            "💸 Теперь введите сумму пополнения в RUB:",
            reply_markup=cancel_keyboard,
            parse_mode="HTML"
        )
        return WAIT_TOPUP_AMOUNT

    elif text == "₿ Криптовалюта":
        await update.message.reply_text(
            "₿ <b>Реквизиты для оплаты криптовалютой</b>:\n\n"
            "🔷 Криптовалюта: USDT TRC20\n"
            "📮 Адрес кошелька: <code>TBvZ1K4bLjLQ9Q7x8Jz3kPqA2nW5rRtYy</code>\n\n"
            "⚠️ Внимание:\n"
            "1. Отправляйте только USDT\n"
            "2. Используйте только сеть TRC20\n"
            "3. Подтверждение занимает до 30 минут\n\n"
            "💸 Теперь введите сумму пополнения в RUB:",
            reply_markup=cancel_keyboard,
            parse_mode="HTML"
        )
        return WAIT_CRYPTO_AMOUNT


async def withdraw_requisites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if text == "❌ Отмена":
        await cancel_operation(update, context)
        return ConversationHandler.END

    if len(text) < 5:
        await update.message.reply_text(
            "❌ Слишком короткие реквизиты. Введите корректные данные:",
            reply_markup=ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True)
        )
        return WAIT_REQUISITES

    amount = context.user_data.get("withdraw_amount")
    method = context.user_data.get("withdraw_method")

    if not amount or not method:
        await update.message.reply_text(
            "⚠️ Ошибка данных. Начните процесс вывода заново.",
            reply_markup=main_keyboard
        )
        return ConversationHandler.END

    request_id = f"{user_id}_{datetime.now().timestamp()}"
    pending_withdrawals[request_id] = {
        "user_id": user_id,
        "amount": amount,
        "method": method,
        "requisites": text,
        "timestamp": datetime.now().isoformat(),
        "username": users[user_id].get('username', f'user_{user_id}')
    }

    await update.message.reply_text(
        "✅ Заявка на вывод создана!\n\n"
        "⏳ Обычно обработка занимает до 1 часа.\n"
        "Вы получите уведомление, когда средства будут отправлены.",
        reply_markup=main_keyboard
    )

    # Уведомление админам
    for admin in ADMINS:
        try:
            await context.bot.send_message(
                chat_id=admin,
                text=(
                    f"🔴 Новая заявка на вывод\n"
                    f"👤 {update.effective_user.full_name} (@{update.effective_user.username})\n"
                    f"🆔 ID: {user_id}\n"
                    f"💸 Сумма: {amount:.2f} RUB\n"
                    f"📝 Метод: {method}\n"
                    f"🔑 Реквизиты: {text}\n"
                    f"🆔 Заявка: {request_id}"
                ),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ Подтвердить", callback_data=f"withdraw_confirm:{request_id}"),
                    InlineKeyboardButton("❌ Отклонить", callback_data=f"withdraw_cancel:{request_id}")
                ]])
            )
        except Exception as e:
            logger.error(f"Ошибка уведомления админа {admin}: {e}")

    return ConversationHandler.END


async def unified_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    logger.info(f"Callback received: {data} from user {query.from_user.id}")

    try:
        # Обработка кнопки "Партнерская программа" (доступно всем)
        if data == "show_ref_stats":
            await referral_stats(query, context)
            await query.edit_message_reply_markup(reply_markup=None)
            return

        elif data == "help_with_bot":
            await help_command(query, context)
            await query.edit_message_reply_markup(reply_markup=None)
            return

        # Проверка прав администратора для остальных действий
        if query.from_user.id not in ADMINS and query.message.chat.id not in ADMINS:
            logger.warning(f"Unauthorized admin attempt from {query.from_user.id}")
            await query.answer("❌ У вас нет прав для этого действия", show_alert=True)
            return

        # Обработка админских действий
        elif data.startswith("topup_confirm:"):
            user_id = int(data.split(":")[1])
            request = pending_topups.get(user_id)

            if not request:
                logger.warning(f"Topup request not found for user {user_id}")
                await query.edit_message_text("⚠️ Заявка не найдена или уже обработана")
                return

            amount = request['amount']

            if user_id not in users:
                users[user_id] = {
                    'balance': 0.0,
                    'deposits': [],
                    'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'username': request.get('username', f'user_{user_id}'),
                    'referrer_id': None,
                    'referral_level': 1
                }

            users[user_id]["balance"] += amount
            save_user(user_id)
            pending_topups.pop(user_id, None)

            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"✅ Ваш баланс пополнен на {amount:.2f} RUB!\n\n"
                         f"💰 Текущий баланс: {users[user_id]['balance']:.2f} RUB"
                )
            except Exception as e:
                logger.error(f"Error notifying user {user_id}: {e}")

            await query.edit_message_text(
                f"🟢 Пополнение подтверждено\n"
                f"👤 Пользователь: {request.get('username', 'N/A')}\n"
                f"🆔 ID: {user_id}\n"
                f"💳 Сумма: {amount:.2f} RUB\n"
                f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}"
            )

        elif data.startswith("topup_cancel:"):
            user_id = int(data.split(":")[1])
            request = pending_topups.get(user_id)

            if not request:
                logger.warning(f"Topup request not found for user {user_id} (cancel)")
                await query.edit_message_text("⚠️ Заявка не найдена или уже обработана")
                return

            pending_topups.pop(user_id, None)
            logger.info(f"Topup canceled for user {user_id}, amount: {request['amount']}")

            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="❌ Ваша заявка на пополнение была отклонена администратором.\n\n"
                         "ℹ️ Если вы считаете это ошибкой, свяжитесь с поддержкой."
                )
            except Exception as e:
                logger.error(f"Error notifying user {user_id}: {e}")

            await query.edit_message_text(
                f"🔴 Пополнение отклонено\n"
                f"👤 Пользователь: {request.get('username', 'N/A')}\n"
                f"🆔 ID: {user_id}\n"
                f"💳 Сумма: {request['amount']:.2f} RUB\n"
                f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}"
            )

        elif data.startswith("withdraw_confirm:"):
            request_id = data.split(":")[1]
            req = pending_withdrawals.get(request_id)

            if not req:
                logger.warning(f"Withdrawal request not found: {request_id}")
                await query.edit_message_text("⚠️ Заявка не найдена или уже обработана")
                return

            user_id = req["user_id"]
            amount = req["amount"]
            logger.info(f"Processing withdraw confirm for user {user_id}, amount: {amount}")

            if user_id not in users:
                users[user_id] = {
                    'balance': 0.0,
                    'deposits': [],
                    'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'username': req.get('username', f'user_{user_id}'),
                    'referrer_id': None,
                    'referral_level': 1
                }

            if users[user_id]["balance"] >= amount:
                users[user_id]["balance"] -= amount
                save_user(user_id)
                pending_withdrawals.pop(request_id, None)

                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"✅ Ваша заявка на вывод {amount:.2f} RUB подтверждена!\n\n"
                             f"📝 Реквизиты: {req['requisites']}\n"
                             f"⏳ Средства будут отправлены в течение 1 часа.\n\n"
                             f"💰 Остаток баланса: {users[user_id]['balance']:.2f} RUB"
                    )
                except Exception as e:
                    logger.error(f"Error notifying user {user_id}: {e}")

                await query.edit_message_text(
                    f"🟢 Вывод подтвержден\n"
                    f"👤 {req.get('username', 'N/A')}\n"
                    f"🆔 {user_id}\n"
                    f"💸 Сумма: {amount:.2f} RUB\n"
                    f"📝 Реквизиты: {req['requisites']}\n"
                    f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}"
                )
            else:
                await query.edit_message_text(
                    f"⚠️ Недостаточно средств у пользователя\n"
                    f"👤 {req.get('username', 'N/A')}\n"
                    f"🆔 {user_id}\n"
                    f"💸 Запрошено: {amount:.2f} RUB\n"
                    f"💰 Имеется: {users[user_id]['balance']:.2f} RUB"
                )

        elif data.startswith("withdraw_cancel:"):
            request_id = data.split(":")[1]
            req = pending_withdrawals.get(request_id)

            if not req:
                logger.warning(f"Withdrawal request not found: {request_id} (cancel)")
                await query.edit_message_text("⚠️ Заявка не найдена или уже обработана")
                return

            pending_withdrawals.pop(request_id, None)
            logger.info(f"Withdrawal canceled for request {request_id}")

            try:
                await context.bot.send_message(
                    chat_id=req["user_id"],
                    text=f"❌ Ваша заявка на вывод {req['amount']:.2f} RUB отклонена.\n\n"
                         "ℹ️ Причина: решение администратора\n\n"
                         "Если вы считаете это ошибкой, свяжитесь с поддержкой."
                )
            except Exception as e:
                logger.error(f"Error notifying user {req['user_id']}: {e}")

            await query.edit_message_text(
                f"🔴 Вывод отклонен\n"
                f"👤 {req.get('username', 'N/A')}\n"
                f"🆔 {req['user_id']}\n"
                f"💸 Сумма: {req['amount']:.2f} RUB\n"
                f"📝 Реквизиты: {req['requisites']}\n"
                f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}"
            )

        else:
            logger.warning(f"Unknown callback data: {data}")
            await query.answer("⚠️ Неизвестная команда")

    except Exception as e:
        logger.error(f"Error in callback handler: {e}", exc_info=True)
        await query.answer("⚠️ Произошла ошибка при обработке запроса")
        await query.edit_message_text(
            "⚠️ Произошла ошибка при обработке запроса\n"
            "Попробуйте еще раз или обратитесь к разработчику"
        )


async def update_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id

    users[chat_id]['username'] = user.username or user.full_name or str(chat_id)
    save_user(chat_id)

    await update.message.reply_text(
        "✅ Профиль обновлен!",
        reply_markup=main_keyboard
    )


async def calculator(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_photo(
        photo="https://keephere.ru/get/BssNEF71mGmzizU/o/photo_2_2025-07-25_12-14-28.jpg",
        # или путь к файлу: open("path.jpg", "rb")
        caption=f"""
💡 <b>Калькулятор доходности</b> 💡

🔢 <b>Введите сумму для расчета</b>  

Примеры:
• 1000
• 500.50
• 25000

💰 <i>Минимальная сумма: 100 ₽</i>
📈 <i>Доходность: 4% ежедневно</i>

Нажмите <b>"🔙 на главную"</b>, чтобы вернуться

🌟 <i>Узнайте, сколько сможете заработать!</i>
        """,
        reply_markup=back_to_main_keyboard,
        parse_mode=ParseMode.HTML
    )
    context.user_data["awaiting_calc"] = True


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    text_lower = text.lower()
    MIN_INVEST_AMOUNT = 10  # Минимальная сумма инвестиций

    # Инициализация пользователя
    if user_id not in users:
        users[user_id] = {
            "username": update.effective_user.username or update.effective_user.full_name or str(user_id),
            "balance": 0.0,
            "deposits": [],
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "last_activity": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        save_user(user_id)
    else:
        users[user_id]["last_activity"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_user(user_id)

        # Обработка состояния инвестирования
    if context.user_data.get('invest_state') == WAIT_INVEST_AMOUNT:
        if text_lower in ["отмена", "🔙 на главную"]:
            await cancel_operation(update, context)
            return ConversationHandler.END
        try:
            amount = float(text.replace(",", "."))
            if amount < MIN_INVEST_AMOUNT:
                await update.message.reply_text(
                    f"❌ Минимальная сумма инвестиций — {MIN_INVEST_AMOUNT} RUB\n"
                    f"Вы ввели: {amount:.2f} RUB\n\n"
                    "Пополните баланс или введите бóльшую сумму:",
                    reply_markup=ReplyKeyboardMarkup(
                        [["💳 Пополнить"], ["🔙 на главную"]],
                        resize_keyboard=True
                    ),
                    parse_mode="HTML"
                )
                return WAIT_INVEST_AMOUNT

            if amount > users[user_id]["balance"]:
                await update.message.reply_text(
                    f"❌ Недостаточно средств. Ваш баланс: {users[user_id]['balance']:.2f} RUB\n"
                    "Пополните баланс:",
                    reply_markup=ReplyKeyboardMarkup(
                        [["💳 Пополнить"], ["🔙 на главную"]],
                        resize_keyboard=True
                    ),
                    parse_mode="HTML"
                )
                return WAIT_INVEST_AMOUNT

            # Успешное инвестирование
            add_deposit(user_id, amount)
            users[user_id]["balance"] -= amount
            save_user(user_id)
            context.user_data.clear()

            await update.message.reply_text(
                f"✅ Успешно инвестировано: {amount:.2f} RUB\n"
                f"💼 Общий вклад: {sum(d['amount'] for d in users[user_id]['deposits']):.2f} RUB\n"
                f"💰 Остаток: {users[user_id]['balance']:.2f} RUB",
                reply_markup=deposit_keyboard,
                parse_mode="HTML"
            )
            logger.info(f"Вызываем process_referral_bonuses для {user_id} с суммой {amount}")
            await (process_referral_bonuses(user_id, amount, context))
            return ConversationHandler.END

        except ValueError:
            await update.message.reply_text(
                f"❌ Неверный формат суммы. Минимум — {MIN_INVEST_AMOUNT} RUB\n"
                "Пример: 10 или 50.5\n"
                "Попробуйте снова:",
                reply_markup=ReplyKeyboardMarkup(
                    [["💳 Пополнить"], ["🔙 на главную"]],
                    resize_keyboard=True
                ),
                parse_mode="HTML"
            )
            return WAIT_INVEST_AMOUNT

        # Обработка команды "Инвестировать"
    elif text_lower in ["📥 инвестировать", "инвестировать", "вложить"]:
        user_balance = users[user_id]["balance"]

        if user_balance < MIN_INVEST_AMOUNT:
            context.user_data['invest_state'] = WAIT_INVEST_AMOUNT
            await update.message.reply_text(
                f"⚠️ <b>Минимальная сумма инвестиций — {MIN_INVEST_AMOUNT} RUB</b>\n"
                f"Ваш баланс: <b>{user_balance:.2f} RUB</b>\n\n"
                "Введите сумму от <b>10 RUB</b> или пополните баланс:",
                reply_markup=ReplyKeyboardMarkup(
                    [["💳 Пополнить"], ["🔙 на главную"]],
                    resize_keyboard=True
                ),
                parse_mode="HTML"
            )
            return WAIT_INVEST_AMOUNT
        else:
            context.user_data['invest_state'] = WAIT_INVEST_AMOUNT
            await update.message.reply_text(
                f"💸 <b>Введите сумму для инвестирования (от {MIN_INVEST_AMOUNT} RUB):</b>\n"
                f"Доступно: <b>{user_balance:.2f} RUB</b>\n"
                "Или нажмите <b>«🔙 на главную»</b> для отмены:",
                reply_markup=back_to_main_keyboard,
                parse_mode="HTML"
            )
            return WAIT_INVEST_AMOUNT

    # Обработка состояния вывода средств
    if 'withdraw_state' in context.user_data:
        current_state = context.user_data['withdraw_state']

        if current_state == WAIT_WITHDRAW_METHOD:
            if text in ["💳 Банковская карта", "📱 СБП", "₿ Криптовалюта"]:
                context.user_data['withdraw_method'] = text
                context.user_data['withdraw_state'] = WAIT_WITHDRAW_AMOUNT
                min_amount = 500 if text == "₿ Криптовалюта" else 100

                await update.message.reply_text(
                    f"💸 Введите сумму для вывода ({text}, мин. {min_amount} RUB):\n"
                    "Или нажмите '❌ Отмена' для возврата",
                    reply_markup=ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True),
                    parse_mode="HTML"
                )
                return WAIT_WITHDRAW_AMOUNT

            elif text == "❌ Отмена":
                await cancel_operation(update, context)
                return ConversationHandler.END

            else:
                await update.message.reply_text(
                    "❌ Пожалуйста, выберите способ вывода из предложенных вариантов:",
                    reply_markup=ReplyKeyboardMarkup(
                        [["💳 Банковская карта", "📱 СБП"],
                         ["₿ Криптовалюта", "❌ Отмена"]],
                        resize_keyboard=True
                    ),
                    parse_mode="HTML"
                )
                return WAIT_WITHDRAW_METHOD

        elif current_state == WAIT_WITHDRAW_AMOUNT:
            if text == "❌ Отмена":
                await cancel_operation(update, context)
                return ConversationHandler.END

            try:
                amount = float(text.replace(",", "."))
                method = context.user_data.get('withdraw_method', '')
                min_amount = 500 if "крипт" in method.lower() else 100

                if amount < min_amount:
                    await update.message.reply_text(
                        f"❌ Минимальная сумма для {method}: {min_amount} RUB\n"
                        "Введите сумму заново:",
                        reply_markup=ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True),
                        parse_mode="HTML"
                    )
                    return WAIT_WITHDRAW_AMOUNT

                if amount > users[user_id]["balance"]:
                    await update.message.reply_text(
                        f"❌ Недостаточно средств. Ваш баланс: {users[user_id]['balance']:.2f} RUB",
                        reply_markup=ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True),
                        parse_mode="HTML"
                    )
                    return WAIT_WITHDRAW_AMOUNT

                context.user_data['withdraw_amount'] = amount
                context.user_data['withdraw_state'] = WAIT_REQUISITES

                await update.message.reply_text(
                    "📝 Введите реквизиты для получения (номер карты/телефона/крипто-кошелька):\n"
                    "Или нажмите '❌ Отмена' для возврата",
                    reply_markup=ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True),
                    parse_mode="HTML"
                )
                return WAIT_REQUISITES

            except ValueError:
                await update.message.reply_text(
                    "❌ Введите корректную сумму (например: 1000 или 500.50)",
                    reply_markup=ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True),
                    parse_mode="HTML"
                )
                return WAIT_WITHDRAW_AMOUNT

        elif current_state == WAIT_REQUISITES:
            if text == "❌ Отмена":
                await cancel_operation(update, context)
                return ConversationHandler.END

            if len(text) < 5:
                await update.message.reply_text(
                    "❌ Слишком короткие реквизиты. Введите корректные данные:",
                    reply_markup=ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True),
                    parse_mode="HTML"
                )
                return WAIT_REQUISITES

            # Создание заявки на вывод
            withdraw_amount = context.user_data['withdraw_amount']
            withdraw_method = context.user_data['withdraw_method']
            username = update.effective_user.username or update.effective_user.full_name

            request_id = f"{user_id}_{datetime.now().timestamp()}"
            pending_withdrawals[request_id] = {
                "user_id": user_id,
                "amount": withdraw_amount,
                "method": withdraw_method,
                "requisites": text,
                "timestamp": datetime.now().isoformat(),
                "username": username
            }

            context.user_data.clear()

            await update.message.reply_text(
                "✅ Заявка на вывод создана!\n\n"
                "⏳ Обычно обработка занимает до 1 часа.\n"
                "Вы получите уведомление, когда средства будут отправлены.",
                reply_markup=main_keyboard,
                parse_mode="HTML"
            )

            # Уведомление админам
            for admin in ADMINS:
                try:
                    await context.bot.send_message(
                        chat_id=admin,
                        text=f"🔴 Новая заявка на вывод\n"
                             f"👤 Пользователь: {username}\n"
                             f"🆔 ID: {user_id}\n"
                             f"💸 Сумма: {withdraw_amount:.2f} RUB\n"
                             f"📝 Метод: {withdraw_method}\n"
                             f"🔑 Реквизиты: {text}\n"
                             f"🆔 Заявка: {request_id}",
                        reply_markup=InlineKeyboardMarkup([
                            [
                                InlineKeyboardButton("✅ Подтвердить", callback_data=f"withdraw_confirm:{request_id}"),
                                InlineKeyboardButton("❌ Отклонить", callback_data=f"withdraw_cancel:{request_id}")
                            ]
                        ]),
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Ошибка уведомления админа {admin}: {e}")

            return ConversationHandler.END

    # Обработка калькулятора
    if context.user_data.get("awaiting_calc"):
        if text_lower in ["отмена", "🔙 на главную"]:
            context.user_data.clear()
            await update.message.reply_text(
                "❌ Расчет отменен. Возврат в главное меню.",
                reply_markup=main_keyboard,
                parse_mode="HTML"
            )
            return ConversationHandler.END

        try:
            amount = float(text.replace(",", "."))
            if amount <= 0:
                raise ValueError("Сумма должна быть положительной")

            hourly = amount * 0.00166
            daily = amount * 0.04
            weekly = amount * 0.28
            monthly = amount * 1.2

            example = ""
            if amount >= 1000:
                example = f"\n\n💡 Пример: при вкладе {amount:.0f} RUB\n" \
                          f"За месяц вы получите ~{monthly:.0f} RUB прибыли"

            await update.message.reply_text(
                f"📊 <b>Расчет доходности</b> для {amount:.2f} RUB:\n\n"
                f"⏱ <b>В час:</b> {hourly:.2f} RUB\n"
                f"🌞 <b>В день:</b> {daily:.2f} RUB\n"
                f"📅 <b>В неделю:</b> {weekly:.2f} RUB\n"
                f"🗓 <b>В месяц (30 дней):</b> {monthly:.2f} RUB"
                f"{example}\n\n"
                "ℹ️ Расчет основан на ставке 4% в день\n"
                "Доходность начисляется ежечасно",
                reply_markup=main_keyboard,
                parse_mode="HTML"
            )
            context.user_data.clear()
        except ValueError:
            await update.message.reply_text(
                "❌ Введите корректную сумму в RUB (например: 5000 или 1250.50)",
                reply_markup=back_to_main_keyboard,
                parse_mode="HTML"
            )
        return ConversationHandler.END

    # Обработка возврата в главное меню
    if text_lower == "🔙 на главную":
        await cancel_operation(update, context)
        return ConversationHandler.END

    # Основные команды меню
    if text_lower in ["💼 кошелёк", "кошелёк", "баланс"]:
        await wallet_menu(update, context)
        return ConversationHandler.END

    elif text_lower in ["📈 калькулятор", "калькулятор", "расчет"]:
        context.user_data["awaiting_calc"] = True
        await calculator(update, context)
        return WAIT_CALC_AMOUNT

    elif text_lower in ["ℹ️ о проекте", "о проекте", "информация"]:
        await about_project(update, context)
        return ConversationHandler.END

    elif text_lower in ["📈 депозит", "депозит", "вклад"]:
        await show_deposit_info(update, context)
        return ConversationHandler.END

    elif text_lower in ["📤 собрать прибыль", "собрать", "забрать"]:
        await collect_profit(update, context)
        return ConversationHandler.END

    elif text_lower in ["💳 пополнить", "пополнить"]:
        if user_id in pending_topups:
            await update.message.reply_text(
                "❗ У вас уже есть активная заявка на пополнение.",
                reply_markup=ReplyKeyboardMarkup([["❌ Отменить операцию"], ["🔙 на главную"]], resize_keyboard=True),
                parse_mode="HTML"
            )
        else:
            await topup_start(update, context)
        return WAIT_PAYMENT_METHOD

    elif text_lower in ["💸 вывести", "вывести", "вывод"]:
        active_withdrawals = any(req['user_id'] == user_id for req in pending_withdrawals.values())
        if active_withdrawals:
            await update.message.reply_text(
                "❗ У вас уже есть активная заявка на вывод.",
                reply_markup=main_keyboard,
                parse_mode="HTML"
            )
        else:
            context.user_data['withdraw_state'] = WAIT_WITHDRAW_METHOD
            await update.message.reply_text(
                "💸 Выберите способ вывода:\n\n"
                "💳 Банковская карта (мин. 100 RUB)\n"
                "📱 СБП (мин. 100 RUB)\n"
                "₿ Криптовалюта (мин. 500 RUB)",
                reply_markup=ReplyKeyboardMarkup(
                    [
                        ["💳 Банковская карта", "📱 СБП"],
                        ["₿ Криптовалюта", "❌ Отмена"]
                    ],
                    resize_keyboard=True
                ),
                parse_mode="HTML"
            )
        return WAIT_WITHDRAW_METHOD

    # Обработка неизвестных команд
    await update.message.reply_text(
        "🔍 Я не распознал команду. Вот что я умею:\n\n"
        "💼 <b>Кошелек</b> - управление балансом\n"
        "📈 <b>Депозит</b> - инвестиции и прибыль\n"
        "📊 <b>Калькулятор</b> - расчет доходности\n"
        "ℹ️ <b>О проекте</b> - информация о боте\n\n"
        "Выберите действие на клавиатуре ниже 👇",
        reply_markup=main_keyboard,
        parse_mode="HTML"
    )
    return ConversationHandler.END


async def about_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Создаем инлайн-кнопки ПОД сообщением
    buttons = [
        [InlineKeyboardButton("💬 Официальный чат", url="https://t.me/tonstocketchat")],
        [InlineKeyboardButton("🛠 Персональный менеджер", url="https://t.me/g0dqq")],
        [InlineKeyboardButton("🎓 Обучение", callback_data="help_with_bot"),
         InlineKeyboardButton("💰 Партнерская программа", callback_data="show_ref_stats")]
    ]
    reply_markup = InlineKeyboardMarkup(buttons)

    about_text = """
🟦 <b>Ton Stocker </b> - Ваш надежный инструмент для пассивного дохода! 🟦

🔹 <b>Ежедневные выплаты 4%</b> - стабильный доход без скрытых условий
🔹 <b>Автоматические начисления</b> - прибыль рассчитывается ежечасно

📈 <b>Почему выбирают нас?</b>

✅ <b>Простота использования</b> - интуитивно понятный интерфейс
✅ <b>Быстрый старт</b> - минимальный депозит всего 100 RUB
✅ <b>Гибкие условия</b> - выводите прибыль в любое время

💎 <b>Наши возможности:</b>
- Инвестирование в RUB
- 3-уровневая реферальная программа
- Мгновенные уведомления о операциях
- Круглосуточная поддержка

🔐 <b>Ваши инвестиции под защитой:</b>
- Безопасное хранение данных
- Регулярное резервное копирование
- Стабильная работа системы

📲 <b>Как начать?</b>
1. Пополните баланс от 100 RUB
2. Инвестируйте в проект
3. Получайте стабильный доход 4% в день
    """

    await update.message.reply_photo(
        photo="https://keephere.ru/get/Kd1NEF71qtNuHGW/o/photo_3_2025-07-25_12-14-28.jpg",
        caption=about_text,
        reply_markup=reply_markup,
        parse_mode="HTML"
    )


async def collect_profit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = users[user_id]

    total_profit = 0
    referral_profit = 0

    logger.info(f"Сбор прибыли для {user_id}. Депозиты: {user.get('deposits')}")

    for deposit in user.get("deposits", []):
        # Обычная прибыль
        if 'start' in deposit and 'amount' in deposit:
            start_time = datetime.strptime(deposit['start'], "%Y-%m-%d %H:%M:%S")
            elapsed = datetime.now() - start_time
            elapsed_hours = elapsed.total_seconds() / 3600
            profit = deposit['amount'] * 0.00166 * elapsed_hours - deposit.get('collected_profit', 0)
            total_profit += max(0, profit)
            deposit['collected_profit'] = deposit.get('collected_profit', 0) + profit

        # Реферальная прибыль
        if deposit.get('is_referral', False):
            profit = deposit.get('referral_profit', 0) - deposit.get('collected_referral', 0)
            referral_profit += profit
            deposit['collected_referral'] = deposit.get('referral_profit', 0)

    total_profit += referral_profit

    if total_profit <= 0:
        await update.message.reply_text("ℹ️ Нет доступной прибыли для сбора.")
        return

    user['balance'] += total_profit
    save_user(user_id)

    await update.message.reply_text(
        f"💰 Выведено {total_profit:.2f} RUB!\n"
        f"💼 Из них реферальные бонусы: {referral_profit:.2f} RUB\n"
        f"💳 Текущий баланс: {user['balance']:.2f} RUB",
        reply_markup=deposit_keyboard
    )


async def forum_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💬 <b>Официальный форум Ton Stocket</b>\n\n"
        "Присоединяйтесь к нашему сообществу:\n"
        "🌐 forum.tonstocket.com\n\n"
        "Здесь вы найдете:\n"
        "- Последние новости проекта\n"
        "- Обсуждение стратегий\n"
        "- Ответы на частые вопросы",
        parse_mode="HTML"
    )


async def support_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛠 <b>Техническая поддержка</b>\n\n"
        "По всем вопросам обращайтесь:\n"
        "👨‍💻 @TonSucketSupport\n"
        "📧 support@tonstocket.com\n\n"
        "⌚ Режим работы: 24/7\n"
        "⏱ Среднее время ответа: 15 минут",
        parse_mode="HTML"
    )


async def process_referral_bonuses(investor_id: int, amount: float, context: ContextTypes.DEFAULT_TYPE):
    """Начисление реферальных бонусов при инвестировании"""
    logger.info(f"Начало process_referral_bonuses для {investor_id}")

    if investor_id not in users:
        logger.error(f"Инвестор {investor_id} не найден")
        return

    # Получаем цепочку рефералов
    chain = []
    current_id = investor_id
    for level in range(1, 4):  # Максимум 3 уровня
        referrer_id = users[current_id].get('referrer_id')
        if not referrer_id or referrer_id not in users:
            break

        chain.append((referrer_id, level))
        current_id = referrer_id

    logger.info(f"Найдена реферальная цепочка: {chain}")

    # Начисляем бонусы
    for referrer_id, level in chain:
        try:
            # Проценты по уровням
            percent = [0.20, 0.03, 0.01][level - 1]
            bonus = round(amount * percent, 2)

            logger.info(f"Начисляем бонус {bonus} RUB для {referrer_id} (уровень {level})")

            # Создаем или находим депозит для бонусов
            if 'deposits' not in users[referrer_id]:
                users[referrer_id]['deposits'] = []

            bonus_deposit = None
            for d in users[referrer_id]['deposits']:
                if d.get('is_referral', False):
                    bonus_deposit = d
                    break

            if not bonus_deposit:
                bonus_deposit = {
                    'amount': 0,
                    'start': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'is_referral': True,
                    'referral_profit': 0,
                    'collected_referral': 0
                }
                users[referrer_id]['deposits'].append(bonus_deposit)

            bonus_deposit['referral_profit'] += bonus
            save_user(referrer_id)

            logger.info(f"Бонус успешно начислен для {referrer_id}")

            try:
                await context.bot.send_message(
                    chat_id=referrer_id,
                    text=f"💎 Реферальный бонус {level}-го уровня!\n"
                         f"💰 +{bonus:.2f} RUB\n"
                         f"💼 Доступно в разделе «Собрать прибыль»"
                )
            except Exception as e:
                logger.error(f"Ошибка уведомления: {e}")

        except Exception as e:
            logger.error(f"Ошибка начисления бонуса: {e}")

    logger.info(f"Завершение process_referral_bonuses для {investor_id}")


async def partners_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤝 <b>Партнерская программа</b>\n\n"
        "Зарабатывайте до 20% с депозитов:\n"
        "1 уровень - 20%\n"
        "2 уровень - 3%\n"
        "3 уровень - 1%\n\n"
        "🔗 Ваша реферальная ссылка:\n"
        f"https://t.me/{(await context.bot.get_me()).username}?start=ref_{update.effective_user.id}",
        parse_mode="HTML"
    )


async def show_deposit_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = users[user_id]
    deposits = user.get("deposits", [])
    total_invested = sum(d["amount"] for d in deposits)
    current_profit = calculate_current_profit(deposits)

    photo = "https://keephere.ru/get/NItNEF71gih9a1R/o/photo_1_2025-07-25_12-14-28.jpg"
    text = f"""
🌟 <b>Ваш инвестиционный доход</b> 🌟

<b>📊 Условия инвестирования</b>  

🏆 <b>Доходность:</b> 4% в сутки
⏳ <b>Начисления:</b> каждый час
📅 <b>Срок действия:</b> 60 дней

<b>💼 Ваши инвестиции</b>

💰 <b>Общий вклад:</b> {total_invested:.2f}₽
📈 <b>Накопленная прибыль:</b> {current_profit:.2f}₽

💡 <i>Доступно для вывода в любое время</i>
✨ <i>Ваши деньги работают на вас 24/7</i>


🚀 <b>Увеличивайте капитал - повышайте доход!</b>
    """

    message = await update.message.reply_photo(
        photo=photo,
        caption=text,
        reply_markup=deposit_keyboard,
        parse_mode=ParseMode.HTML
    )

    # Сохраняем ID сообщения для обновления
    user["last_deposit_msg_id"] = message.message_id

    # Останавливаем предыдущее обновление если было
    if context.job_queue and f"depositupdate{user_id}" in context.job_queue.jobs():
        context.job_queue.jobs()[f"depositupdate{user_id}"].schedule_removal()

    # Запускаем автообновление каждую минуту
    context.job_queue.run_repeating(
        callback=lambda ctx: update_deposit_message(ctx, user_id),
        interval=60.0,
        first=0,
        name=f"deposit_update_{user_id}"
    )


async def invest_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    try:
        amount = float(text.replace(",", "."))
        if amount <= 0:
            raise ValueError("Сумма должна быть положительной")

        if amount < MIN_INVEST_AMOUNT:
            await update.message.reply_text(
                f"Минимальная сумма инвестиции: {MIN_INVEST_AMOUNT} RUB",
                reply_markup=main_keyboard
            )
            return WAIT_INVEST_AMOUNT

        if amount > users[user_id]["balance"]:
            await update.message.reply_text(
                f"Недостаточно средств. Ваш баланс: {users[user_id]['balance']:.2f} RUB",
                reply_markup=main_keyboard
            )
            return WAIT_INVEST_AMOUNT

        # Создаем депозит
        add_deposit(user_id, amount)
        users[user_id]["balance"] -= amount
        save_user(user_id)

        logger.info(f"Завершили process_referral_bonuses для {user_id}")

        await update.message.reply_text(
            f"✅ Инвестировано {amount:.2f} RUB\n"
            f"💼 Доход начнет начисляться сразу",
            reply_markup=deposit_keyboard
        )

        return ConversationHandler.END

    except ValueError:
        await update.message.reply_text(
            "Введите корректную сумму",
            reply_markup=main_keyboard
        )
        return WAIT_INVEST_AMOUNT


def add_deposit(user_id, amount):
    now = datetime.now()
    deposit = {
        "amount": amount,
        "start": now.strftime("%Y-%m-%d %H:%M:%S"),
        "last_profit": now.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_days": 60,
        "referral_profit": 0,
        "collected_referral": 0
    }

    if user_id not in users:
        users[user_id] = {
            "username": f"user_{user_id}",
            "balance": 0,
            "deposits": [],
            "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "referrer_id": None,
            "referral_level": 1,
            "referrals": []
        }

    users[user_id]["deposits"].append(deposit)


async def invest_prepare(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_balance = users.get(user_id, {}).get("balance", 0)

    # Если баланс меньше 10 RUB — предлагаем только пополнение
    if user_balance < 10:
        keyboard = ReplyKeyboardMarkup(
            [["💳 Пополнить"], ["🔙 на главную"]],
            resize_keyboard=True
        )
        await update.message.reply_text(
            "⚠️ *Минимальная сумма инвестиций — 10 RUB.*\n"
            f"Ваш баланс: *{user_balance:.2f} RUB*\n\n"
            "Пополните баланс, чтобы начать:",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    # Если денег хватает — запрашиваем сумму
    context.user_data['invest_state'] = WAIT_INVEST_AMOUNT
    await update.message.reply_text(
        f"💸 *Введите сумму для инвестирования (от 10 RUB):*\n"
        f"Доступно: *{user_balance:.2f} RUB*\n"
        "Или нажмите *'🔙 на главную'* для отмены:",
        reply_markup=back_to_main_keyboard,
        parse_mode="Markdown"
    )
    return WAIT_INVEST_AMOUNT


def load_user_from_db(user_id):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT id, username, balance, deposits, created_at, referrer_id, referral_level, referrals_count 
            FROM users WHERE id = ?
        """, (user_id,))

        row = cursor.fetchone()
        if row:
            users[user_id] = {
                "username": row[1],
                "balance": float(row[2]),
                "deposits": json.loads(row[3] or "[]"),
                "created_at": row[4],
                "referrer_id": row[5],
                "referral_level": row[6] if row[6] else 1,
                "referrals_count": row[7] if row[7] else 0
            }
    except Exception as e:
        logger.error(f"Ошибка загрузки пользователя {user_id}: {e}")
    finally:
        conn.close()


async def check_refs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect("users.db")
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, username, referrals_count 
            FROM users 
            WHERE id = ? OR referrer_id = ?
        """, (user_id, user_id))

        rows = cursor.fetchall()
        if not rows:
            await update.message.reply_text("Данные не найдены")
            return

        response = "📊 Статистика рефералов:\n"
        for row in rows:
            response += f"👤 {row[1]} (ID: {row[0]}): {row[2]} рефералов\n"

        await update.message.reply_text(response)

    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")
    finally:
        conn.close()


def main():
    print(f"Admin chat ID: {ADMINS[0]}, type: {type(ADMINS[0])}")
    init_db()
    load_users()
    TOKEN = "7879007807:AAHGr3mBXCcd-VamRqQKj4CyY7F-YIKfpjw"

    application = Application.builder().token(TOKEN).build()
    # Основные команды (добавляются первыми)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("ref", referral_stats))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("update", update_profile))
    application.add_handler(CommandHandler("cancel", cancel_operation))  # Добавляем обработчик отмены
    application.add_handler(CallbackQueryHandler(unified_callback_handler))

    # В main() после других обработчиков текста, но перед ConversationHandler
    application.add_handler(MessageHandler(filters.Text(["📈 Депозит", "депозит", "вклад"]), show_deposit_info))
    application.add_handler(MessageHandler(filters.Text(["💼 Кошелёк", "кошелёк"]), wallet_menu))
    application.add_handler(MessageHandler(filters.Text(["🔢 Калькулятор", "калькулятор"]), calculator))
    application.add_handler(MessageHandler(filters.Text(["ℹ️ О проекте"]), about_project))

    # Обработчик возврата в главное меню (заменяем на прямую функцию)
    application.add_handler(MessageHandler(
        filters.Regex("(?i)^🔙 на главную$"),
        cancel_operation
    ))

    application.add_handler(CommandHandler("checkrefs", check_refs))

    # ConversationHandler для пополнения баланса
    topup_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r"(?i)^\s*💳?\s*пополнить\s*$"), topup_start)
        ],
        states={
            WAIT_PAYMENT_METHOD: [
                MessageHandler(filters.Text(["💳 Банковская карта", "📱 СБП", "₿ Криптовалюта"]), select_payment_method),
                MessageHandler(filters.Text(["❌ Отмена"]), cancel_operation),
                MessageHandler(filters.Text(["🔙 на главную"]), cancel_operation)
            ],
            WAIT_TOPUP_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, topup_amount),
                MessageHandler(filters.Text(["❌ Отмена"]), cancel_operation),
                MessageHandler(filters.Text(["🔙 на главную"]), cancel_operation)
            ],
            WAIT_CRYPTO_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, topup_amount),
                MessageHandler(filters.Text(["❌ Отмена"]), cancel_operation),
                MessageHandler(filters.Text(["🔙 на главную"]), cancel_operation)
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel_operation)
        ]
    )

    withdraw_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Text(["💸 Вывести", "вывести", "вывод"]), withdraw_start)
        ],
        states={
            WAIT_WITHDRAW_METHOD: [
                MessageHandler(
                    filters.Text(["💳 Банковская карта", "📱 СБП", "₿ Криптовалюта", "❌ Отмена"]),
                    select_withdraw_method
                ),
                # Добавляем обработчик для любых текстовых сообщений
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    lambda update, ctx: update.message.reply_text(
                        "Пожалуйста, выберите способ вывода из предложенных кнопок",
                        reply_markup=ReplyKeyboardMarkup(
                            [["💳 Банковская карта", "📱 СБП"],
                             ["₿ Криптовалюта", "❌ Отмена"]],
                            resize_keyboard=True
                        )
                    )
                )
            ],
            WAIT_WITHDRAW_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_amount),
                MessageHandler(filters.Text(["❌ Отмена"]), cancel_operation)
            ],
            WAIT_REQUISITES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_requisites),
                MessageHandler(filters.Text(["❌ Отмена"]), cancel_operation)
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel_operation),
            MessageHandler(filters.Text(["❌ Отмена"]), cancel_operation)
        ]
    )
    invest_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Text(["📥 Инвестировать", "инвестировать"]), invest_prepare)
        ],
        states={
            WAIT_INVEST_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text),
                MessageHandler(filters.Text(["🔙 на главную"]), cancel_operation)
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel_operation),
            MessageHandler(filters.Text(["🔙 на главную"]), cancel_operation)
        ]
    )

    application.add_handler(topup_handler)
    application.add_handler(withdraw_handler)
    application.add_handler(invest_handler)
    # Обработчик для всех остальных сообщений (должен быть самым последним)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    if os.environ.get('USE_WEBHOOK'):
        # Production mode - webhook
        webhook_url = os.environ.get('WEBHOOK_URL')
        application.run_webhook(
            listen="0.0.0.0",
            port=int(os.environ.get('WEBHOOK_PORT', 8443)),
            webhook_url=f"{webhook_url}/webhook/{TOKEN}",
        )
    else:
        # Development mode - polling
        application.run_polling()

    logger.info("Бот запускается...")
    application.run_polling()


async def cancel_operation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Очищаем все состояния и данные, связанные с инвестированием
    context.user_data.clear()

    # Удаляем задачу обновления депозита, если она есть
    user_id = update.effective_user.id
    if context.job_queue and f"depositupdate{user_id}" in context.job_queue.jobs():
        context.job_queue.jobs()[f"depositupdate{user_id}"].schedule_removal()

    await update.message.reply_text(
        "🏠 Вы вернулись в главное меню",
        reply_markup=main_keyboard
    )
    return ConversationHandler.END


async def handle_unknown_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка неизвестных команд"""
    if update.message:
        await update.message.reply_text(
            "🔍 Я не распознал команду. Пожалуйста, используйте кнопки меню.",
            reply_markup=main_keyboard
        )
    return ConversationHandler.END


if __name__ == "__main__":
    main()
