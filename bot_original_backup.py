import os
import random
import re
from datetime import datetime
from collections import Counter

import psycopg
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)


CATALOG_LIFETIME_SECONDS = 24 * 60 * 60
ADMIN_PAGE_SIZE = 12
USE_PREMIUM_BUTTON_EMOJI = True
ORDER_SUCCESS_STICKER = os.getenv("ORDER_SUCCESS_STICKER", "").strip()

# Невидимая строка для расширения пузыря сообщений.
# Если нужно шире/уже — меняй число 30.
WIDE_MESSAGE_PAD = "⠀" * 30


def wide_text(text):
    if not text:
        return text

    # Добавляем невидимую строку в конец.
    # Так пузырь становится шире, а сверху не появляется пустой отступ.
    return f"{text}\n{WIDE_MESSAGE_PAD}"

ADMIN_PANEL_TEXT = (
    "⚙️ Админ-панель\n\n"
    "Выберите действие для управления каталогом:"
)

CATALOG_TEXT = (
    "Каталог товаров\n\n"
    "Выберите нужную категорию из списка ниже:"
)


# =========================
# ENV
# =========================

def get_env(name, default=None):
    value = os.environ.get(name, default)
    if isinstance(value, str):
        return value.strip()
    return value


def get_token():
    return get_env("BOT_TOKEN")


def get_database_url():
    return get_env("DATABASE_URL")


def get_admin_id():
    admin_id = get_env("ADMIN_ID")
    if not admin_id:
        return None
    try:
        return int(admin_id)
    except ValueError:
        return None


def get_admin_login():
    return get_env("ADMIN_LOGIN", "admin")


def get_admin_password():
    return get_env("ADMIN_PASSWORD", "123321")


# =========================
# PREMIUM EMOJI HELPERS
# =========================

def utf16_len(text):
    return len(text.encode("utf-16-le")) // 2


def remove_utf16_range(text, offset, length):
    result = []
    current_offset = 0

    for char in text:
        char_len = utf16_len(char)
        next_offset = current_offset + char_len

        if next_offset <= offset or current_offset >= offset + length:
            result.append(char)

        current_offset = next_offset

    return "".join(result)


def extract_text_and_custom_emoji(message):
    text = message.text or message.caption or ""
    emoji_id = None
    cleaned_text = text
    entities = message.entities or message.caption_entities or []

    custom_entities = [
        entity for entity in entities
        if entity.type == "custom_emoji"
    ]

    if custom_entities:
        emoji_id = custom_entities[0].custom_emoji_id

        for entity in sorted(custom_entities, key=lambda e: e.offset, reverse=True):
            cleaned_text = remove_utf16_range(
                cleaned_text,
                entity.offset,
                entity.length
            )

    cleaned_text = " ".join(cleaned_text.split()).strip()
    return cleaned_text, emoji_id


def normalize_ru_phone(raw_phone):
    digits = re.sub(r"\D", "", raw_phone or "")

    # Принимаем:
    # 8 9XX XXX XX XX
    # 8 8XX XXX XX XX
    # +7 9XX XXX XX XX
    # +7 8XX XXX XX XX
    # 7 9XX XXX XX XX
    # 7 8XX XXX XX XX
    # 9XX XXX XX XX
    # 8XX XXX XX XX
    if len(digits) == 10 and digits[0] in ["9", "8"]:
        digits = "8" + digits

    if len(digits) == 11 and digits.startswith("7"):
        digits = "8" + digits[1:]

    if len(digits)!= 11:
        return None

    if not digits.startswith("8"):
        return None

    if digits[1] not in ["9", "8"]:
        return None

    return f"{digits[0]} {digits[1:4]} {digits[4:7]} {digits[7:9]} {digits[9:11]}"


def address_has_city(address):
    text = " ".join((address or "").strip().split())

    if not text:
        return False

    lower = text.lower()

    # Явные варианты: "г. Москва", "город Москва"
    if re.search(r"(^|[\s,])г\.\s*[а-яёa-z]", lower, re.IGNORECASE):
        return True

    if re.search(r"(^|[\s,])город\s+[а-яёa-z]", lower, re.IGNORECASE):
        return True

    # Вариант: "Москва, Парковый 1" — первая часть до запятой считается городом.
    parts = [part.strip() for part in text.split(",") if part.strip()]

    if len(parts) >= 2 and re.search(r"[а-яёa-z]", parts[0], re.IGNORECASE):
        return True

    return False


# =========================
# ORDER BEAUTY
# =========================

def generate_order_number():
    return random.randint(100000, 999999)


def build_pretty_order_text(order_number, order_name, order_phone, order_address, lines):
    items_text = "\n".join(lines)

    return (
        "━━━━━━━━━━━━━━━━━━\n"
        "✅ <b>ЗАКАЗ ОФОРМЛЕН</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"🧾 <b>Номер заказа:</b> <code>#{order_number}</code>\n"
        f"👤 <b>ФИО:</b> {order_name}\n"
        f"📞 <b>Телефон:</b> {order_phone}\n"
        f"📍 <b>Адрес:</b> {order_address}\n\n"
        f"📦 <b>Состав заказа:</b>\n{items_text}\n\n"
        "🙏 <b>Спасибо за покупку!</b>\n"
        "Менеджер скоро свяжется с вами для подтверждения заказа."
    )


def build_admin_order_text(order_number, order_name, order_phone, order_address, lines, username, user_id):
    items_text = "\n".join(lines)

    return (
        "🆕 Новый заказ!\n\n"
        f"Номер заказа: #{order_number}\n\n"
        f"Товары:\n{items_text}\n\n"
        f"Имя клиента: {order_name}\n"
        f"Телефон: {order_phone}\n"
        f"Адрес: {order_address}\n\n"
        f"Telegram: {username or 'username не указан'}\n"
        f"Telegram ID: {user_id}\n\n"
        f"Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )


# =========================
# DATABASE
# =========================

def db_connect():
    database_url = get_database_url()
    if not database_url:
        raise RuntimeError("DATABASE_URL не найден. Добавь DATABASE_URL в Railway Variables.")
    return psycopg.connect(database_url, autocommit=True)


def init_db():
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS categories (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    emoji_id TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)
            cur.execute("ALTER TABLE categories ADD COLUMN IF NOT EXISTS emoji_id TEXT;")
            cur.execute("ALTER TABLE categories ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS models (
                    id SERIAL PRIMARY KEY,
                    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    emoji_id TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)
            cur.execute("ALTER TABLE models ADD COLUMN IF NOT EXISTS description TEXT DEFAULT '';")
            cur.execute("ALTER TABLE models ADD COLUMN IF NOT EXISTS emoji_id TEXT;")
            cur.execute("ALTER TABLE models ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS product_types (
                    id SERIAL PRIMARY KEY,
                    model_id INTEGER NOT NULL REFERENCES models(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    emoji_id TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)
            cur.execute("ALTER TABLE product_types ADD COLUMN IF NOT EXISTS description TEXT DEFAULT '';")
            cur.execute("ALTER TABLE product_types ADD COLUMN IF NOT EXISTS emoji_id TEXT;")
            cur.execute("ALTER TABLE product_types ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    id SERIAL PRIMARY KEY,
                    model_id INTEGER REFERENCES models(id) ON DELETE CASCADE,
                    type_id INTEGER REFERENCES product_types(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    photo_file_id TEXT,
                    price TEXT NOT NULL DEFAULT '',
                    emoji_id TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                );
            """)
            cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS category_id INTEGER REFERENCES categories(id) ON DELETE CASCADE;")
            cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS model_id INTEGER REFERENCES models(id) ON DELETE CASCADE;")
            cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS type_id INTEGER REFERENCES product_types(id) ON DELETE CASCADE;")
            cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS description TEXT DEFAULT '';")
            cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS photo_file_id TEXT;")
            cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS price TEXT NOT NULL DEFAULT '';")
            cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS emoji_id TEXT;")
            cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;")
            cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW();")

            # Безопасная миграция для старой базы Railway:
            # раньше products.category_id/model_id могли быть NOT NULL.
            # В новой структуре товар связан через type_id -> model_id -> category_id,
            # поэтому эти старые NOT NULL ограничения нужно снять.
            cur.execute("ALTER TABLE products ALTER COLUMN category_id DROP NOT NULL;")
            cur.execute("ALTER TABLE products ALTER COLUMN model_id DROP NOT NULL;")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    username TEXT,
                    full_name TEXT,
                    phone TEXT,
                    address TEXT,
                    product_id INTEGER,
                    product_name TEXT,
                    price TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)
            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS phone TEXT;")
            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS address TEXT;")
            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS product_id INTEGER;")
            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS product_name TEXT;")
            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS price TEXT;")
            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS items TEXT;")
            cur.execute("ALTER TABLE orders ALTER COLUMN items DROP NOT NULL;")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS price_history (
                    id SERIAL PRIMARY KEY,
                    product_id INTEGER,
                    old_price TEXT,
                    new_price TEXT,
                    changed_by BIGINT,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS admins (
                    id SERIAL PRIMARY KEY,
                    telegram_id BIGINT UNIQUE NOT NULL,
                    username TEXT,
                    full_name TEXT,
                    role TEXT DEFAULT 'admin',
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS admin_login_attempts (
                    id SERIAL PRIMARY KEY,
                    telegram_id BIGINT,
                    username TEXT,
                    full_name TEXT,
                    login TEXT,
                    success BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)


# =========================
# CATEGORY DB
# =========================

def get_categories():
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name
                FROM categories
                WHERE is_active = TRUE
                ORDER BY id;
            """)
            return cur.fetchall()


def get_categories_for_catalog():
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name, emoji_id
                FROM categories
                WHERE is_active = TRUE
                ORDER BY id;
            """)
            return cur.fetchall()


def get_category(category_id):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name
                FROM categories
                WHERE id = %s AND is_active = TRUE;
            """, (category_id,))
            return cur.fetchone()


def add_category(name, emoji_id=None):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO categories (name, emoji_id, is_active)
                VALUES (%s, %s, TRUE)
                ON CONFLICT (name)
                DO UPDATE SET
                    is_active = TRUE,
                    emoji_id = EXCLUDED.emoji_id
                RETURNING id;
            """, (name, emoji_id))
            return cur.fetchone()[0]


def rename_category(category_id, new_name, emoji_id=None):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE categories
                SET name = %s,
                    emoji_id = %s
                WHERE id = %s;
            """, (new_name, emoji_id, category_id))


def delete_category(category_id):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE categories
                SET is_active = FALSE
                WHERE id = %s;
            """, (category_id,))


# =========================
# MODEL DB
# =========================

def get_models_by_category(category_id):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name, description, emoji_id
                FROM models
                WHERE category_id = %s AND is_active = TRUE
                ORDER BY id;
            """, (category_id,))
            return cur.fetchall()


def get_model(model_id):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT m.id, m.name, m.description, c.id, c.name
                FROM models m
                JOIN categories c ON c.id = m.category_id
                WHERE m.id = %s
                  AND m.is_active = TRUE
                  AND c.is_active = TRUE;
            """, (model_id,))
            return cur.fetchone()


def get_all_models():
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT m.id, m.name, m.description, c.name
                FROM models m
                JOIN categories c ON c.id = m.category_id
                WHERE m.is_active = TRUE
                  AND c.is_active = TRUE
                ORDER BY c.id, m.id;
            """)
            return cur.fetchall()


def add_model(category_id, name, description, emoji_id=None):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO models (category_id, name, description, emoji_id)
                VALUES (%s, %s, %s, %s)
                RETURNING id;
            """, (category_id, name, description, emoji_id))
            return cur.fetchone()[0]


def rename_model(model_id, new_name):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE models SET name = %s WHERE id = %s;", (new_name, model_id))


def update_model_description(model_id, new_description):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE models SET description = %s WHERE id = %s;", (new_description, model_id))


def delete_model(model_id):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE models SET is_active = FALSE WHERE id = %s;", (model_id,))


# =========================
# PRODUCT TYPE DB
# =========================

def get_types_by_model(model_id):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name, description, emoji_id
                FROM product_types
                WHERE model_id = %s AND is_active = TRUE
                ORDER BY id;
            """, (model_id,))
            return cur.fetchall()


def get_type(type_id):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    t.id,
                    t.name,
                    t.description,
                    m.id,
                    m.name,
                    c.id,
                    c.name
                FROM product_types t
                JOIN models m ON m.id = t.model_id
                JOIN categories c ON c.id = m.category_id
                WHERE t.id = %s
                  AND t.is_active = TRUE
                  AND m.is_active = TRUE
                  AND c.is_active = TRUE;
            """, (type_id,))
            return cur.fetchone()


def get_all_types():
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    t.id,
                    t.name,
                    t.description,
                    m.name,
                    c.name
                FROM product_types t
                JOIN models m ON m.id = t.model_id
                JOIN categories c ON c.id = m.category_id
                WHERE t.is_active = TRUE
                  AND m.is_active = TRUE
                  AND c.is_active = TRUE
                ORDER BY c.id, m.id, t.id;
            """)
            return cur.fetchall()


def add_type(model_id, name, description, emoji_id=None):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO product_types (model_id, name, description, emoji_id)
                VALUES (%s, %s, %s, %s)
                RETURNING id;
            """, (model_id, name, description, emoji_id))
            return cur.fetchone()[0]


def rename_type(type_id, new_name):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE product_types SET name = %s WHERE id = %s;", (new_name, type_id))


def update_type_description(type_id, new_description):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE product_types SET description = %s WHERE id = %s;", (new_description, type_id))


def delete_type(type_id):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE product_types SET is_active = FALSE WHERE id = %s;", (type_id,))


# =========================
# PRODUCT DB
# =========================

def get_products_by_type(type_id):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name, description, photo_file_id, price, emoji_id
                FROM products
                WHERE type_id = %s AND is_active = TRUE
                ORDER BY id;
            """, (type_id,))
            return cur.fetchall()


def get_product(product_id):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    p.id,
                    p.name,
                    p.description,
                    p.photo_file_id,
                    p.price,
                    t.id,
                    t.name,
                    m.id,
                    m.name,
                    c.id,
                    c.name
                FROM products p
                JOIN product_types t ON t.id = p.type_id
                JOIN models m ON m.id = t.model_id
                JOIN categories c ON c.id = m.category_id
                WHERE p.id = %s
                  AND p.is_active = TRUE
                  AND t.is_active = TRUE
                  AND m.is_active = TRUE
                  AND c.is_active = TRUE;
            """, (product_id,))
            return cur.fetchone()


def get_all_products():
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    p.id,
                    c.name,
                    m.name,
                    t.name,
                    p.name,
                    p.price
                FROM products p
                JOIN product_types t ON t.id = p.type_id
                JOIN models m ON m.id = t.model_id
                JOIN categories c ON c.id = m.category_id
                WHERE p.is_active = TRUE
                  AND t.is_active = TRUE
                  AND m.is_active = TRUE
                  AND c.is_active = TRUE
                ORDER BY c.id, m.id, t.id, p.id;
            """)
            return cur.fetchall()


def add_product(type_id, name, description, photo_file_id, price, emoji_id=None):
    product_type = get_type(type_id)

    if not product_type:
        return None

    # get_type возвращает:
    # 0 type_id, 1 type_name, 2 type_description,
    # 3 model_id, 4 model_name, 5 category_id, 6 category_name
    model_id = product_type[3]
    category_id = product_type[5]

    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO products
                (category_id, model_id, type_id, name, description, photo_file_id, price, emoji_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
            """, (category_id, model_id, type_id, name, description, photo_file_id, price, emoji_id))
            return cur.fetchone()[0]


def rename_product(product_id, new_name):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE products
                SET name = %s,
                    updated_at = NOW()
                WHERE id = %s;
            """, (new_name, product_id))


def update_product_description(product_id, description):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE products
                SET description = %s,
                    updated_at = NOW()
                WHERE id = %s;
            """, (description, product_id))


def update_product_photo(product_id, photo_file_id):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE products
                SET photo_file_id = %s,
                    updated_at = NOW()
                WHERE id = %s;
            """, (photo_file_id, product_id))


def update_product_price(product_id, new_price, changed_by=None):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT price FROM products WHERE id = %s;", (product_id,))
            row = cur.fetchone()

            if not row:
                return None

            old_price = row[0]

            cur.execute("""
                UPDATE products
                SET price = %s,
                    updated_at = NOW()
                WHERE id = %s;
            """, (new_price, product_id))

            cur.execute("""
                INSERT INTO price_history (product_id, old_price, new_price, changed_by)
                VALUES (%s, %s, %s, %s);
            """, (product_id, old_price, new_price, changed_by))

            return old_price


def delete_product(product_id):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE products
                SET is_active = FALSE,
                    updated_at = NOW()
                WHERE id = %s;
            """, (product_id,))


# =========================
# ORDERS / ADMINS
# =========================

def save_order(user_id, username, full_name, phone, address, product_id, product_name, price):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO orders
                (user_id, username, full_name, phone, address, product_id, product_name, price)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
            """, (user_id, username, full_name, phone, address, product_id, product_name, price))


def is_admin_in_db(telegram_id):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM admins WHERE telegram_id = %s;", (telegram_id,))
            return cur.fetchone() is not None


def add_admin_to_db(telegram_id, username, full_name):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO admins (telegram_id, username, full_name)
                VALUES (%s, %s, %s)
                ON CONFLICT (telegram_id)
                DO UPDATE SET
                    username = EXCLUDED.username,
                    full_name = EXCLUDED.full_name;
            """, (telegram_id, username, full_name))


def get_admins_list():
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT telegram_id, username, full_name, role, created_at
                FROM admins
                ORDER BY created_at DESC;
            """)
            return cur.fetchall()


def delete_admin_from_db(telegram_id):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM admins
                WHERE telegram_id = %s;
            """, (telegram_id,))
            return cur.rowcount


def save_admin_login_attempt(telegram_id, username, full_name, login, success):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO admin_login_attempts
                (telegram_id, username, full_name, login, success)
                VALUES (%s, %s, %s, %s, %s);
            """, (telegram_id, username, full_name, login, success))


def is_admin_user(user_id):
    main_admin_id = get_admin_id()

    if main_admin_id and user_id == main_admin_id:
        return True

    return is_admin_in_db(user_id)


def is_admin_logged(context):
    return context.user_data.get("admin_logged") is True


def is_main_admin(user_id):
    main_admin_id = get_admin_id()
    return bool(main_admin_id and user_id == main_admin_id)


async def try_delete_message(context, chat_id, message_id):
    if not chat_id or not message_id:
        return

    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass


async def delete_saved_prompt(context, chat_id, key):
    message_id = context.user_data.pop(key, None)
    await try_delete_message(context, chat_id, message_id)


# =========================
# KEYBOARDS
# =========================

reply_menu = ReplyKeyboardMarkup(
    keyboard=[
        ["📦 Каталог"],
        ["🛒 Корзина"],
    ],
    resize_keyboard=True
)

order_menu = ReplyKeyboardMarkup(
    keyboard=[
        ["❌ Отменить оформление"],
        ["📦 Каталог", "🛒 Корзина"],
    ],
    resize_keyboard=True
)


def button(text, callback_data, style=None):
    api_kwargs = {}

    if style:
        api_kwargs["style"] = style

    return InlineKeyboardButton(
        text=text,
        callback_data=callback_data,
        api_kwargs=api_kwargs
    )


def primary_button(text, callback_data):
    return button(text, callback_data, style="primary")


def success_button(text, callback_data):
    return button(text, callback_data, style="success")


def danger_button(text, callback_data):
    return button(text, callback_data, style="danger")


def default_button(text, callback_data):
    return button(text, callback_data, style="default")


def pbutton(text, callback_data, emoji_id=None, style=None):
    api_kwargs = {}

    if USE_PREMIUM_BUTTON_EMOJI and emoji_id:
        api_kwargs["icon_custom_emoji_id"] = emoji_id

    if style:
        api_kwargs["style"] = style

    return InlineKeyboardButton(
        text=text,
        callback_data=callback_data,
        api_kwargs=api_kwargs
    )


def make_two_columns(buttons):
    keyboard = []
    for i in range(0, len(buttons), 2):
        keyboard.append(buttons[i:i + 2])
    return keyboard


def paginate_items(items, page, page_size=ADMIN_PAGE_SIZE):
    total = len(items)
    start = page * page_size
    end = start + page_size
    return items[start:end], total


def pagination_buttons(prefix, page, total, page_size=ADMIN_PAGE_SIZE):
    buttons = []
    max_page = (total - 1) // page_size if total > 0 else 0
    row = []

    if page > 0:
        row.append(button("⬅️ Назад", f"{prefix}_{page - 1}"))

    if page < max_page:
        row.append(button("Вперёд ➡️", f"{prefix}_{page + 1}"))

    if row:
        buttons.append(row)

    return buttons


def catalog_keyboard():
    categories = get_categories_for_catalog()

    buttons = [
        pbutton(
            text=name,
            callback_data=f"cat_{category_id}",
            emoji_id=emoji_id
        )
        for category_id, name, emoji_id in categories
    ]

    keyboard = make_two_columns(buttons)
    # Корзина тут специально убрана

    return InlineKeyboardMarkup(keyboard)


def admin_keyboard():
    return InlineKeyboardMarkup([
        [button("➕ Добавить категорию", "admin_add_category")],
        [button("➕ Добавить модель", "admin_add_model")],
        [button("➕ Добавить вид товара", "admin_add_type")],
        [button("➕ Добавить товар", "admin_add_product")],
        [button("⚡ Массовое обновление цен", "admin_bulk_prices")],
        [button("🧩 Редактор категорий", "admin_edit_categories")],
        [button("📱 Редактор моделей", "admin_edit_models")],
        [button("📂 Редактор видов товара", "admin_edit_types")],
        [button("📦 Редактор товаров", "admin_products")],
        [button("👥 Добавить админа", "admin_add_admin")],
        [button("📋 Список админов", "admin_list_admins")],
        [button("❌ Удалить админа", "admin_delete_admin")],
        [button("🚪 Выйти из админ-панели", "admin_logout")],
    ])


def cancel_admin_keyboard():
    return InlineKeyboardMarkup([
        [button("⬅️ Назад в админ-панель", "admin_cancel")]
    ])


def admin_choose_category_for_model_keyboard(page=0):
    categories = get_categories()
    page_items, total = paginate_items(categories, page)

    keyboard = []

    for category_id, name in page_items:
        keyboard.append([
            button(name, f"admin_model_cat_{category_id}")
        ])

    keyboard += pagination_buttons("admin_add_model_page", page, total)
    keyboard.append([button("Назад в админ-панель", "admin_menu")])

    return InlineKeyboardMarkup(keyboard)


def admin_choose_model_for_type_keyboard(page=0):
    models = get_all_models()
    page_items, total = paginate_items(models, page)

    keyboard = []

    for model_id, model_name, description, category_name in page_items:
        keyboard.append([
            button(f"{category_name} → {model_name}", f"admin_type_model_{model_id}")
        ])

    keyboard += pagination_buttons("admin_add_type_page", page, total)
    keyboard.append([button("Назад в админ-панель", "admin_menu")])

    return InlineKeyboardMarkup(keyboard)


def admin_choose_type_for_product_keyboard(page=0):
    types = get_all_types()
    page_items, total = paginate_items(types, page)

    keyboard = []

    for type_id, type_name, description, model_name, category_name in page_items:
        keyboard.append([
            button(
                f"{category_name} → {model_name} → {type_name}",
                f"admin_product_type_{type_id}"
            )
        ])

    keyboard += pagination_buttons("admin_add_product_page", page, total)
    keyboard.append([button("Назад в админ-панель", "admin_menu")])

    return InlineKeyboardMarkup(keyboard)


def admin_edit_categories_keyboard(page=0):
    categories = get_categories()
    page_items, total = paginate_items(categories, page)

    keyboard = []

    for category_id, name in page_items:
        keyboard.append([
            button(name, f"admin_edit_category_{category_id}")
        ])

    keyboard += pagination_buttons("admin_edit_categories_page", page, total)
    keyboard.append([button("Назад в админ-панель", "admin_menu")])

    return InlineKeyboardMarkup(keyboard)


def admin_edit_models_keyboard(page=0):
    models = get_all_models()
    page_items, total = paginate_items(models, page)

    keyboard = []

    for model_id, model_name, description, category_name in page_items:
        keyboard.append([
            button(f"{category_name} → {model_name}", f"admin_edit_model_{model_id}")
        ])

    keyboard += pagination_buttons("admin_edit_models_page", page, total)
    keyboard.append([button("Назад в админ-панель", "admin_menu")])

    return InlineKeyboardMarkup(keyboard)


def admin_edit_types_keyboard(page=0):
    types = get_all_types()
    page_items, total = paginate_items(types, page)

    keyboard = []

    for type_id, type_name, description, model_name, category_name in page_items:
        keyboard.append([
            button(
                f"{category_name} → {model_name} → {type_name}",
                f"admin_edit_type_{type_id}"
            )
        ])

    keyboard += pagination_buttons("admin_edit_types_page", page, total)
    keyboard.append([button("Назад в админ-панель", "admin_menu")])

    return InlineKeyboardMarkup(keyboard)


def admin_products_keyboard(page=0):
    products = get_all_products()
    page_items, total = paginate_items(products, page)

    keyboard = []

    for product_id, category_name, model_name, type_name, product_name, price in page_items:
        keyboard.append([
            button(
                f"#{product_id} — {product_name} — {price}",
                f"admin_product_{product_id}"
            )
        ])

    keyboard += pagination_buttons("admin_products_page", page, total)
    keyboard.append([button("Назад в админ-панель", "admin_menu")])

    return InlineKeyboardMarkup(keyboard)


# =========================
# STATE HELPERS
# =========================

def clear_admin_temp_data(context):
    keys_to_clear = [
        "new_model_category_id",
        "new_model_name",
        "new_model_emoji_id",
        "new_type_model_id",
        "new_type_name",
        "new_type_emoji_id",
        "new_product_type_id",
        "new_product_name",
        "new_product_emoji_id",
        "new_product_description",
        "new_product_photo_file_id",
        "edit_category_id",
        "edit_model_id",
        "edit_type_id",
        "edit_product_id",
        "admin_login_input",
        "new_admin_id_input",
        "delete_admin_id_input",
    ]

    for key in keys_to_clear:
        context.user_data.pop(key, None)

    context.user_data["admin_state"] = None


def clear_order_data(context):
    keys = [
        "order_product_id",
        "order_name",
        "order_phone",
        "order_address",
        "checkout_items",
        "checkout_source",
    ]

    for key in keys:
        context.user_data.pop(key, None)

    context.user_data["order_state"] = None


async def cancel_order_flow(update: Update, context: ContextTypes.DEFAULT_TYPE, message="Оформление заказа отменено."):
    clear_order_data(context)
    await update.message.reply_text(
        message,
        reply_markup=reply_menu
    )


def parse_price_to_int(price):
    digits = re.sub(r"\D", "", str(price or ""))

    if not digits:
        return None

    try:
        return int(digits)
    except ValueError:
        return None


def format_money(value):
    if value is None:
        return "не указано"

    return f"{value:,}".replace(",", " ")


def get_product_qty(context, product_id):
    return max(1, int(context.user_data.get(f"qty_{product_id}", 1)))


def set_product_qty(context, product_id, qty):
    qty = max(1, min(99, int(qty)))
    context.user_data[f"qty_{product_id}"] = qty
    return qty


def get_cart(context):
    return context.user_data.setdefault("cart", [])


def add_product_to_cart(context, product_id, qty=1):
    cart = get_cart(context)

    for _ in range(max(1, int(qty))):
        cart.append(product_id)

    context.user_data["cart"] = cart


def clear_cart(context):
    context.user_data["cart"] = []


def remove_cart_product(context, product_id):
    cart = get_cart(context)
    new_cart = [item_id for item_id in cart if item_id!= product_id]

    if len(new_cart) == len(cart):
        return False

    context.user_data["cart"] = new_cart
    return True


def remove_cart_item_by_index(context, index):
    cart = get_cart(context)

    if index < 0 or index >= len(cart):
        return False

    cart.pop(index)
    context.user_data["cart"] = cart
    return True


def set_checkout_items(context, product_ids):
    context.user_data["checkout_items"] = list(product_ids)


def get_checkout_items(context):
    return context.user_data.get("checkout_items") or []


def clear_checkout_items(context):
    context.user_data.pop("checkout_items", None)


def build_cart_lines(context, product_ids=None):
    if product_ids is None:
        product_ids = get_cart(context)

    counter = Counter(product_ids)
    lines = []
    valid_product_ids = []
    total_sum = 0
    has_total = False
    index = 1

    for product_id, qty in counter.items():
        product = get_product(product_id)

        if not product:
            continue

        (
            real_product_id,
            product_name,
            description,
            photo_file_id,
            price,
            type_id,
            type_name,
            model_id,
            model_name,
            category_id,
            category_name
        ) = product

        valid_product_ids.extend([real_product_id] * qty)

        price_value = parse_price_to_int(price)
        if price_value is not None:
            item_total = price_value * qty
            total_sum += item_total
            has_total = True
            lines.append(
                f"{index}. #{real_product_id} — {product_name}\n"
                f"   Количество: {qty} шт.\n"
                f"   Цена за шт: {price}\n"
                f"   Общая цена: {format_money(item_total)}"
            )
        else:
            lines.append(
                f"{index}. #{real_product_id} — {product_name}\n"
                f"   Количество: {qty} шт.\n"
                f"   Цена за шт: {price}\n"
                f"   Общая цена: не посчитана"
            )

        index += 1

    if has_total:
        lines.append(f"\nИтого: {format_money(total_sum)}")

    return lines, valid_product_ids


def cart_markup(context):
    return InlineKeyboardMarkup([
        [success_button("✅ Оформить заказ", "checkout")],
        [danger_button("❌ Удалить товар", "cart_delete_menu")],
        [danger_button("🗑 Очистить корзину", "clear_cart")],
        [default_button("📦 Вернуться в каталог", "catalog")],
    ])


def cart_delete_markup(context):
    cart = get_cart(context)
    counter = Counter(cart)
    keyboard = []

    for product_id, qty in counter.items():
        product = get_product(product_id)

        if not product:
            continue

        keyboard.append([
            danger_button(
                f"Удалить #{product[0]} — {product[1]} ({qty} шт.)",
                f"remove_cart_product_{product_id}"
            )
        ])

    keyboard.append([danger_button("↩️ Назад в корзину", "cart")])
    keyboard.append([default_button("📦 Вернуться в каталог", "catalog")])

    return InlineKeyboardMarkup(keyboard)


async def safe_show_text(query, text, reply_markup=None):
    text = wide_text(text)

    try:
        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup
        )
    except Exception:
        try:
            await query.message.delete()
        except Exception:
            pass

        await query.message.chat.send_message(
            text=text,
            reply_markup=reply_markup
        )


def build_product_card_caption(product, qty):
    (
        product_id,
        product_name,
        description,
        photo_file_id,
        price,
        type_id,
        type_name,
        model_id,
        model_name,
        category_id,
        category_name
    ) = product

    price_value = parse_price_to_int(price)
    total_price = None

    if price_value is not None:
        total_price = price_value * qty

    caption = (
        f"{product_name}\n\n"
        f"ID товара: #{product_id}\n"
        f"Количество: {qty} шт.\n"
        f"Цена за шт: {price}\n"
    )

    if total_price is not None:
        caption += f"Общая цена: {format_money(total_price)}\n"
    else:
        caption += "Общая цена: не посчитана\n"

    if description:
        caption += f"\nОписание:\n{description}\n"

    return caption


def product_card_keyboard(product_id, type_id, qty):
    return InlineKeyboardMarkup([
        [
            default_button("−", f"qty_minus_{product_id}"),
            default_button(str(qty), f"qty_show_{product_id}"),
            default_button("+", f"qty_plus_{product_id}"),
        ],
        [success_button("✅ Оформить заказ", f"buy_{product_id}")],
        [primary_button("🛒 Добавить в корзину", f"addcart_{product_id}")],
        [danger_button("↩️ Вернуться обратно", f"type_{type_id}")],
        [default_button("📦 Вернуться в каталог", "catalog")],
    ])


async def update_product_card(query, context, product_id):
    product = get_product(product_id)

    if not product:
        await safe_show_text(query, "Товар не найден.")
        return

    (
        product_id,
        product_name,
        description,
        photo_file_id,
        price,
        type_id,
        type_name,
        model_id,
        model_name,
        category_id,
        category_name
    ) = product

    qty = get_product_qty(context, product_id)
    caption = build_product_card_caption(product, qty)
    keyboard = product_card_keyboard(product_id, type_id, qty)

    if photo_file_id:
        try:
            await query.edit_message_caption(
                caption=caption,
                reply_markup=keyboard
            )
            return
        except Exception:
            pass

    try:
        await query.edit_message_text(
            text=caption,
            reply_markup=keyboard
        )
    except Exception:
        await safe_show_text(query, caption, keyboard)


async def show_product_card(query, product, context=None):
    (
        product_id,
        product_name,
        description,
        photo_file_id,
        price,
        type_id,
        type_name,
        model_id,
        model_name,
        category_id,
        category_name
    ) = product

    if context:
        qty = set_product_qty(context, product_id, get_product_qty(context, product_id))
    else:
        qty = 1

    caption = build_product_card_caption(product, qty)
    keyboard = product_card_keyboard(product_id, type_id, qty)

    if photo_file_id:
        try:
            await query.message.delete()
        except Exception:
            pass

        await query.message.chat.send_photo(
            photo=photo_file_id,
            caption=caption,
            reply_markup=keyboard
        )
    else:
        await safe_show_text(
            query,
            caption,
            keyboard
        )


# =========================
# JOBS
# =========================

async def delete_catalog_job(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    chat_id = job_data["chat_id"]
    message_id = job_data["message_id"]

    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass


# =========================
# COMMANDS
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        (
            'Добро пожаловать! '
            '<tg-emoji emoji-id="5339547060859345402">☺</tg-emoji>\n\n'
            'Мы знаем, как найти то, что вам нужно. '
            'От мощных игровых станций до компактных смартфонов — '
            'поможем разобраться в мире гаджетов без лишнего шума.'
        ),
        reply_markup=reply_menu,
        parse_mode="HTML"
    )


async def send_catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    categories = get_categories()

    if not categories:
        await update.message.reply_text(
            (
                "Каталог\n\n"
                "Каталог пока пустой.\n\n"
                "Скоро здесь появятся товары."
            ),
            reply_markup=reply_menu
        )
        return

    message = await update.message.reply_text(
        wide_text(CATALOG_TEXT),
        reply_markup=catalog_keyboard()
    )

    context.job_queue.run_once(
        delete_catalog_job,
        when=CATALOG_LIFETIME_SECONDS,
        data={
            "chat_id": message.chat_id,
            "message_id": message.message_id,
        },
        name=f"delete_catalog_{message.chat_id}_{message.message_id}"
    )


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["admin_state"] = "wait_login"
    context.user_data["admin_logged"] = False

    message = await update.message.reply_text(
        "🔐 Вход в админ-панель\n\nВведите логин:"
    )

    context.user_data["admin_login_prompt_id"] = message.message_id


async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_admin_user(user_id):
        await update.message.reply_text("Нет доступа.")
        return

    text = update.message.text.strip()
    parts = text.split(maxsplit=2)

    if len(parts) < 3:
        await update.message.reply_text(
            "Формат:\n/price ID новая_цена\n\nНапример:\n/price 25 118000"
        )
        return

    try:
        product_id = int(parts[1])
    except ValueError:
        await update.message.reply_text("ID товара должен быть числом.")
        return

    new_price = parts[2].strip()
    product = get_product(product_id)

    if not product:
        await update.message.reply_text("Товар не найден.")
        return

    old_price = update_product_price(product_id, new_price, changed_by=user_id)

    await update.message.reply_text(
        (
            "Цена обновлена ✅\n\n"
            f"Товар #{product_id}\n"
            f"{product[1]}\n\n"
            f"Было: {old_price}\n"
            f"Стало: {new_price}"
        )
    )


# =========================
# TEXT HANDLER
# =========================

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user = update.effective_user
    user_id = user.id
    username = f"@{user.username}" if user.username else None
    full_name = user.full_name

    admin_state = context.user_data.get("admin_state")
    order_state = context.user_data.get("order_state")

    if order_state and text in ["❌ Отменить оформление", "/cancel", "отмена", "Отмена"]:
        await cancel_order_flow(update, context)
        return

    if order_state and text == "📦 Каталог":
        await cancel_order_flow(update, context, "Оформление заказа отменено. Открываю каталог.")
        await send_catalog(update, context)
        return

    if order_state and text == "🛒 Корзина":
        await cancel_order_flow(update, context, "Оформление заказа отменено. Открываю корзину.")
        await send_cart_message(update, context)
        return

    # ===== FAST FIX: PRODUCT PRICE AFTER PHOTO =====
    # Этот блок стоит высоко специально, чтобы цена товара точно сохранялась.
    if admin_state == "add_product_price":
        if not is_admin_user(user_id) or not is_admin_logged(context):
            await update.message.reply_text("Нет доступа.")
            return

        type_id = context.user_data.get("new_product_type_id")
        name = context.user_data.get("new_product_name")
        emoji_id = context.user_data.get("new_product_emoji_id")
        description = context.user_data.get("new_product_description", "")
        photo_file_id = context.user_data.get("new_product_photo_file_id")
        price = text.strip()

        if not price:
            await update.message.reply_text(
                "Цена пустая. Введите цену товара, например: 100 000",
                reply_markup=cancel_admin_keyboard()
            )
            return

        if not type_id or not name:
            await update.message.reply_text(
                (
                    "Ошибка добавления товара.\n\n"
                    f"type_id: {type_id}\n"
                    f"name: {name}\n\n"
                    "Попробуйте добавить товар заново."
                ),
                reply_markup=admin_keyboard()
            )
            clear_admin_temp_data(context)
            return

        try:
            product_id = add_product(
                type_id=type_id,
                name=name,
                description=description,
                photo_file_id=photo_file_id,
                price=price,
                emoji_id=emoji_id
            )
        except Exception as e:
            await update.message.reply_text(
                f"Ошибка сохранения товара:\n{e}",
                reply_markup=admin_keyboard()
            )
            clear_admin_temp_data(context)
            return

        if not product_id:
            await update.message.reply_text(
                "Ошибка: вид товара не найден.",
                reply_markup=admin_keyboard()
            )
            clear_admin_temp_data(context)
            return

        clear_admin_temp_data(context)

        await update.message.reply_text(
            (
                "Товар добавлен ✅\n\n"
                f"ID: {product_id}\n"
                f"Название: {name}\n"
                f"Цена: {price}\n"
                f"Фото: {'есть' if photo_file_id else 'нет'}\n"
                f"Premium emoji: {'есть' if emoji_id else 'нет'}"
            ),
            reply_markup=admin_keyboard()
        )
        return

    if admin_state and text.lower() in ["назад", "отмена", "/cancel"]:
        clear_admin_temp_data(context)

        await update.message.reply_text(
            ADMIN_PANEL_TEXT,
            reply_markup=admin_keyboard()
        )
        return

    if order_state and text.lower() in ["назад", "отмена", "/cancel"]:
        clear_order_data(context)

        await update.message.reply_text(
            "Оформление заказа отменено.",
            reply_markup=reply_menu
        )
        return

    # ===== ORDER FLOW =====

    if order_state == "wait_order_name":
        context.user_data["order_name"] = text
        context.user_data["order_state"] = "wait_order_phone"

        await update.message.reply_text(
            "Введите номер телефона:",
            reply_markup=order_menu
        )
        return

    if order_state == "wait_order_phone":
        normalized_phone = normalize_ru_phone(text)

        if not normalized_phone:
            await update.message.reply_text(
                (
                    "Номер указан неверно.\n\n"
                    "Формат должен быть такой:\n"
                    "+7 977 777 77 77\n"
                    "или\n"
                    "8 977 777 77 77\n\n"
                    "Можно писать слитно, без пробелов, со скобками или дефисами.\n"
                    "Например: 89777777777"
                ),
                reply_markup=order_menu
            )
            return

        context.user_data["order_phone"] = normalized_phone
        context.user_data["order_state"] = "wait_order_address"

        await update.message.reply_text(
            (
                "Введите адрес доставки.\n\n"
                "Обязательно укажите город.\n"
                "Пример: г. Москва, ул. Примерная 1"
            ),
            reply_markup=order_menu
        )
        return

    if order_state == "wait_order_address":
        order_name = context.user_data.get("order_name")
        order_phone = context.user_data.get("order_phone")
        order_address = text

        if not address_has_city(order_address):
            await update.message.reply_text(
                (
                    "В адресе нужно указать город.\n\n"
                    "Пример:\n"
                    "г. Москва, ул. Примерная 1\n\n"
                    "Или:\n"
                    "Москва, ул. Примерная 1"
                ),
                reply_markup=order_menu
            )
            return

        checkout_items = get_checkout_items(context)
        lines, valid_product_ids = build_cart_lines(context, checkout_items)

        if not valid_product_ids:
            clear_order_data(context)
            await update.message.reply_text(
                "Нет товаров для оформления. Заказ отменён.",
                reply_markup=reply_menu
            )
            return

        admin_id = get_admin_id()

        if not admin_id:
            clear_order_data(context)
            await update.message.reply_text("ADMIN_ID не настроен.")
            return

        order_number = generate_order_number()

        try:
            for product_id in valid_product_ids:
                product = get_product(product_id)

                if not product:
                    continue

                save_order(
                    user_id=user.id,
                    username=username,
                    full_name=order_name,
                    phone=order_phone,
                    address=order_address,
                    product_id=product[0],
                    product_name=product[1],
                    price=product[4]
                )

            order_text = build_admin_order_text(
                order_number=order_number,
                order_name=order_name,
                order_phone=order_phone,
                order_address=order_address,
                lines=lines,
                username=username,
                user_id=user.id
            )

            await context.bot.send_message(
                chat_id=admin_id,
                text=order_text
            )
        except Exception as e:
            await update.message.reply_text(
                f"Ошибка оформления заказа:\n{e}",
                reply_markup=reply_menu
            )
            return

        pretty_text = build_pretty_order_text(
            order_number=order_number,
            order_name=order_name,
            order_phone=order_phone,
            order_address=order_address,
            lines=lines
        )

        if ORDER_SUCCESS_STICKER:
            try:
                await context.bot.send_sticker(
                    chat_id=update.effective_chat.id,
                    sticker=ORDER_SUCCESS_STICKER
                )
            except Exception:
                pass

        checkout_source = context.user_data.get("checkout_source")

        if checkout_source == "cart":
            clear_cart(context)

        clear_order_data(context)

        await update.message.reply_text(
            wide_text(pretty_text),
            parse_mode=ParseMode.HTML,
            reply_markup=reply_menu
        )
        return

    # ===== ADMIN LOGIN =====

    if admin_state == "wait_login":
        await try_delete_message(context, update.effective_chat.id, update.message.message_id)
        await delete_saved_prompt(context, update.effective_chat.id, "admin_login_prompt_id")

        context.user_data["admin_login_input"] = text

        if text == get_admin_login():
            context.user_data["admin_state"] = "wait_password"
            message = await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Теперь введите пароль:"
            )
            context.user_data["admin_password_prompt_id"] = message.message_id
        else:
            context.user_data["admin_state"] = None
            save_admin_login_attempt(user_id, username, full_name, text, False)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Неверный логин."
            )
        return

    if admin_state == "wait_password":
        await try_delete_message(context, update.effective_chat.id, update.message.message_id)
        await delete_saved_prompt(context, update.effective_chat.id, "admin_password_prompt_id")

        login = context.user_data.get("admin_login_input", "")

        if text == get_admin_password():
            if not is_main_admin(user_id) and not is_admin_in_db(user_id):
                context.user_data["admin_logged"] = False
                context.user_data["admin_state"] = None
                save_admin_login_attempt(user_id, username, full_name, login, False)

                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=(
                        "Доступ запрещён.\n\n"
                        "Логин и пароль верные, но ваш Telegram ID не добавлен в список админов."
                    )
                )
                return

            context.user_data["admin_logged"] = True
            context.user_data["admin_state"] = None

            if is_main_admin(user_id):
                add_admin_to_db(user_id, username, full_name)

            save_admin_login_attempt(user_id, username, full_name, login, True)

            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Вход выполнен ✅\n\n" + ADMIN_PANEL_TEXT,
                reply_markup=admin_keyboard()
            )
        else:
            context.user_data["admin_logged"] = False
            context.user_data["admin_state"] = None
            save_admin_login_attempt(user_id, username, full_name, login, False)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Неверный пароль."
            )
        return

    # ===== ADD ADMIN =====

    if admin_state == "add_admin_id":
        if not is_main_admin(user_id) or not is_admin_logged(context):
            await update.message.reply_text("Нет доступа.")
            return

        raw_admin_id = text.strip()

        try:
            new_admin_id = int(raw_admin_id)
        except ValueError:
            await update.message.reply_text(
                "Telegram ID должен быть числом.\n\nНапример: 707131428",
                reply_markup=cancel_admin_keyboard()
            )
            return

        add_admin_to_db(
            telegram_id=new_admin_id,
            username=None,
            full_name="Добавлен владельцем"
        )

        clear_admin_temp_data(context)

        await update.message.reply_text(
            (
                "Админ добавлен ✅\n\n"
                f"Telegram ID: {new_admin_id}\n\n"
                "Теперь этот сотрудник сможет войти через /admin по логину и паролю."
            ),
            reply_markup=admin_keyboard()
        )
        return

    if admin_state == "delete_admin_id":
        if not is_main_admin(user_id) or not is_admin_logged(context):
            await update.message.reply_text("Нет доступа.")
            return

        raw_admin_id = text.strip()

        try:
            admin_id_to_delete = int(raw_admin_id)
        except ValueError:
            await update.message.reply_text(
                "Telegram ID должен быть числом.\n\nНапример: 707131428",
                reply_markup=cancel_admin_keyboard()
            )
            return

        if admin_id_to_delete == get_admin_id():
            await update.message.reply_text(
                "Основного админа удалить нельзя.",
                reply_markup=admin_keyboard()
            )
            clear_admin_temp_data(context)
            return

        deleted_count = delete_admin_from_db(admin_id_to_delete)
        clear_admin_temp_data(context)

        if deleted_count:
            await update.message.reply_text(
                (
                    "Админ удалён ✅\n\n"
                    f"Telegram ID: {admin_id_to_delete}\n\n"
                    "Теперь этот пользователь не сможет войти в админку."
                ),
                reply_markup=admin_keyboard()
            )
        else:
            await update.message.reply_text(
                (
                    "Админ не найден.\n\n"
                    f"Telegram ID: {admin_id_to_delete}"
                ),
                reply_markup=admin_keyboard()
            )
        return

    # ===== CATEGORY =====

    if admin_state == "add_category_name":
        if not is_admin_user(user_id) or not is_admin_logged(context):
            await update.message.reply_text("Нет доступа.")
            return

        category_name, emoji_id = extract_text_and_custom_emoji(update.message)

        if not category_name:
            await update.message.reply_text(
                "Название категории пустое. Отправьте premium emoji вместе с текстом, например: [emoji] iPhone",
                reply_markup=cancel_admin_keyboard()
            )
            return

        category_id = add_category(category_name, emoji_id)
        clear_admin_temp_data(context)

        await update.message.reply_text(
            (
                "Категория добавлена ✅\n\n"
                f"ID: {category_id}\n"
                f"Название: {category_name}\n"
                f"Premium emoji: {'есть' if emoji_id else 'нет'}"
            ),
            reply_markup=admin_keyboard()
        )
        return

    if admin_state == "rename_category":
        if not is_admin_user(user_id) or not is_admin_logged(context):
            await update.message.reply_text("Нет доступа.")
            return

        category_id = context.user_data.get("edit_category_id")
        category_name, emoji_id = extract_text_and_custom_emoji(update.message)

        if not category_id:
            clear_admin_temp_data(context)
            await update.message.reply_text("Ошибка. Категория не найдена.", reply_markup=admin_keyboard())
            return

        if not category_name:
            await update.message.reply_text(
                "Название категории пустое.",
                reply_markup=cancel_admin_keyboard()
            )
            return

        try:
            rename_category(category_id, category_name, emoji_id)
            await update.message.reply_text(
                (
                    "Категория переименована ✅\n\n"
                    f"Новое название: {category_name}\n"
                    f"Premium emoji: {'есть' if emoji_id else 'нет'}"
                ),
                reply_markup=admin_keyboard()
            )
        except Exception as e:
            await update.message.reply_text(
                f"Ошибка переименования категории:\n{e}",
                reply_markup=admin_keyboard()
            )

        clear_admin_temp_data(context)
        return

    # ===== MODEL =====

    if admin_state == "add_model_name":
        if not is_admin_user(user_id) or not is_admin_logged(context):
            await update.message.reply_text("Нет доступа.")
            return

        model_name, emoji_id = extract_text_and_custom_emoji(update.message)

        if not model_name:
            await update.message.reply_text(
                "Название модели пустое. Отправьте premium emoji вместе с текстом, например: [emoji] iPhone 17",
                reply_markup=cancel_admin_keyboard()
            )
            return

        context.user_data["new_model_name"] = model_name
        context.user_data["new_model_emoji_id"] = emoji_id
        context.user_data["admin_state"] = "add_model_description"

        await update.message.reply_text(
            (
                "Введите описание модели.\n\n"
                "Если описание не нужно, напишите -"
            ),
            reply_markup=cancel_admin_keyboard()
        )
        return

    if admin_state == "add_model_description":
        if not is_admin_user(user_id) or not is_admin_logged(context):
            await update.message.reply_text("Нет доступа.")
            return

        category_id = context.user_data.get("new_model_category_id")
        model_name = context.user_data.get("new_model_name")
        emoji_id = context.user_data.get("new_model_emoji_id")
        description = "" if text == "-" else text

        if not category_id or not model_name:
            clear_admin_temp_data(context)
            await update.message.reply_text(
                "Ошибка добавления модели. Попробуйте заново.",
                reply_markup=admin_keyboard()
            )
            return

        model_id = add_model(category_id, model_name, description, emoji_id)
        clear_admin_temp_data(context)

        await update.message.reply_text(
            (
                "Модель добавлена ✅\n\n"
                f"ID: {model_id}\n"
                f"Название: {model_name}\n"
                f"Premium emoji: {'есть' if emoji_id else 'нет'}"
            ),
            reply_markup=admin_keyboard()
        )
        return

    if admin_state == "rename_model":
        if not is_admin_user(user_id) or not is_admin_logged(context):
            await update.message.reply_text("Нет доступа.")
            return

        model_id = context.user_data.get("edit_model_id")

        if not model_id:
            clear_admin_temp_data(context)
            await update.message.reply_text("Ошибка. Модель не найдена.", reply_markup=admin_keyboard())
            return

        rename_model(model_id, text)
        clear_admin_temp_data(context)

        await update.message.reply_text(
            f"Модель переименована ✅\n\nНовое название: {text}",
            reply_markup=admin_keyboard()
        )
        return

    if admin_state == "edit_model_description":
        if not is_admin_user(user_id) or not is_admin_logged(context):
            await update.message.reply_text("Нет доступа.")
            return

        model_id = context.user_data.get("edit_model_id")
        new_description = "" if text == "-" else text

        if not model_id:
            clear_admin_temp_data(context)
            await update.message.reply_text("Ошибка. Модель не найдена.", reply_markup=admin_keyboard())
            return

        update_model_description(model_id, new_description)
        clear_admin_temp_data(context)

        await update.message.reply_text(
            "Описание модели обновлено ✅",
            reply_markup=admin_keyboard()
        )
        return

    # ===== PRODUCT TYPE =====

    if admin_state == "add_type_name":
        if not is_admin_user(user_id) or not is_admin_logged(context):
            await update.message.reply_text("Нет доступа.")
            return

        type_name, emoji_id = extract_text_and_custom_emoji(update.message)

        if not type_name:
            await update.message.reply_text(
                "Название вида товара пустое. Отправьте premium emoji вместе с текстом, например: [emoji] e-Sim",
                reply_markup=cancel_admin_keyboard()
            )
            return

        context.user_data["new_type_name"] = type_name
        context.user_data["new_type_emoji_id"] = emoji_id
        context.user_data["admin_state"] = "add_type_description"

        await update.message.reply_text(
            (
                "Введите описание вида товара.\n\n"
                "Например: модели только с e-Sim.\n"
                "Если описание не нужно, напишите -"
            ),
            reply_markup=cancel_admin_keyboard()
        )
        return

    if admin_state == "add_type_description":
        if not is_admin_user(user_id) or not is_admin_logged(context):
            await update.message.reply_text("Нет доступа.")
            return

        model_id = context.user_data.get("new_type_model_id")
        type_name = context.user_data.get("new_type_name")
        emoji_id = context.user_data.get("new_type_emoji_id")
        description = "" if text == "-" else text

        if not model_id or not type_name:
            clear_admin_temp_data(context)
            await update.message.reply_text(
                "Ошибка добавления вида товара. Попробуйте заново.",
                reply_markup=admin_keyboard()
            )
            return

        type_id = add_type(model_id, type_name, description, emoji_id)
        clear_admin_temp_data(context)

        await update.message.reply_text(
            (
                "Вид товара добавлен ✅\n\n"
                f"ID: {type_id}\n"
                f"Название: {type_name}\n"
                f"Premium emoji: {'есть' if emoji_id else 'нет'}"
            ),
            reply_markup=admin_keyboard()
        )
        return

    if admin_state == "rename_type":
        if not is_admin_user(user_id) or not is_admin_logged(context):
            await update.message.reply_text("Нет доступа.")
            return

        type_id = context.user_data.get("edit_type_id")

        if not type_id:
            clear_admin_temp_data(context)
            await update.message.reply_text("Ошибка. Вид товара не найден.", reply_markup=admin_keyboard())
            return

        rename_type(type_id, text)
        clear_admin_temp_data(context)

        await update.message.reply_text(
            f"Вид товара переименован ✅\n\nНовое название: {text}",
            reply_markup=admin_keyboard()
        )
        return

    if admin_state == "edit_type_description":
        if not is_admin_user(user_id) or not is_admin_logged(context):
            await update.message.reply_text("Нет доступа.")
            return

        type_id = context.user_data.get("edit_type_id")
        description = "" if text == "-" else text

        if not type_id:
            clear_admin_temp_data(context)
            await update.message.reply_text("Ошибка. Вид товара не найден.", reply_markup=admin_keyboard())
            return

        update_type_description(type_id, description)
        clear_admin_temp_data(context)

        await update.message.reply_text(
            "Описание вида товара обновлено ✅",
            reply_markup=admin_keyboard()
        )
        return

    # ===== ADD PRODUCT =====

    if admin_state == "add_product_name":
        if not is_admin_user(user_id) or not is_admin_logged(context):
            await update.message.reply_text("Нет доступа.")
            return

        product_name, emoji_id = extract_text_and_custom_emoji(update.message)

        if not product_name:
            await update.message.reply_text(
                "Название товара пустое. Отправьте premium emoji вместе с текстом, например: [emoji] iPhone 17 256GB e-Sim Blue",
                reply_markup=cancel_admin_keyboard()
            )
            return

        context.user_data["new_product_name"] = product_name
        context.user_data["new_product_emoji_id"] = emoji_id
        context.user_data["admin_state"] = "add_product_description"

        await update.message.reply_text(
            (
                "Введите описание товара.\n\n"
                "Если описание не нужно, напишите -"
            ),
            reply_markup=cancel_admin_keyboard()
        )
        return

    if admin_state == "add_product_description":
        if not is_admin_user(user_id) or not is_admin_logged(context):
            await update.message.reply_text("Нет доступа.")
            return

        description = "" if text == "-" else text
        context.user_data["new_product_description"] = description
        context.user_data["admin_state"] = "add_product_photo"

        await update.message.reply_text(
            (
                "Отправьте фото товара.\n\n"
                "Если фото не нужно, напишите -"
            ),
            reply_markup=cancel_admin_keyboard()
        )
        return

    if admin_state == "add_product_photo":
        if not is_admin_user(user_id) or not is_admin_logged(context):
            await update.message.reply_text("Нет доступа.")
            return

        if text == "-":
            context.user_data["new_product_photo_file_id"] = None
            context.user_data["admin_state"] = "add_product_price"

            await update.message.reply_text(
                "Введите цену товара:",
                reply_markup=cancel_admin_keyboard()
            )
            return

        await update.message.reply_text(
            "Нужно отправить фото или написать -",
            reply_markup=cancel_admin_keyboard()
        )
        return

    # ===== EDIT PRODUCT =====

    if admin_state == "rename_product":
        if not is_admin_user(user_id) or not is_admin_logged(context):
            await update.message.reply_text("Нет доступа.")
            return

        product_id = context.user_data.get("edit_product_id")

        if not product_id:
            clear_admin_temp_data(context)
            await update.message.reply_text("Ошибка. Товар не найден.", reply_markup=admin_keyboard())
            return

        rename_product(product_id, text)
        clear_admin_temp_data(context)

        await update.message.reply_text(
            f"Название товара обновлено ✅\n\nНовое название: {text}",
            reply_markup=admin_keyboard()
        )
        return

    if admin_state == "edit_product_description":
        if not is_admin_user(user_id) or not is_admin_logged(context):
            await update.message.reply_text("Нет доступа.")
            return

        product_id = context.user_data.get("edit_product_id")
        description = "" if text == "-" else text

        if not product_id:
            clear_admin_temp_data(context)
            await update.message.reply_text("Ошибка. Товар не найден.", reply_markup=admin_keyboard())
            return

        update_product_description(product_id, description)
        clear_admin_temp_data(context)

        await update.message.reply_text(
            "Описание товара обновлено ✅",
            reply_markup=admin_keyboard()
        )
        return

    if admin_state == "edit_product_photo":
        if not is_admin_user(user_id) or not is_admin_logged(context):
            await update.message.reply_text("Нет доступа.")
            return

        product_id = context.user_data.get("edit_product_id")

        if not product_id:
            clear_admin_temp_data(context)
            await update.message.reply_text("Ошибка. Товар не найден.", reply_markup=admin_keyboard())
            return

        if text == "-":
            update_product_photo(product_id, None)
            clear_admin_temp_data(context)

            await update.message.reply_text(
                "Фото товара удалено ✅",
                reply_markup=admin_keyboard()
            )
            return

        await update.message.reply_text(
            "Отправьте новое фото или напишите - чтобы удалить фото.",
            reply_markup=cancel_admin_keyboard()
        )
        return

    if admin_state == "edit_product_price":
        if not is_admin_user(user_id) or not is_admin_logged(context):
            await update.message.reply_text("Нет доступа.")
            return

        product_id = context.user_data.get("edit_product_id")

        if not product_id:
            clear_admin_temp_data(context)
            await update.message.reply_text("Ошибка. Товар не найден.", reply_markup=admin_keyboard())
            return

        old_price = update_product_price(product_id, text, changed_by=user_id)
        clear_admin_temp_data(context)

        await update.message.reply_text(
            (
                "Цена товара обновлена ✅\n\n"
                f"Было: {old_price}\n"
                f"Стало: {text}"
            ),
            reply_markup=admin_keyboard()
        )
        return

    # ===== BULK PRICE UPDATE =====

    if admin_state == "bulk_prices":
        if not is_admin_user(user_id) or not is_admin_logged(context):
            await update.message.reply_text("Нет доступа.")
            return

        updated = []
        errors = []
        lines = text.splitlines()

        for line in lines:
            line = line.strip()

            if not line:
                continue

            if "=" not in line:
                errors.append(f"{line} — нет знака =")
                continue

            left, right = line.split("=", 1)
            left = left.strip().replace("#", "")
            new_price = right.strip()

            try:
                product_id = int(left)
            except ValueError:
                errors.append(f"{line} — неверный ID")
                continue

            product = get_product(product_id)

            if not product:
                errors.append(f"#{product_id} — товар не найден")
                continue

            old_price = update_product_price(product_id, new_price, changed_by=user_id)
            updated.append(f"#{product_id}: {old_price} → {new_price}")

        clear_admin_temp_data(context)

        result = "Массовое обновление цен завершено ✅\n\n"

        if updated:
            result += "Обновлено:\n" + "\n".join(updated[:30]) + "\n\n"

        if errors:
            result += "Ошибки:\n" + "\n".join(errors[:30])

        await update.message.reply_text(
            result,
            reply_markup=admin_keyboard()
        )
        return

    # ===== NORMAL TEXT =====

    if text == "📦 Каталог":
        await send_catalog(update, context)
        return

    if text == "🛒 Корзина":
        await send_cart_message(update, context)
        return

    await update.message.reply_text(
        "Нажмите кнопку 📦 Каталог или 🛒 Корзина внизу.",
        reply_markup=reply_menu
    )


async def send_cart_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines, valid_product_ids = build_cart_lines(context)

    if not valid_product_ids:
        await update.message.reply_text(
            wide_text("Корзина\n\nКорзина пока пустая."),
            reply_markup=reply_menu
        )
        return

    text_msg = (
        "Корзина\n\n"
        + "\n".join(lines)
        + f"\n\nПозиций в корзине: {len(valid_product_ids)}"
    )

    await update.message.reply_text(
        text_msg,
        reply_markup=cart_markup(context)
    )


# =========================
# PHOTO HANDLER
# =========================

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    admin_state = context.user_data.get("admin_state")

    if not is_admin_user(user_id) or not is_admin_logged(context):
        return

    if admin_state == "add_product_photo":
        photo_file_id = update.message.photo[-1].file_id

        context.user_data["new_product_photo_file_id"] = photo_file_id
        context.user_data["admin_state"] = "add_product_price"

        await update.message.reply_text(
            "Фото сохранено ✅\n\nТеперь введите цену товара:",
            reply_markup=cancel_admin_keyboard()
        )
        return

    if admin_state == "edit_product_photo":
        product_id = context.user_data.get("edit_product_id")

        if not product_id:
            clear_admin_temp_data(context)
            await update.message.reply_text("Ошибка. Товар не найден.", reply_markup=admin_keyboard())
            return

        photo_file_id = update.message.photo[-1].file_id
        update_product_photo(product_id, photo_file_id)
        clear_admin_temp_data(context)

        await update.message.reply_text(
            "Фото товара обновлено ✅",
            reply_markup=admin_keyboard()
        )
        return


# =========================
# CALLBACK HANDLER
# =========================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    # ===== CLIENT CATALOG =====

    if data == "catalog":
        categories = get_categories()

        if not categories:
            await safe_show_text(query, "Каталог\n\nКаталог пока пустой.")
            return

        await safe_show_text(
            query,
            CATALOG_TEXT,
            catalog_keyboard()
        )

    elif data.startswith("cat_"):
        category_id = int(data.replace("cat_", ""))
        category = get_category(category_id)

        if not category:
            await safe_show_text(query, "Категория не найдена.", catalog_keyboard())
            return

        models = get_models_by_category(category_id)

        buttons = [
            pbutton(name, f"model_{model_id}", emoji_id=emoji_id)
            for model_id, name, description, emoji_id in models
        ]

        keyboard = make_two_columns(buttons)
        keyboard.append([danger_button("↩️ Назад в каталог", "catalog")])

        if not models:
            text_msg = f"Категория: {category[1]}\n\nМоделей пока нет."
        else:
            text_msg = f"Категория: {category[1]}\n\nВыберите модель:"

        await safe_show_text(query, text_msg, InlineKeyboardMarkup(keyboard))

    elif data.startswith("model_"):
        model_id = int(data.replace("model_", ""))
        model = get_model(model_id)

        if not model:
            await safe_show_text(query, "Модель не найдена.", catalog_keyboard())
            return

        model_id, model_name, description, category_id, category_name = model
        types = get_types_by_model(model_id)

        buttons = [
            pbutton(type_name, f"type_{type_id}", emoji_id=emoji_id)
            for type_id, type_name, type_description, emoji_id in types
        ]

        keyboard = make_two_columns(buttons)
        keyboard.append([danger_button("↩️ Назад к категориям", f"cat_{category_id}")])
        keyboard.append([default_button("📦 Вернуться в каталог", "catalog")])

        text_msg = f"{model_name}\n\nКатегория: {category_name}\n"

        if description:
            text_msg += f"\nОписание:\n{description}\n"

        if not types:
            text_msg += "\nВидов товара пока нет."
        else:
            text_msg += "\nВыберите вид товара:"

        await safe_show_text(query, text_msg, InlineKeyboardMarkup(keyboard))

    elif data.startswith("type_"):
        type_id = int(data.replace("type_", ""))
        product_type = get_type(type_id)

        if not product_type:
            await safe_show_text(query, "Вид товара не найден.", catalog_keyboard())
            return

        (
            type_id,
            type_name,
            type_description,
            model_id,
            model_name,
            category_id,
            category_name
        ) = product_type

        products = get_products_by_type(type_id)

        buttons = [
            pbutton(product_name, f"product_{product_id}", emoji_id=emoji_id)
            for product_id, product_name, product_description, photo_file_id, price, emoji_id in products
        ]

        keyboard = make_two_columns(buttons)
        keyboard.append([danger_button("↩️ Назад к модели", f"model_{model_id}")])
        keyboard.append([default_button("📦 Вернуться в каталог", "catalog")])

        text_msg = (
            f"{type_name}\n\n"
            f"Категория: {category_name}\n"
            f"Модель: {model_name}\n"
        )

        if type_description:
            text_msg += f"\nОписание:\n{type_description}\n"

        if not products:
            text_msg += "\nТоваров пока нет."
        else:
            text_msg += "\nВыберите товар:"

        await safe_show_text(query, text_msg, InlineKeyboardMarkup(keyboard))

    elif data.startswith("product_"):
        product_id = int(data.replace("product_", ""))
        product = get_product(product_id)

        if not product:
            await safe_show_text(query, "Товар не найден.", catalog_keyboard())
            return

        await show_product_card(query, product, context)

    elif data.startswith("qty_minus_"):
        product_id = int(data.replace("qty_minus_", ""))
        current_qty = get_product_qty(context, product_id)
        set_product_qty(context, product_id, current_qty - 1)
        await update_product_card(query, context, product_id)

    elif data.startswith("qty_plus_"):
        product_id = int(data.replace("qty_plus_", ""))
        current_qty = get_product_qty(context, product_id)
        set_product_qty(context, product_id, current_qty + 1)
        await update_product_card(query, context, product_id)

    elif data.startswith("qty_show_"):
        product_id = int(data.replace("qty_show_", ""))
        qty = get_product_qty(context, product_id)
        await query.answer(f"Количество: {qty} шт.")

    elif data.startswith("addcart_"):
        product_id = int(data.replace("addcart_", ""))
        product = get_product(product_id)

        if not product:
            await safe_show_text(query, "Товар не найден.")
            return

        qty = get_product_qty(context, product_id)
        add_product_to_cart(context, product_id, qty)

        price_value = parse_price_to_int(product[4])
        total_price = price_value * qty if price_value is not None else None

        text_msg = (
            "Товар добавлен в корзину ✅\n\n"
            f"{product[1]}\n"
            f"Количество: {qty} шт.\n"
            f"Цена за шт: {product[4]}\n"
        )

        if total_price is not None:
            text_msg += f"Общая цена: {format_money(total_price)}"
        else:
            text_msg += "Общая цена: не посчитана"

        await safe_show_text(
            query,
            text_msg,
            InlineKeyboardMarkup([
                [success_button("✅ Оформить заказ", "checkout")],
                [primary_button("🛒 Корзина", "cart")],
                [primary_button("Продолжить покупки", "catalog")],
            ])
        )

    elif data.startswith("buy_"):
        product_id = int(data.replace("buy_", ""))
        product = get_product(product_id)

        if not product:
            await safe_show_text(query, "Товар не найден.")
            return

        qty = get_product_qty(context, product_id)
        checkout_items = [product_id] * qty
        set_checkout_items(context, checkout_items)
        context.user_data["checkout_source"] = "single"
        context.user_data["order_state"] = "wait_order_name"

        lines, valid_product_ids = build_cart_lines(context, checkout_items)

        await safe_show_text(
            query,
            (
                "Оформление заказа\n\n"
                f"Товар:\n{chr(10).join(lines)}\n\n"
                "Введите имя и фамилию:"
            ),
            reply_markup=order_menu
        )

    elif data == "cart":
        lines, valid_product_ids = build_cart_lines(context)

        if not valid_product_ids:
            await safe_show_text(
                query,
                "Корзина\n\nКорзина пока пустая.",
                InlineKeyboardMarkup([
                    [default_button("📦 Вернуться в каталог", "catalog")]
                ])
            )
            return

        text_msg = (
            "Корзина\n\n"
            + "\n".join(lines)
            + f"\n\nПозиций в корзине: {len(valid_product_ids)}"
        )

        await safe_show_text(
            query,
            text_msg,
            cart_markup(context)
        )

    elif data == "cart_delete_menu":
        lines, valid_product_ids = build_cart_lines(context)

        if not valid_product_ids:
            await safe_show_text(
                query,
                "Корзина\n\nКорзина пока пустая.",
                InlineKeyboardMarkup([
                    [default_button("📦 Вернуться в каталог", "catalog")]
                ])
            )
            return

        text_msg = (
            "Удаление товара из корзины\n\n"
            "Выберите позицию, которую нужно убрать:\n\n"
            + "\n".join(lines)
        )

        await safe_show_text(
            query,
            text_msg,
            cart_delete_markup(context)
        )

    elif data.startswith("remove_cart_product_"):
        try:
            product_id = int(data.replace("remove_cart_product_", ""))
        except ValueError:
            await safe_show_text(query, "Ошибка удаления товара.")
            return

        removed = remove_cart_product(context, product_id)

        if not removed:
            await safe_show_text(
                query,
                "Товар уже удалён или не найден.",
                InlineKeyboardMarkup([
                    [default_button("📦 Вернуться в каталог", "catalog")]
                ])
            )
            return

        lines, valid_product_ids = build_cart_lines(context)

        if not valid_product_ids:
            await safe_show_text(
                query,
                "Корзина\n\nКорзина теперь пустая.",
                InlineKeyboardMarkup([
                    [default_button("📦 Вернуться в каталог", "catalog")]
                ])
            )
            return

        text_msg = (
            "Корзина\n\n"
            + "\n".join(lines)
            + f"\n\nПозиций в корзине: {len(valid_product_ids)}"
        )

        await safe_show_text(
            query,
            text_msg,
            cart_markup(context)
        )

    elif data.startswith("remove_cart_"):
        try:
            item_index = int(data.replace("remove_cart_", ""))
        except ValueError:
            await safe_show_text(query, "Ошибка удаления позиции.")
            return

        removed = remove_cart_item_by_index(context, item_index)

        if not removed:
            await safe_show_text(
                query,
                "Позиция уже удалена или не найдена.",
                InlineKeyboardMarkup([
                    [default_button("📦 Вернуться в каталог", "catalog")]
                ])
            )
            return

        lines, valid_product_ids = build_cart_lines(context)

        if not valid_product_ids:
            await safe_show_text(
                query,
                "Корзина\n\nКорзина теперь пустая.",
                InlineKeyboardMarkup([
                    [default_button("📦 Вернуться в каталог", "catalog")]
                ])
            )
            return

        text_msg = (
            "Корзина\n\n"
            + "\n".join(lines)
            + f"\n\nПозиций в корзине: {len(valid_product_ids)}"
        )

        await safe_show_text(
            query,
            text_msg,
            cart_markup(context)
        )

    elif data == "clear_cart":
        clear_cart(context)

        await safe_show_text(
            query,
            "Корзина очищена ✅",
            InlineKeyboardMarkup([
                [default_button("📦 Вернуться в каталог", "catalog")]
            ])
        )

    elif data == "checkout":
        lines, valid_product_ids = build_cart_lines(context)

        if not valid_product_ids:
            await safe_show_text(
                query,
                "Корзина пустая. Сначала добавьте товар.",
                InlineKeyboardMarkup([
                    [default_button("📦 Вернуться в каталог", "catalog")]
                ])
            )
            return

        set_checkout_items(context, valid_product_ids)
        context.user_data["checkout_source"] = "cart"
        context.user_data["order_state"] = "wait_order_name"

        await safe_show_text(
            query,
            (
                "Оформление заказа\n\n"
                f"Товары:\n{chr(10).join(lines)}\n\n"
                "Введите имя и фамилию:"
            ),
            reply_markup=order_menu
        )

    # ===== ADMIN ADD =====

    elif data == "admin_add_category":
        if not is_admin_user(query.from_user.id) or not is_admin_logged(context):
            await safe_show_text(query, "Нет доступа.")
            return

        context.user_data["admin_state"] = "add_category_name"
        await safe_show_text(
            query,
            "➕ Добавление категории\n\nВведите название новой категории.\n\nМожно отправить premium emoji + текст.",
            cancel_admin_keyboard()
        )

    elif data == "admin_add_model":
        if not is_admin_user(query.from_user.id) or not is_admin_logged(context):
            await safe_show_text(query, "Нет доступа.")
            return

        categories = get_categories()

        if not categories:
            await safe_show_text(query, "Категорий пока нет.\n\nСначала добавьте хотя бы одну категорию.", admin_keyboard())
            return

        await safe_show_text(
            query,
            "➕ Добавление модели\n\nВыберите категорию для новой модели:",
            admin_choose_category_for_model_keyboard(page=0)
        )

    elif data.startswith("admin_add_model_page_"):
        page = int(data.replace("admin_add_model_page_", ""))
        await safe_show_text(
            query,
            "➕ Добавление модели\n\nВыберите категорию для новой модели:",
            admin_choose_category_for_model_keyboard(page=page)
        )

    elif data.startswith("admin_model_cat_"):
        category_id = int(data.replace("admin_model_cat_", ""))

        context.user_data["new_model_category_id"] = category_id
        context.user_data["admin_state"] = "add_model_name"

        await safe_show_text(
            query,
            "Введите название модели.\n\nНапример: iPhone 17\n\nМожно отправить premium emoji + текст.",
            cancel_admin_keyboard()
        )

    elif data == "admin_add_type":
        if not is_admin_user(query.from_user.id) or not is_admin_logged(context):
            await safe_show_text(query, "Нет доступа.")
            return

        models = get_all_models()

        if not models:
            await safe_show_text(query, "Моделей пока нет.\n\nСначала добавьте хотя бы одну модель.", admin_keyboard())
            return

        await safe_show_text(
            query,
            "➕ Добавление вида товара\n\nВыберите модель:",
            admin_choose_model_for_type_keyboard(page=0)
        )

    elif data.startswith("admin_add_type_page_"):
        page = int(data.replace("admin_add_type_page_", ""))
        await safe_show_text(
            query,
            "➕ Добавление вида товара\n\nВыберите модель:",
            admin_choose_model_for_type_keyboard(page=page)
        )

    elif data.startswith("admin_type_model_"):
        model_id = int(data.replace("admin_type_model_", ""))

        context.user_data["new_type_model_id"] = model_id
        context.user_data["admin_state"] = "add_type_name"

        await safe_show_text(
            query,
            "Введите название вида товара.\n\nНапример: e-Sim, Ростест, Global, Pro Max\n\nМожно отправить premium emoji + текст.",
            cancel_admin_keyboard()
        )

    elif data == "admin_add_product":
        if not is_admin_user(query.from_user.id) or not is_admin_logged(context):
            await safe_show_text(query, "Нет доступа.")
            return

        types = get_all_types()

        if not types:
            await safe_show_text(query, "Видов товара пока нет.\n\nСначала добавьте хотя бы один вид товара.", admin_keyboard())
            return

        await safe_show_text(
            query,
            "➕ Добавление товара\n\nВыберите вид товара:",
            admin_choose_type_for_product_keyboard(page=0)
        )

    elif data.startswith("admin_add_product_page_"):
        page = int(data.replace("admin_add_product_page_", ""))
        await safe_show_text(
            query,
            "➕ Добавление товара\n\nВыберите вид товара:",
            admin_choose_type_for_product_keyboard(page=page)
        )

    elif data.startswith("admin_product_type_"):
        type_id = int(data.replace("admin_product_type_", ""))

        context.user_data["new_product_type_id"] = type_id
        context.user_data["admin_state"] = "add_product_name"

        await safe_show_text(
            query,
            (
                "Введите название товара.\n\n"
                "Например:\n"
                "iPhone 17 256GB e-Sim Blue\n\n"
                "Можно отправить premium emoji + текст."
            ),
            cancel_admin_keyboard()
        )

    elif data == "admin_add_admin":
        if not is_main_admin(query.from_user.id) or not is_admin_logged(context):
            await safe_show_text(
                query,
                "Нет доступа. Добавлять админов может только основной админ.",
                admin_keyboard()
            )
            return

        context.user_data["admin_state"] = "add_admin_id"

        await safe_show_text(
            query,
            (
                "👥 Добавление админа\n\n"
                "Отправьте Telegram ID сотрудника.\n\n"
                "Например:\n"
                "707131428"
            ),
            cancel_admin_keyboard()
        )

    elif data == "admin_list_admins":
        if not is_main_admin(query.from_user.id) or not is_admin_logged(context):
            await safe_show_text(
                query,
                "Нет доступа. Смотреть список админов может только основной админ.",
                admin_keyboard()
            )
            return

        admins = get_admins_list()
        main_admin_id = get_admin_id()

        lines = [
            "📋 Список админов\n",
            f"Основной админ: {main_admin_id}\n"
        ]

        if not admins:
            lines.append("Дополнительных админов пока нет.")
        else:
            for index, admin in enumerate(admins, start=1):
                telegram_id, username, full_name, role, created_at = admin
                username_text = username or "username не указан"
                full_name_text = full_name or "имя не указано"
                lines.append(
                    f"{index}. ID: {telegram_id}\n"
                    f"   Username: {username_text}\n"
                    f"   Имя: {full_name_text}\n"
                    f"   Роль: {role}\n"
                )

        await safe_show_text(
            query,
            "\n".join(lines),
            admin_keyboard()
        )

    elif data == "admin_delete_admin":
        if not is_main_admin(query.from_user.id) or not is_admin_logged(context):
            await safe_show_text(
                query,
                "Нет доступа. Удалять админов может только основной админ.",
                admin_keyboard()
            )
            return

        admins = get_admins_list()

        if not admins:
            await safe_show_text(
                query,
                "Дополнительных админов пока нет.",
                admin_keyboard()
            )
            return

        lines = ["❌ Удаление админа\n", "Список админов:\n"]

        for index, admin in enumerate(admins, start=1):
            telegram_id, username, full_name, role, created_at = admin
            username_text = username or "username не указан"
            full_name_text = full_name or "имя не указано"
            lines.append(
                f"{index}. ID: {telegram_id}\n"
                f"   Username: {username_text}\n"
                f"   Имя: {full_name_text}\n"
            )

        lines.append("\nОтправьте Telegram ID админа, которого нужно удалить:")

        context.user_data["admin_state"] = "delete_admin_id"

        await safe_show_text(
            query,
            "\n".join(lines),
            cancel_admin_keyboard()
        )

    # ===== ADMIN BULK PRICES =====

    elif data == "admin_bulk_prices":
        if not is_admin_user(query.from_user.id) or not is_admin_logged(context):
            await safe_show_text(query, "Нет доступа.")
            return

        products = get_all_products()

        if not products:
            await safe_show_text(query, "Товаров пока нет.", admin_keyboard())
            return

        lines = []

        for product_id, category_name, model_name, type_name, product_name, price in products[:80]:
            lines.append(f"#{product_id} — {product_name} — {price}")

        text = (
            "⚡ Массовое обновление цен\n\n"
            "Список товаров:\n\n"
            + "\n".join(lines)
            + "\n\nОтправьте цены в формате:\n"
            "ID = новая цена\n\n"
            "Пример:\n"
            "25 = 118000\n"
            "26 = 132000"
        )

        context.user_data["admin_state"] = "bulk_prices"
        await safe_show_text(query, text, cancel_admin_keyboard())

    # ===== ADMIN EDIT CATEGORIES =====

    elif data == "admin_edit_categories":
        categories = get_categories()

        if not categories:
            await safe_show_text(query, "Редактор категорий\n\nКатегорий пока нет.", admin_keyboard())
            return

        await safe_show_text(
            query,
            "Редактор категорий\n\nВыберите категорию для редактирования:",
            admin_edit_categories_keyboard(page=0)
        )

    elif data.startswith("admin_edit_categories_page_"):
        page = int(data.replace("admin_edit_categories_page_", ""))
        await safe_show_text(
            query,
            "Редактор категорий\n\nВыберите категорию для редактирования:",
            admin_edit_categories_keyboard(page=page)
        )

    elif data.startswith("admin_edit_category_"):
        category_id = int(data.replace("admin_edit_category_", ""))
        category = get_category(category_id)

        if not category:
            await safe_show_text(query, "Категория не найдена.", admin_keyboard())
            return

        category_id, category_name = category

        await safe_show_text(
            query,
            (
                f"Категория #{category_id}\n\n"
                f"Название: {category_name}\n\n"
                "Выберите действие:"
            ),
            InlineKeyboardMarkup([
                [button("Переименовать категорию", f"admin_rename_category_{category_id}")],
                [button("Удалить категорию", f"admin_delete_category_{category_id}")],
                [button("Назад к категориям", "admin_edit_categories")],
            ])
        )

    elif data.startswith("admin_rename_category_"):
        category_id = int(data.replace("admin_rename_category_", ""))
        context.user_data["edit_category_id"] = category_id
        context.user_data["admin_state"] = "rename_category"

        await safe_show_text(
            query,
            "Введите новое название категории.\n\nМожно отправить premium emoji + текст.",
            cancel_admin_keyboard()
        )

    elif data.startswith("admin_delete_category_"):
        category_id = int(data.replace("admin_delete_category_", ""))
        delete_category(category_id)

        await safe_show_text(query, "Категория удалена ✅\n\nОна больше не отображается в каталоге.", admin_keyboard())

    # ===== ADMIN EDIT MODELS =====

    elif data == "admin_edit_models":
        models = get_all_models()

        if not models:
            await safe_show_text(query, "Редактор моделей\n\nМоделей пока нет.", admin_keyboard())
            return

        await safe_show_text(
            query,
            "Редактор моделей\n\nВыберите модель для редактирования:",
            admin_edit_models_keyboard(page=0)
        )

    elif data.startswith("admin_edit_models_page_"):
        page = int(data.replace("admin_edit_models_page_", ""))
        await safe_show_text(
            query,
            "Редактор моделей\n\nВыберите модель для редактирования:",
            admin_edit_models_keyboard(page=page)
        )

    elif data.startswith("admin_edit_model_"):
        model_id = int(data.replace("admin_edit_model_", ""))
        model = get_model(model_id)

        if not model:
            await safe_show_text(query, "Модель не найдена.", admin_keyboard())
            return

        model_id, model_name, description, category_id, category_name = model
        text_msg = (
            f"Модель #{model_id}\n\n"
            f"Категория: {category_name}\n"
            f"Название: {model_name}\n"
        )

        if description:
            text_msg += f"\nОписание:\n{description}\n"
        else:
            text_msg += "\nОписание: не указано\n"

        await safe_show_text(
            query,
            text_msg,
            InlineKeyboardMarkup([
                [button("Переименовать модель", f"admin_rename_model_{model_id}")],
                [button("Изменить описание", f"admin_model_desc_{model_id}")],
                [button("Удалить модель", f"admin_delete_model_{model_id}")],
                [button("Назад к моделям", "admin_edit_models")],
            ])
        )

    elif data.startswith("admin_rename_model_"):
        model_id = int(data.replace("admin_rename_model_", ""))
        context.user_data["edit_model_id"] = model_id
        context.user_data["admin_state"] = "rename_model"

        await safe_show_text(query, "Введите новое название модели:", cancel_admin_keyboard())

    elif data.startswith("admin_model_desc_"):
        model_id = int(data.replace("admin_model_desc_", ""))
        context.user_data["edit_model_id"] = model_id
        context.user_data["admin_state"] = "edit_model_description"

        await safe_show_text(
            query,
            "Введите новое описание модели.\n\nЕсли описание нужно очистить, отправьте -",
            cancel_admin_keyboard()
        )

    elif data.startswith("admin_delete_model_"):
        model_id = int(data.replace("admin_delete_model_", ""))
        delete_model(model_id)
        await safe_show_text(query, "Модель удалена ✅\n\nОна больше не отображается в каталоге.", admin_keyboard())

    # ===== ADMIN EDIT TYPES =====

    elif data == "admin_edit_types":
        types = get_all_types()

        if not types:
            await safe_show_text(query, "Редактор видов товара\n\nВидов товара пока нет.", admin_keyboard())
            return

        await safe_show_text(
            query,
            "Редактор видов товара\n\nВыберите вид товара:",
            admin_edit_types_keyboard(page=0)
        )

    elif data.startswith("admin_edit_types_page_"):
        page = int(data.replace("admin_edit_types_page_", ""))
        await safe_show_text(
            query,
            "Редактор видов товара\n\nВыберите вид товара:",
            admin_edit_types_keyboard(page=page)
        )

    elif data.startswith("admin_edit_type_"):
        type_id = int(data.replace("admin_edit_type_", ""))
        product_type = get_type(type_id)

        if not product_type:
            await safe_show_text(query, "Вид товара не найден.", admin_keyboard())
            return

        (
            type_id,
            type_name,
            description,
            model_id,
            model_name,
            category_id,
            category_name
        ) = product_type

        text_msg = (
            f"Вид товара #{type_id}\n\n"
            f"Категория: {category_name}\n"
            f"Модель: {model_name}\n"
            f"Название: {type_name}\n"
        )

        if description:
            text_msg += f"\nОписание:\n{description}\n"
        else:
            text_msg += "\nОписание: не указано\n"

        await safe_show_text(
            query,
            text_msg,
            InlineKeyboardMarkup([
                [button("Переименовать вид товара", f"admin_rename_type_{type_id}")],
                [button("Изменить описание", f"admin_type_desc_{type_id}")],
                [button("Удалить вид товара", f"admin_delete_type_{type_id}")],
                [button("Назад к видам товара", "admin_edit_types")],
            ])
        )

    elif data.startswith("admin_rename_type_"):
        type_id = int(data.replace("admin_rename_type_", ""))
        context.user_data["edit_type_id"] = type_id
        context.user_data["admin_state"] = "rename_type"

        await safe_show_text(query, "Введите новое название вида товара:", cancel_admin_keyboard())

    elif data.startswith("admin_type_desc_"):
        type_id = int(data.replace("admin_type_desc_", ""))
        context.user_data["edit_type_id"] = type_id
        context.user_data["admin_state"] = "edit_type_description"

        await safe_show_text(
            query,
            "Введите новое описание вида товара.\n\nЕсли описание нужно очистить, отправьте -",
            cancel_admin_keyboard()
        )

    elif data.startswith("admin_delete_type_"):
        type_id = int(data.replace("admin_delete_type_", ""))
        delete_type(type_id)
        await safe_show_text(query, "Вид товара удалён ✅\n\nОн больше не отображается в каталоге.", admin_keyboard())

    # ===== ADMIN EDIT PRODUCTS =====

    elif data == "admin_products":
        products = get_all_products()

        if not products:
            await safe_show_text(query, "Редактор товаров\n\nТоваров пока нет.", admin_keyboard())
            return

        await safe_show_text(
            query,
            "Редактор товаров\n\nВыберите товар для редактирования:",
            admin_products_keyboard(page=0)
        )

    elif data.startswith("admin_products_page_"):
        page = int(data.replace("admin_products_page_", ""))
        await safe_show_text(
            query,
            "Редактор товаров\n\nВыберите товар для редактирования:",
            admin_products_keyboard(page=page)
        )

    elif data.startswith("admin_product_"):
        product_id = int(data.replace("admin_product_", ""))
        product = get_product(product_id)

        if not product:
            await safe_show_text(query, "Товар не найден.", admin_keyboard())
            return

        (
            product_id,
            product_name,
            description,
            photo_file_id,
            price,
            type_id,
            type_name,
            model_id,
            model_name,
            category_id,
            category_name
        ) = product

        text_msg = (
            f"Товар #{product_id}\n\n"
            f"Категория: {category_name}\n"
            f"Модель: {model_name}\n"
            f"Вид товара: {type_name}\n"
            f"Название: {product_name}\n"
            f"Цена: {price}\n"
            f"Фото: {'есть' if photo_file_id else 'нет'}\n"
        )

        if description:
            text_msg += f"\nОписание:\n{description}"

        await safe_show_text(
            query,
            text_msg,
            InlineKeyboardMarkup([
                [button("Переименовать товар", f"admin_product_name_{product_id}")],
                [button("Изменить описание", f"admin_product_desc_{product_id}")],
                [button("Изменить фото", f"admin_product_photo_{product_id}")],
                [button("Изменить цену", f"admin_product_price_{product_id}")],
                [button("Удалить товар", f"admin_product_delete_{product_id}")],
                [button("Назад к товарам", "admin_products")],
            ])
        )

    elif data.startswith("admin_product_name_"):
        product_id = int(data.replace("admin_product_name_", ""))
        context.user_data["edit_product_id"] = product_id
        context.user_data["admin_state"] = "rename_product"

        await safe_show_text(query, "Введите новое название товара:", cancel_admin_keyboard())

    elif data.startswith("admin_product_desc_"):
        product_id = int(data.replace("admin_product_desc_", ""))
        context.user_data["edit_product_id"] = product_id
        context.user_data["admin_state"] = "edit_product_description"

        await safe_show_text(
            query,
            "Введите новое описание товара.\n\nЕсли описание нужно очистить, отправьте -",
            cancel_admin_keyboard()
        )

    elif data.startswith("admin_product_photo_"):
        product_id = int(data.replace("admin_product_photo_", ""))
        context.user_data["edit_product_id"] = product_id
        context.user_data["admin_state"] = "edit_product_photo"

        await safe_show_text(
            query,
            "Отправьте новое фото товара.\n\nЕсли фото нужно удалить, отправьте -",
            cancel_admin_keyboard()
        )

    elif data.startswith("admin_product_price_"):
        product_id = int(data.replace("admin_product_price_", ""))
        context.user_data["edit_product_id"] = product_id
        context.user_data["admin_state"] = "edit_product_price"

        await safe_show_text(query, "Введите новую цену товара:", cancel_admin_keyboard())

    elif data.startswith("admin_product_delete_"):
        product_id = int(data.replace("admin_product_delete_", ""))
        delete_product(product_id)

        await safe_show_text(
            query,
            "Товар удалён ✅\n\nОн больше не отображается в каталоге.",
            admin_keyboard()
        )

    # ===== ADMIN NAV =====

    elif data == "admin_cancel":
        if not is_admin_user(query.from_user.id) or not is_admin_logged(context):
            await safe_show_text(query, "Нет доступа.")
            return

        await delete_saved_prompt(context, query.message.chat_id, "admin_login_prompt_id")
        await delete_saved_prompt(context, query.message.chat_id, "admin_password_prompt_id")
        clear_admin_temp_data(context)
        await safe_show_text(query, ADMIN_PANEL_TEXT, admin_keyboard())

    elif data == "admin_menu":
        if not is_admin_user(query.from_user.id) or not is_admin_logged(context):
            await safe_show_text(query, "Нет доступа.")
            return

        await safe_show_text(query, ADMIN_PANEL_TEXT, admin_keyboard())

    elif data == "admin_logout":
        context.user_data["admin_logged"] = False
        clear_admin_temp_data(context)
        await safe_show_text(query, "Вы вышли из админ-панели.")


# =========================
# MAIN
# =========================

def main():
    token = get_token()

    print("Проверка переменных Railway...")
    print("BOT_TOKEN найден:", bool(token))
    print("DATABASE_URL найден:", bool(get_database_url()))
    print("ADMIN_ID найден:", bool(get_admin_id()))

    if not token:
        print("Ошибка: BOT_TOKEN не найден.")
        return

    if not get_database_url():
        print("Ошибка: DATABASE_URL не найден.")
        return

    init_db()
    print("База данных готова.")

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("price", price_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
