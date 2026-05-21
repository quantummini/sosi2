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


