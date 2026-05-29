# =========================
# KEYBOARDS
# =========================

reply_menu = ReplyKeyboardMarkup(
    keyboard=[
        [" Каталог"],
        [" Корзина"],
        ["ℹ️ О нас"],
    ],
    resize_keyboard=True,
)

order_menu = ReplyKeyboardMarkup(
    keyboard=[
        ["❌ Отменить оформление"],
        [" Каталог", " Корзина"],
    ],
    resize_keyboard=True,
)

# Callback cache for catalog navigation. It keeps callback_data short and safe.
CATALOG_CALLBACK_CACHE = {}
ADMIN_CATALOG_VALUE_CACHE = {}


def make_catalog_callback(step, filters=None):
    payload = {
        "step": step,
        "filters": normalize_filters(filters or {}),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    token = hashlib.md5(raw.encode("utf-8")).hexdigest()[:18]
    CATALOG_CALLBACK_CACHE[token] = payload
    return f"nav_{token}"


def get_catalog_callback(token):
    return CATALOG_CALLBACK_CACHE.get(token)


def make_admin_catalog_value_callback(action, field, value):
    payload = {
        "action": action,
        "field": field,
        "value": clean_catalog_value(value, optional=field in OPTIONAL_COLUMNS),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    token = hashlib.md5(raw.encode("utf-8")).hexdigest()[:18]
    ADMIN_CATALOG_VALUE_CACHE[token] = payload
    return f"admv_{token}"


def get_admin_catalog_value_callback(token):
    return ADMIN_CATALOG_VALUE_CACHE.get(token)


def button(text, callback_data, style=None):
    # Telegram Bot API не поддерживает поле style у inline-кнопок.
    # Если отправлять его через api_kwargs, часть клиентов/версий API возвращает
    # ошибку при создании клавиатуры. Параметр style оставлен для совместимости
    # с остальным кодом, но в Telegram не передаётся.
    return InlineKeyboardButton(
        text=text,
        callback_data=callback_data,
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
    # icon_custom_emoji_id тоже не является стандартным полем inline-кнопки.
    # Не отправляем его в API, чтобы кнопки каталога не падали с BadRequest.
    return InlineKeyboardButton(
        text=text,
        callback_data=callback_data,
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
    options = get_catalog_options({}, "brand_name")
    buttons = []

    for representative_id, brand_name, total in options:
        buttons.append(
            pbutton(
                text=brand_name,
                callback_data=make_catalog_callback("category", {"brand_name": brand_name}),
            )
        )

    return InlineKeyboardMarkup(make_two_columns(buttons))


def admin_keyboard():
    return InlineKeyboardMarkup([
        [button("➕ Добавить товар", "admin_add_product")],
        [button("📦 Массовое добавление каталога", "admin_bulk_catalog")],
        [button("⚡ Массовое обновление цен", "admin_bulk_prices")],
        [button("📋 История заказов", "admin_recent_orders")],
        [button("🧩 Редактор брендов", "admin_edit_level_brand")],
        [button("📂 Редактор категорий", "admin_edit_level_category")],
        [button("🧬 Редактор серий", "admin_edit_level_series")],
        [button("📱 Редактор моделей", "admin_edit_level_model")],
        [button("📶 Редактор симок", "admin_edit_level_sim")],
        [button("💾 Редактор памяти", "admin_edit_level_memory")],
        [button("🎨 Редактор цветов", "admin_edit_level_color")],
        [button("📦 Редактор товаров", "admin_products")],
        [button(" Добавить админа", "admin_add_admin")],
        [button(" Список админов", "admin_list_admins")],
        [button("❌ Удалить админа", "admin_delete_admin")],
        [button(" Выйти из админ-панели", "admin_logout")],
    ])


def cancel_admin_keyboard():
    return InlineKeyboardMarkup([
        [button("⬅️ Назад в админ-панель", "admin_cancel")],
    ])


def catalog_back_keyboard():
    return InlineKeyboardMarkup([
        [default_button(" Вернуться в каталог", "catalog")],
    ])


def admin_products_keyboard(page=0):
    products = get_all_products()
    page_items, total = paginate_items(products, page)

    keyboard = []
    for product_id, brand_name, category_name, path_name, product_name, price in page_items:
        short_path = " → ".join(part for part in [brand_name, category_name, path_name] if part)
        if len(short_path) > 45:
            short_path = short_path[:42] + "..."
        keyboard.append([
            button(
                f"#{product_id} — {product_name} — {price}",
                f"admin_product_{product_id}",
            ),
        ])

    keyboard += pagination_buttons("admin_products_page", page, total)
    keyboard.append([button("Назад в админ-панель", "admin_menu")])
    return InlineKeyboardMarkup(keyboard)


def admin_catalog_level_keyboard(field, page=0):
    values = get_catalog_field_values(field)
    page_items, total = paginate_items(values, page)

    keyboard = []
    for representative_id, value, count in page_items:
        keyboard.append([
            button(
                f"{value} ({count})",
                make_admin_catalog_value_callback("open", field, value),
            )
        ])

    keyboard += pagination_buttons(f"admin_level_page_{field}", page, total)
    keyboard.append([button("Назад в админ-панель", "admin_menu")])
    return InlineKeyboardMarkup(keyboard)
