import os
import random
import re
import json
import hashlib
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
# Если нужно шире/уже - меняй число 30.
WIDE_MESSAGE_PAD = "⠀" * 30


def wide_text(text):
    if not text:
        return text
    return f"{text}\n{WIDE_MESSAGE_PAD}"


ADMIN_PANEL_TEXT = (
    "⚙️ Админ-панель\n\n"
    "Выберите действие для управления каталогом:"
)

CATALOG_TEXT = (
    "Каталог товаров\n\n"
    "Выберите бренд:"
)

ABOUT_TEXT = (
    "ℹ️ О нас\n\n"
    "Мы занимаемся продажей качественной техники и аксессуаров.\n"
    "Помогаем подобрать подходящий товар, консультируем по наличию, "
    "ценам и доставке.\n\n"
    "Для заказа выберите товар в каталоге и оформите корзину."
)

BULK_CATALOG_HELP_TEXT = (
    "📦 Массовое добавление каталога\n\n"
    "Отправьте товары строками через разделитель |\n\n"
    "Основной формат:\n"
    "Бренд | Категория | Серия | Модель | Симка | Память | Цвет | Полное название товара | Цена | Описание\n\n"
    "Серия и Симка необязательные. Если их нет, можно написать - или оставить пусто между разделителями.\n\n"
    "Примеры:\n"
    "Apple | Смартфоны | 15 серия | iPhone 15 Pro | eSIM | 256GB | Blue | iPhone 15 Pro 256GB eSIM Blue | 118000 | Новый, оригинал\n"
    "Apple | Смартфоны | - | iPhone 15 | - | 128GB | Black | iPhone 15 128GB Black | 89000\n"
    "Samsung | Смартфоны | S | S24 Ultra | 2 SIM | 512GB | Titanium Gray | Samsung S24 Ultra 512GB 2 SIM Titanium Gray | 125000\n\n"
    "Короткий формат без серии и симки тоже поддерживается:\n"
    "Бренд | Категория | Модель | Память | Цвет | Полное название товара | Цена | Описание\n\n"
    "Важно:\n"
    "— фото массово не добавляются, их можно потом поставить через редактор товара\n"
    "— если такой товар уже есть, бот обновит цену и описание, а дубль не создаст"
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


def get_orders_storage_limit_bytes():
    """Лимит хранения заказов. По умолчанию 3 ГБ.

    При желании можно переопределить в Railway переменной
    ORDERS_STORAGE_LIMIT_GB, например 2.5 или 5.
    """
    raw_value = get_env("ORDERS_STORAGE_LIMIT_GB", "3")

    try:
        gigabytes = float(str(raw_value).replace(",", "."))
    except (TypeError, ValueError):
        gigabytes = 3.0

    if gigabytes <= 0:
        gigabytes = 3.0

    return int(gigabytes * 1024 * 1024 * 1024)


def get_orders_cleanup_target_bytes():
    # Чистим с запасом до 85% лимита, чтобы новые заказы
    # некоторое время писались в уже освобожденное место.
    return int(get_orders_storage_limit_bytes() * 0.85)


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
                entity.length,
            )

    cleaned_text = " ".join(cleaned_text.split()).strip()
    return cleaned_text, emoji_id


# =========================
# ORDER HELPERS
# =========================

def normalize_ru_phone(raw_phone):
    digits = re.sub(r"\D", "", raw_phone or "")

    if len(digits) == 10 and digits[0] in ["9", "8"]:
        digits = "8" + digits

    if len(digits) == 11 and digits.startswith("7"):
        digits = "8" + digits[1:]

    if len(digits) != 11:
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

    if re.search(r"(^|[\s,])г\.\s*[а-яёa-z]", lower, re.IGNORECASE):
        return True

    if re.search(r"(^|[\s,])город\s+[а-яёa-z]", lower, re.IGNORECASE):
        return True

    parts = [part.strip() for part in text.split(",") if part.strip()]
    if len(parts) >= 2 and re.search(r"[а-яёa-z]", parts[0], re.IGNORECASE):
        return True

    return False
