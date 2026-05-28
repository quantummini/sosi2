# =========================
# CALLBACK HANDLER
# =========================


def build_selected_catalog_text(filters):
    filters = normalize_filters(filters or {})
    labels = [
        ("Бренд", "brand_name"),
        ("Категория", "category_name"),
        ("Серия", "series_name"),
        ("Модель", "model_name"),
        ("Симка", "sim_name"),
        ("Память", "memory_name"),
        ("Цвет", "color_name"),
    ]
    lines = []
    for title, key in labels:
        value = filters.get(key, "")
        if value:
            lines.append(f"{title}: {value}")
    return "\n".join(lines)


def options_keyboard(options, column, next_step, filters, empty_label=None):
    buttons = []
    for representative_id, value, total in options:
        label = value
        if value == "" and empty_label:
            label = empty_label
        elif value == "":
            continue

        next_filters = dict(normalize_filters(filters))
        next_filters[column] = value
        buttons.append(pbutton(label, make_catalog_callback(next_step, next_filters)))

    keyboard = make_two_columns(buttons)
    keyboard.append([default_button(" Вернуться в каталог", "catalog")])
    return InlineKeyboardMarkup(keyboard)


async def show_products_or_card(query, context, filters):
    products = get_catalog_products(filters)

    if not products:
        await safe_show_text(
            query,
            "По выбранным параметрам товаров пока нет.",
            catalog_back_keyboard(),
        )
        return

    if len(products) == 1:
        await show_product_card(query, products[0], context)
        return

    selected = build_selected_catalog_text(filters)
    text_msg = "Выберите товар:"
    if selected:
        text_msg = f"{selected}\n\nВыберите товар:"

    keyboard = []
    for product in products[:80]:
        keyboard.append([pbutton(product[1], f"product_{product[0]}")])

    if len(products) > 80:
        text_msg += f"\n\nПоказаны первые 80 товаров из {len(products)}."

    keyboard.append([default_button(" Вернуться в каталог", "catalog")])
    await safe_show_text(query, text_msg, InlineKeyboardMarkup(keyboard))


async def show_catalog_step(query, context, step, filters):
    filters = normalize_filters(filters or {})
    selected = build_selected_catalog_text(filters)

    if step == "category":
        options = get_catalog_options(filters, "category_name")
        if not options:
            await show_products_or_card(query, context, filters)
            return
        text_msg = f"{selected}\n\nВыберите категорию:" if selected else "Выберите категорию:"
        await safe_show_text(query, text_msg, options_keyboard(options, "category_name", "series_or_model", filters))
        return

    if step == "series_or_model":
        series_options = get_catalog_options(filters, "series_name", include_empty=True)
        has_non_empty = any(value for _, value, _ in series_options)

        if has_non_empty:
            text_msg = f"{selected}\n\nВыберите серию:" if selected else "Выберите серию:"
            await safe_show_text(
                query,
                text_msg,
                options_keyboard(series_options, "series_name", "model", filters, empty_label="Без серии"),
            )
            return

        options = get_catalog_options(filters, "model_name")
        if not options:
            await show_products_or_card(query, context, filters)
            return
        text_msg = f"{selected}\n\nВыберите модель:" if selected else "Выберите модель:"
        await safe_show_text(query, text_msg, options_keyboard(options, "model_name", "sim_or_memory", filters))
        return

    if step == "model":
        options = get_catalog_options(filters, "model_name")
        if not options:
            await show_products_or_card(query, context, filters)
            return
        text_msg = f"{selected}\n\nВыберите модель:" if selected else "Выберите модель:"
        await safe_show_text(query, text_msg, options_keyboard(options, "model_name", "sim_or_memory", filters))
        return

    if step == "sim_or_memory":
        sim_options = get_catalog_options(filters, "sim_name", include_empty=True)
        has_non_empty = any(value for _, value, _ in sim_options)

        if has_non_empty:
            text_msg = f"{selected}\n\nВыберите симку:" if selected else "Выберите симку:"
            await safe_show_text(
                query,
                text_msg,
                options_keyboard(sim_options, "sim_name", "memory", filters, empty_label="Без симки"),
            )
            return

        options = get_catalog_options(filters, "memory_name")
        if not options:
            await show_products_or_card(query, context, filters)
            return
        text_msg = f"{selected}\n\nВыберите память:" if selected else "Выберите память:"
        await safe_show_text(query, text_msg, options_keyboard(options, "memory_name", "color", filters))
        return

    if step == "memory":
        options = get_catalog_options(filters, "memory_name")
        if not options:
            await show_products_or_card(query, context, filters)
            return
        text_msg = f"{selected}\n\nВыберите память:" if selected else "Выберите память:"
        await safe_show_text(query, text_msg, options_keyboard(options, "memory_name", "color", filters))
        return

    if step == "color":
        options = get_catalog_options(filters, "color_name")
        if not options:
            await show_products_or_card(query, context, filters)
            return
        text_msg = f"{selected}\n\nВыберите цвет:" if selected else "Выберите цвет:"
        await safe_show_text(query, text_msg, options_keyboard(options, "color_name", "products", filters))
        return

    if step == "products":
        await show_products_or_card(query, context, filters)
        return

    await safe_show_text(query, "Каталог устарел. Откройте каталог заново.", catalog_back_keyboard())


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    # ===== CLIENT CATALOG =====

    if data == "catalog":
        brands = get_categories()
        if not brands:
            await safe_show_text(query, "Каталог\n\nКаталог пока пустой.")
            return
        await safe_show_text(query, CATALOG_TEXT, catalog_keyboard())
        return

    if data.startswith("nav_"):
        token = data.replace("nav_", "", 1)
        payload = get_catalog_callback(token)
        if not payload:
            await safe_show_text(query, "Кнопка каталога устарела. Откройте каталог заново.", catalog_back_keyboard())
            return
        await show_catalog_step(query, context, payload.get("step"), payload.get("filters") or {})
        return

    if data.startswith("product_"):
        product_id = int(data.replace("product_", "", 1))
        product = get_product(product_id)
        if not product:
            await safe_show_text(query, "Товар не найден.", catalog_keyboard())
            return
        await show_product_card(query, product, context)
        return

    if data.startswith("qty_minus_"):
        product_id = int(data.replace("qty_minus_", "", 1))
        current_qty = get_product_qty(context, product_id)
        set_product_qty(context, product_id, current_qty - 1)
        await update_product_card(query, context, product_id)
        return

    if data.startswith("qty_plus_"):
        product_id = int(data.replace("qty_plus_", "", 1))
        current_qty = get_product_qty(context, product_id)
        set_product_qty(context, product_id, current_qty + 1)
        await update_product_card(query, context, product_id)
        return

    if data.startswith("qty_show_"):
        product_id = int(data.replace("qty_show_", "", 1))
        qty = get_product_qty(context, product_id)
        await query.answer(f"Количество: {qty} шт.")
        return

    if data.startswith("addcart_"):
        product_id = int(data.replace("addcart_", "", 1))
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
                [primary_button(" Корзина", "cart")],
                [primary_button("Продолжить покупки", "catalog")],
            ]),
        )
        return

    if data.startswith("buy_"):
        product_id = int(data.replace("buy_", "", 1))
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
            reply_markup=order_menu,
        )
        return

    if data == "cart":
        lines, valid_product_ids = build_cart_lines(context)
        if not valid_product_ids:
            await safe_show_text(
                query,
                "Корзина\n\nКорзина пока пустая.",
                InlineKeyboardMarkup([[default_button(" Вернуться в каталог", "catalog")]]),
            )
            return

        text_msg = "Корзина\n\n" + "\n".join(lines) + f"\n\nПозиций в корзине: {len(valid_product_ids)}"
        await safe_show_text(query, text_msg, cart_markup(context))
        return

    if data == "cart_delete_menu":
        lines, valid_product_ids = build_cart_lines(context)
        if not valid_product_ids:
            await safe_show_text(
                query,
                "Корзина\n\nКорзина пока пустая.",
                InlineKeyboardMarkup([[default_button(" Вернуться в каталог", "catalog")]]),
            )
            return

        text_msg = "Удаление товара из корзины\n\nВыберите позицию, которую нужно убрать:\n\n" + "\n".join(lines)
        await safe_show_text(query, text_msg, cart_delete_markup(context))
        return

    if data.startswith("remove_cart_product_"):
        try:
            product_id = int(data.replace("remove_cart_product_", "", 1))
        except ValueError:
            await safe_show_text(query, "Ошибка удаления товара.")
            return

        removed = remove_cart_product(context, product_id)
        if not removed:
            await safe_show_text(query, "Товар уже удалён или не найден.", catalog_back_keyboard())
            return

        lines, valid_product_ids = build_cart_lines(context)
        if not valid_product_ids:
            await safe_show_text(query, "Корзина\n\nКорзина теперь пустая.", catalog_back_keyboard())
            return

        text_msg = "Корзина\n\n" + "\n".join(lines) + f"\n\nПозиций в корзине: {len(valid_product_ids)}"
        await safe_show_text(query, text_msg, cart_markup(context))
        return

    if data.startswith("remove_cart_"):
        try:
            item_index = int(data.replace("remove_cart_", "", 1))
        except ValueError:
            await safe_show_text(query, "Ошибка удаления позиции.")
            return

        removed = remove_cart_item_by_index(context, item_index)
        if not removed:
            await safe_show_text(query, "Позиция уже удалена или не найдена.", catalog_back_keyboard())
            return

        lines, valid_product_ids = build_cart_lines(context)
        if not valid_product_ids:
            await safe_show_text(query, "Корзина\n\nКорзина теперь пустая.", catalog_back_keyboard())
            return

        text_msg = "Корзина\n\n" + "\n".join(lines) + f"\n\nПозиций в корзине: {len(valid_product_ids)}"
        await safe_show_text(query, text_msg, cart_markup(context))
        return

    if data == "clear_cart":
        clear_cart(context)
        await safe_show_text(query, "Корзина очищена ✅", catalog_back_keyboard())
        return

    if data == "checkout":
        lines, valid_product_ids = build_cart_lines(context)
        if not valid_product_ids:
            await safe_show_text(query, "Корзина пустая. Сначала добавьте товар.", catalog_back_keyboard())
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
            reply_markup=order_menu,
        )
        return

    # ===== ADMIN ADD PRODUCT =====

    if data == "admin_add_product":
        if not is_admin_user(query.from_user.id) or not is_admin_logged(context):
            await safe_show_text(query, "Нет доступа.")
            return
        context.user_data["admin_state"] = "add_product_brand"
        await safe_show_text(
            query,
            "➕ Добавление товара\n\nВведите бренд.\n\nНапример: Apple",
            cancel_admin_keyboard(),
        )
        return

    # ===== ADMIN BULK =====

    if data == "admin_bulk_catalog":
        if not is_admin_user(query.from_user.id) or not is_admin_logged(context):
            await safe_show_text(query, "Нет доступа.")
            return
        context.user_data["admin_state"] = "bulk_catalog_add"
        await safe_show_text(query, BULK_CATALOG_HELP_TEXT, cancel_admin_keyboard())
        return

    if data == "admin_bulk_prices":
        if not is_admin_user(query.from_user.id) or not is_admin_logged(context):
            await safe_show_text(query, "Нет доступа.")
            return

        products = get_all_products()
        if not products:
            await safe_show_text(query, "Товаров пока нет.", admin_keyboard())
            return

        lines = []
        for product_id, brand_name, category_name, path_name, product_name, price in products[:80]:
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

        if len(products) > 80:
            text += f"\n\nПоказаны первые 80 товаров из {len(products)}. Остальные тоже можно обновлять по ID."

        context.user_data["admin_state"] = "bulk_prices"
        await safe_show_text(query, text, cancel_admin_keyboard())
        return

    # ===== ADMIN ADMINS =====

    if data == "admin_add_admin":
        if not is_main_admin(query.from_user.id) or not is_admin_logged(context):
            await safe_show_text(query, "Нет доступа. Добавлять админов может только основной админ.", admin_keyboard())
            return
        context.user_data["admin_state"] = "add_admin_id"
        await safe_show_text(
            query,
            " Добавление админа\n\nОтправьте Telegram ID сотрудника.\n\nНапример:\n707131428",
            cancel_admin_keyboard(),
        )
        return

    if data == "admin_list_admins":
        if not is_main_admin(query.from_user.id) or not is_admin_logged(context):
            await safe_show_text(query, "Нет доступа. Смотреть список админов может только основной админ.", admin_keyboard())
            return

        admins = get_admins_list()
        main_admin_id = get_admin_id()
        lines = [" Список админов\n", f"Основной админ: {main_admin_id}\n"]

        if not admins:
            lines.append("Дополнительных админов пока нет.")
        else:
            for index, admin in enumerate(admins, start=1):
                telegram_id, username, full_name, role, created_at = admin
                lines.append(
                    f"{index}. ID: {telegram_id}\n"
                    f" Username: {username or 'username не указан'}\n"
                    f" Имя: {full_name or 'имя не указано'}\n"
                    f" Роль: {role}\n"
                )

        await safe_show_text(query, "\n".join(lines), admin_keyboard())
        return

    if data == "admin_delete_admin":
        if not is_main_admin(query.from_user.id) or not is_admin_logged(context):
            await safe_show_text(query, "Нет доступа. Удалять админов может только основной админ.", admin_keyboard())
            return

        admins = get_admins_list()
        if not admins:
            await safe_show_text(query, "Дополнительных админов пока нет.", admin_keyboard())
            return

        lines = ["❌ Удаление админа\n", "Список админов:\n"]
        for index, admin in enumerate(admins, start=1):
            telegram_id, username, full_name, role, created_at = admin
            lines.append(
                f"{index}. ID: {telegram_id}\n"
                f" Username: {username or 'username не указан'}\n"
                f" Имя: {full_name or 'имя не указано'}\n"
            )
        lines.append("\nОтправьте Telegram ID админа, которого нужно удалить:")
        context.user_data["admin_state"] = "delete_admin_id"
        await safe_show_text(query, "\n".join(lines), cancel_admin_keyboard())
        return

    # ===== ADMIN PRODUCTS =====

    if data == "admin_products":
        products = get_all_products()
        if not products:
            await safe_show_text(query, "Редактор товаров\n\nТоваров пока нет.", admin_keyboard())
            return
        await safe_show_text(query, "Редактор товаров\n\nВыберите товар для редактирования:", admin_products_keyboard(page=0))
        return

    if data.startswith("admin_products_page_"):
        page = int(data.replace("admin_products_page_", "", 1))
        await safe_show_text(query, "Редактор товаров\n\nВыберите товар для редактирования:", admin_products_keyboard(page=page))
        return

    if data.startswith("admin_product_name_"):
        product_id = int(data.replace("admin_product_name_", "", 1))
        context.user_data["edit_product_id"] = product_id
        context.user_data["admin_state"] = "rename_product"
        await safe_show_text(query, "Введите новое полное название товара:", cancel_admin_keyboard())
        return

    if data.startswith("admin_product_desc_"):
        product_id = int(data.replace("admin_product_desc_", "", 1))
        context.user_data["edit_product_id"] = product_id
        context.user_data["admin_state"] = "edit_product_description"
        await safe_show_text(query, "Введите новое описание товара.\n\nЕсли описание нужно очистить, отправьте -", cancel_admin_keyboard())
        return

    if data.startswith("admin_product_photo_"):
        product_id = int(data.replace("admin_product_photo_", "", 1))
        context.user_data["edit_product_id"] = product_id
        context.user_data["admin_state"] = "edit_product_photo"
        await safe_show_text(query, "Отправьте новое фото товара.\n\nЕсли фото нужно удалить, отправьте -", cancel_admin_keyboard())
        return

    if data.startswith("admin_product_price_"):
        product_id = int(data.replace("admin_product_price_", "", 1))
        context.user_data["edit_product_id"] = product_id
        context.user_data["admin_state"] = "edit_product_price"
        await safe_show_text(query, "Введите новую цену товара:", cancel_admin_keyboard())
        return

    if data.startswith("admin_product_field_"):
        raw = data.replace("admin_product_field_", "", 1)
        product_id_text, field_name = raw.split("_", 1)
        product_id = int(product_id_text)
        field_map = {
            "brand": "brand_name",
            "category": "category_name",
            "series": "series_name",
            "model": "model_name",
            "sim": "sim_name",
            "memory": "memory_name",
            "color": "color_name",
        }
        if field_name not in field_map:
            await safe_show_text(query, "Ошибка поля.", admin_keyboard())
            return
        context.user_data["edit_product_id"] = product_id
        context.user_data["edit_catalog_field"] = field_map[field_name]
        context.user_data["admin_state"] = "edit_catalog_field"
        extra = "\n\nДля серии или симки можно отправить -, чтобы очистить поле." if field_name in ["series", "sim"] else ""
        await safe_show_text(query, f"Введите новое значение поля.{extra}", cancel_admin_keyboard())
        return

    if data.startswith("admin_product_delete_"):
        product_id = int(data.replace("admin_product_delete_", "", 1))
        delete_product(product_id)
        await safe_show_text(query, "Товар удалён ✅\n\nОн больше не отображается в каталоге.", admin_keyboard())
        return

    if data.startswith("admin_product_"):
        raw_product_id = data.replace("admin_product_", "", 1)
        if not raw_product_id.isdigit():
            await safe_show_text(query, "Ошибка: неверный ID товара.", admin_keyboard())
            return

        product_id = int(raw_product_id)
        product = get_product(product_id)
        if not product:
            await safe_show_text(query, "Товар не найден.", admin_keyboard())
            return

        text_msg = (
            f"Товар #{product[0]}\n\n"
            f"Бренд: {product[11]}\n"
            f"Категория: {product[10]}\n"
            f"Серия: {product[12] or 'не указана'}\n"
            f"Модель: {product[8]}\n"
            f"Симка: {product[6] or 'не указана'}\n"
            f"Память: {product[13]}\n"
            f"Цвет: {product[14]}\n"
            f"Название: {product[1]}\n"
            f"Цена: {product[4]}\n"
            f"Фото: {'есть' if product[3] else 'нет'}\n"
        )

        if product[2]:
            text_msg += f"\nОписание:\n{product[2]}"

        await safe_show_text(
            query,
            text_msg,
            InlineKeyboardMarkup([
                [button("Изменить бренд", f"admin_product_field_{product_id}_brand")],
                [button("Изменить категорию", f"admin_product_field_{product_id}_category")],
                [button("Изменить серию", f"admin_product_field_{product_id}_series")],
                [button("Изменить модель", f"admin_product_field_{product_id}_model")],
                [button("Изменить симку", f"admin_product_field_{product_id}_sim")],
                [button("Изменить память", f"admin_product_field_{product_id}_memory")],
                [button("Изменить цвет", f"admin_product_field_{product_id}_color")],
                [button("Переименовать товар", f"admin_product_name_{product_id}")],
                [button("Изменить описание", f"admin_product_desc_{product_id}")],
                [button("Изменить фото", f"admin_product_photo_{product_id}")],
                [button("Изменить цену", f"admin_product_price_{product_id}")],
                [button("Удалить товар", f"admin_product_delete_{product_id}")],
                [button("Назад к товарам", "admin_products")],
            ]),
        )
        return

    # ===== ADMIN NAV =====

    if data == "admin_cancel":
        if not is_admin_user(query.from_user.id) or not is_admin_logged(context):
            await safe_show_text(query, "Нет доступа.")
            return
        await delete_saved_prompt(context, query.message.chat_id, "admin_login_prompt_id")
        await delete_saved_prompt(context, query.message.chat_id, "admin_password_prompt_id")
        clear_admin_temp_data(context)
        await safe_show_text(query, ADMIN_PANEL_TEXT, admin_keyboard())
        return

    if data == "admin_menu":
        if not is_admin_user(query.from_user.id) or not is_admin_logged(context):
            await safe_show_text(query, "Нет доступа.")
            return
        await safe_show_text(query, ADMIN_PANEL_TEXT, admin_keyboard())
        return

    if data == "admin_logout":
        context.user_data["admin_logged"] = False
        clear_admin_temp_data(context)
        await safe_show_text(query, "Вы вышли из админ-панели.")
        return

    await safe_show_text(query, "Неизвестная кнопка. Откройте меню заново.", catalog_back_keyboard())
