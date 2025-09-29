import sqlite3
from datetime import datetime

from Main import logger


def add_referral(referrer_id: int, referral_id: int):
    """Безопасное добавление реферала с проверками"""
    conn = sqlite3.connect("users.db")
    try:
        # 1. Проверяем условия
        if referrer_id == referral_id:
            return False

        cursor = conn.cursor()

        # 2. Проверяем, есть ли уже реферер у пользователя
        cursor.execute("SELECT referrer_id FROM users WHERE id = ?", (referral_id,))
        existing_referrer = cursor.fetchone()

        if existing_referrer and existing_referrer[0]:
            logger.warning(f"Пользователь {referral_id} уже имеет реферера")
            return False

        # 3. Проверяем существование реферера
        cursor.execute("SELECT 1 FROM users WHERE id = ?", (referrer_id,))
        if not cursor.fetchone():
            logger.warning(f"Реферер {referrer_id} не найден")
            return False

        # 4. Добавляем связь
        cursor.execute("""
            UPDATE users 
            SET referrer_id = ?,
                referral_level = 1,
                is_ref_used = 1
            WHERE id = ?
        """, (referrer_id, referral_id))

        # 5. Обновляем счетчик рефералов
        cursor.execute("""
            UPDATE users 
            SET referrals_count = referrals_count + 1,
                last_updated = ?
            WHERE id = ?
        """, (datetime.now().isoformat(), referrer_id))

        conn.commit()
        return cursor.rowcount > 0

    except sqlite3.IntegrityError as e:
        logger.error(f"Ошибка целостности: {e}")
        return False
    except Exception as e:
        logger.error(f"Ошибка в add_referral: {e}")
        return False
    finally:
        conn.close()