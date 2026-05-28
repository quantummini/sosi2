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
            text_msg += "\nПока нет вариантов."

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

    elif data == "admin_bulk_catalog":
    if not is_admin_user(query.from_user.id) or not is_admin_logged(context):
        await safe_show_text(query, "Нет доступа.")
        return

    context.user_data["admin_state"] = "bulk_catalog_add"

    await safe_show_text(
        query,
        BULK_CATALOG_HELP_TEXT,
        cancel_admin_keyboard()

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


