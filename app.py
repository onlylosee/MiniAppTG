from flask import Flask, jsonify, request, send_from_directory, render_template_string
from flask_cors import CORS
import sqlite3
import json
import os
import threading
import asyncio
from datetime import datetime
import logging

# Импорты для бота
import sys
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, \
    ContextTypes, filters
from telegram.constants import ParseMode

app = Flask(__name__)
CORS(app)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Глобальные переменные
users = {}
pending_topups = {}
pending_withdrawals = {}

BOT_TOKEN = "8455535012:AAF7Re7qBMAyPoNn-V-jNSpP1SiI94GCMW0"
ADMINS = [-1002562283915]
MIN_INVEST_AMOUNT = 10

# Создаем глобальные объекты для бота
bot_instance = None
application_instance = None

# Conversation states
WAIT_TOPUP_AMOUNT = 1
WAIT_WITHDRAW_AMOUNT = 2
WAIT_REQUISITES = 3
WAIT_PAYMENT_METHOD = 4
WAIT_INVEST_AMOUNT = 5
WAIT_WITHDRAW_METHOD = 6
WAIT_CRYPTO_AMOUNT = 7


# === ФУНКЦИИ БАЗЫ ДАННЫХ (те же что были) ===
def init_db():
    """Инициализация базы данных"""
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            balance REAL DEFAULT 0.0,
            deposits TEXT DEFAULT '[]',
            created_at TEXT,
            referrer_id INTEGER,
            referral_level INTEGER DEFAULT 1,
            referrals_count INTEGER DEFAULT 0
        )
    ''')

    conn.commit()
    conn.close()


def load_users():
    """Загрузка пользователей из базы"""
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()

    global users
    users.clear()

    try:
        cursor.execute('SELECT * FROM users')
        rows = cursor.fetchall()

        for row in rows:
            user_id = row[0]
            deposits_json = row[3] if row[3] else '[]'

            try:
                deposits = json.loads(deposits_json)
            except json.JSONDecodeError:
                deposits = []

            users[user_id] = {
                'username': row[1],
                'balance': float(row[2]) if row[2] else 0.0,
                'deposits': deposits,
                'created_at': row[4],
                'referrer_id': row[5],
                'referral_level': row[6] if row[6] else 1,
                'referrals_count': row[7] if row[7] else 0
            }

    except Exception as e:
        logger.error(f"Ошибка загрузки пользователей: {e}")
    finally:
        conn.close()


def save_user(user_id):
    """Сохранение пользователя в базу"""
    if user_id not in users:
        return

    user = users[user_id]
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()

    try:
        cursor.execute('''
            INSERT OR REPLACE INTO users 
            (id, username, balance, deposits, created_at, referrer_id, referral_level, referrals_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            user.get('username'),
            user.get('balance', 0.0),
            json.dumps(user.get('deposits', [])),
            user.get('created_at'),
            user.get('referrer_id'),
            user.get('referral_level', 1),
            user.get('referrals_count', 0)
        ))

        conn.commit()
    except Exception as e:
        logger.error(f"Ошибка сохранения пользователя {user_id}: {e}")
    finally:
        conn.close()


def add_deposit(user_id, amount):
    """Добавление депозита"""
    if user_id not in users:
        return False

    deposit = {
        'amount': amount,
        'start': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'collected_profit': 0,
        'status': 'active'
    }

    users[user_id]['deposits'].append(deposit)
    save_user(user_id)
    return True


def create_user_if_not_exists(user_id, username):
    """Создать пользователя если не существует"""
    if user_id not in users:
        users[user_id] = {
            'username': username,
            'balance': 0.0,
            'deposits': [],
            'created_at': datetime.now().strftime('%d.%m.%Y'),
            'referrer_id': None,
            'referral_level': 1,
            'referrals_count': 0
        }
        save_user(user_id)


# === API ФУНКЦИИ (те же что были) ===
def get_user_data_api(user_id):
    """Получить данные пользователя для API"""
    load_users()

    if user_id not in users:
        return None

    user = users[user_id]
    deposits = user.get('deposits', [])

    total_invested = sum(d.get('amount', 0) for d in deposits)
    current_profit = 0

    now = datetime.now()
    for deposit in deposits:
        if 'start' in deposit and deposit.get('status') == 'active':
            try:
                start_time = datetime.strptime(deposit['start'], '%Y-%m-%d %H:%M:%S')
                elapsed = now - start_time
                elapsed_hours = elapsed.total_seconds() / 3600

                hourly_profit = deposit['amount'] * 0.04 / 24
                profit = hourly_profit * elapsed_hours

                collected = deposit.get('collected_profit', 0)
                current_profit += max(0, profit - collected)

            except ValueError:
                continue

    referrals = get_referrals_by_levels_api(user_id)

    return {
        'user_id': user_id,
        'username': user.get('username', ''),
        'balance': user.get('balance', 0.0),
        'deposits': deposits,
        'total_invested': total_invested,
        'current_profit': current_profit,
        'deposits_count': len(deposits),
        'referrals': {
            'level1': len(referrals['level1']),
            'level2': len(referrals['level2']),
            'level3': len(referrals['level3'])
        }
    }


def get_referrals_by_levels_api(user_id):
    """Получить рефералов по уровням"""
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()

    level1 = []
    level2 = []
    level3 = []

    try:
        cursor.execute("SELECT id FROM users WHERE referrer_id = ?", (user_id,))
        level1 = [row[0] for row in cursor.fetchall()]

        for ref1_id in level1:
            cursor.execute("SELECT id FROM users WHERE referrer_id = ?", (ref1_id,))
            level2.extend([row[0] for row in cursor.fetchall()])

        for ref2_id in level2:
            cursor.execute("SELECT id FROM users WHERE referrer_id = ?", (ref2_id,))
            level3.extend([row[0] for row in cursor.fetchall()])

    except Exception as e:
        logger.error(f"Ошибка получения рефералов: {e}")
    finally:
        conn.close()

    return {
        'level1': level1,
        'level2': level2,
        'level3': level3
    }


# === FLASK ROUTES ===
@app.route('/')
def webapp():
    """Serve the web app"""
    try:
        with open('webapp/index.html', 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return "Web App not found", 404


@app.route('/api/user/<int:user_id>', methods=['GET'])
def get_user_info(user_id):
    """Получить информацию о пользователе"""
    try:
        user_data = get_user_data_api(user_id)
        if user_data:
            return jsonify({
                'success': True,
                'data': user_data
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Пользователь не найден'
            }), 404

    except Exception as e:
        logger.error(f"Ошибка API /user/{user_id}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    """Проверка работоспособности"""
    return jsonify({
        'success': True,
        'message': 'Сервер работает',
        'timestamp': datetime.now().isoformat(),
        'users_count': len(users)
    })


# === BOT HANDLERS ===
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.full_name

    create_user_if_not_exists(user_id, username)

    # Web App кнопка
    webapp_url = os.environ.get('RAILWAY_STATIC_URL', 'localhost:5000')
    if not webapp_url.startswith('http'):
        webapp_url = f"https://{webapp_url}"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Открыть приложение",
                              web_app=WebAppInfo(url=webapp_url))]
    ])

    await update.message.reply_text(
        "🌟 Добро пожаловать в TON STOCKER!\n\n"
        "💰 Стабильный доход 4% в день\n"
        "🚀 Откройте современное приложение:",
        reply_markup=keyboard
    )


async def webapp_data_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик данных от Web App"""
    try:
        web_app_data = json.loads(update.effective_message.web_app_data.data)
        user_id = update.effective_user.id
        action = web_app_data.get('action')

        if action == 'deposit':
            amount = web_app_data.get('amount', 0)
            method = web_app_data.get('method', '')

            await update.effective_message.reply_text(
                f"✅ Заявка на пополнение {amount} RUB создана!\n"
                f"Способ: {method}\n"
                f"Ожидайте подтверждения администратором."
            )

        elif action == 'withdraw':
            amount = web_app_data.get('amount', 0)
            requisites = web_app_data.get('requisites', '')

            if user_id in users and users[user_id]['balance'] >= amount:
                await update.effective_message.reply_text(
                    f"✅ Заявка на вывод {amount} RUB создана!"
                )
            else:
                await update.effective_message.reply_text(
                    "❌ Недостаточно средств на балансе"
                )

        elif action == 'invest':
            amount = web_app_data.get('amount', 0)

            if user_id in users and users[user_id]['balance'] >= amount:
                users[user_id]['balance'] -= amount
                add_deposit(user_id, amount)

                await update.effective_message.reply_text(
                    f"✅ Депозит {amount} RUB создан!\n"
                    f"Доходность: 4% в день"
                )
            else:
                await update.effective_message.reply_text(
                    "❌ Недостаточно средств на балансе"
                )

    except Exception as e:
        logger.error(f"Ошибка обработки webapp data: {e}")
        await update.effective_message.reply_text("❌ Произошла ошибка")


# === ИСПРАВЛЕННЫЙ WEBHOOK ===
@app.route(f'/webhook/{BOT_TOKEN}', methods=['POST'])
def webhook():
    """Webhook для бота"""
    try:
        json_data = request.get_json(force=True)
        update = Update.de_json(json_data, bot_instance)

        # Создаем новый event loop для обработки
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Обрабатываем update через application
        if application_instance:
            loop.run_until_complete(application_instance.process_update(update))

        loop.close()
        return 'OK'

    except Exception as e:
        logger.error(f"Ошибка webhook: {e}")
        return 'Error', 500


def run_bot():
    """Запуск бота"""
    global bot_instance, application_instance

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        # Создаем application и bot
        application_instance = Application.builder().token(BOT_TOKEN).build()
        bot_instance = application_instance.bot

        # Добавляем обработчики
        application_instance.add_handler(CommandHandler("start", start_handler))
        application_instance.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, webapp_data_handler))

        # Проверяем режим запуска
        webhook_url = os.environ.get('RAILWAY_STATIC_URL')

        if webhook_url:
            # Production mode - webhook
            logger.info(f"Запуск в режиме webhook: {webhook_url}")

            # Устанавливаем webhook
            webhook_full_url = f"https://{webhook_url}/webhook/{BOT_TOKEN}"
            loop.run_until_complete(bot_instance.set_webhook(webhook_full_url))

            # Инициализируем application без запуска polling
            loop.run_until_complete(application_instance.initialize())

            # Держим loop живым
            try:
                loop.run_forever()
            except KeyboardInterrupt:
                pass
            finally:
                loop.run_until_complete(application_instance.shutdown())
        else:
            # Development mode - polling
            logger.info("Запуск в режиме polling")
            application_instance.run_polling()

    except Exception as e:
        logger.error(f"Ошибка запуска бота: {e}")


if __name__ == '__main__':
    # Инициализация
    init_db()
    load_users()
    logger.info(f"Загружено пользователей: {len(users)}")

    # Запуск бота в отдельном потоке только в production режиме
    webhook_url = os.environ.get('RAILWAY_STATIC_URL')
    if webhook_url:
        bot_thread = threading.Thread(target=run_bot, daemon=True)
        bot_thread.start()

    # Запуск Flask сервера
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
