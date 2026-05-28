# =========================
# TEXT HANDLER
# =========================

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    def normalize_bulk_name(value):
    return " ".join((value or "").strip().split()).lower()


def find_category_id_by_name(name):
    name_key = normalize_bulk_name(name)

    for category_id, category_name in get_categories():
        if normalize_bulk_name(category_name) == name_key:
            return category_id

    return None


def find_model_id_by_name(category_id, name):
    name_key = normalize_bulk_name(name)

    for model_id, model_name, description, emoji_id in get_models_by_category(category_id):
        if normalize_bulk_name(model_name) == name_key:
            return model_id

    return None


def find_type_id_by_name(model_id, name):
    name_key = normalize_bulk_name(name)

    for type_id, type_name, description, emoji_id in get_types_by_model(model_id):
        if normalize_bulk_name(type_name) == name_key:
            return type_id

    return None


def find_product_id_by_name(type_id, name):
    name_key = normalize_bulk_name(name)

    for product_id, product_name, description, photo_file_id, price, emoji_id in get_products_by_type(type_id):
        if normalize_bulk_name(product_name) == name_key:
            return product_id

    return None


def ensure_bulk_category(name, stats):
    category_id = find_category_id_by_name(name)

    if category_id:
        return category_id

    category_id = add_category(name)
    stats["categories_created"] += 1
    return category_id


def ensure_bulk_model(category_id, name, stats):
    model_id = find_model_id_by_name(category_id, name)

    if model_id:
        return model_id

    model_id = add_model(
        category_id=category_id,
        name=name,
        description="",
        emoji_id=None
    )
    stats["models_created"] += 1
    return model_id


def ensure_bulk_type(model_id, name, stats):
    type_id = find_type_id_by_name(model_id, name)

    if type_id:
        return type_id

    type_id = add_type(
        model_id=model_id,
        name=name,
        description="",
        emoji_id=None
    )
    stats["types_created"] += 1
    return type_id


def process_bulk_catalog_text(raw_text, changed_by=None):
    stats = {
        "categories_created": 0,
        "models_created": 0,
        "types_created": 0,
        "products_created": 0,
        "products_updated": 0,
        "skipped": 0,
    }

    errors = []

    for line_number, raw_line in enumerate(raw_text.splitlines(), start=1):
        line = raw_line.strip()

        if not line:
            continue

        if line.startswith("#"):
            continue

        parts = [part.strip() for part in line.split("|")]

        while parts and not parts[-1]:
            parts.pop()

        if not parts:
            continue

        try:
            # Формат: Категория
            if len(parts) == 1:
                category_name = parts[0]

                if not category_name:
                    stats["skipped"] += 1
                    continue

                ensure_bulk_category(category_name, stats)
                continue

            # Формат: Категория | Модель
            if len(parts) == 2:
                category_name, model_name = parts

                if not category_name or not model_name:
                    errors.append(f"Строка {line_number}: нужны категория и модель")
                    continue

                category_id = ensure_bulk_category(category_name, stats)
                ensure_bulk_model(category_id, model_name, stats)
                continue

            # Формат: Категория | Модель | Вид товара
            if len(parts) == 3:
                category_name, model_name, type_name = parts

                if not category_name or not model_name or not type_name:
                    errors.append(f"Строка {line_number}: нужны категория, модель и вид товара")
                    continue

                category_id = ensure_bulk_category(category_name, stats)
                model_id = ensure_bulk_model(category_id, model_name, stats)
                ensure_bulk_type(model_id, type_name, stats)
                continue

            # Для товара нужна минимум 5 колонок:
            # Категория | Модель | Вид товара | Товар | Цена
            if len(parts) == 4:
                errors.append(
                    f"Строка {line_number}: для товара нужна цена. "
                    "Формат: Категория | Модель | Вид товара | Товар | Цена"
                )
                continue

            category_name = parts[0]
            model_name = parts[1]
            type_name = parts[2]
            product_name = parts[3]
            price = parts[4]
            description = parts[5] if len(parts) >= 6 else ""

            if not category_name or not model_name or not type_name or not product_name or not price:
                errors.append(
                    f"Строка {line_number}: пустое обязательное поле. "
                    "Нужны категория, модель, вид товара, товар и цена"
                )
                continue

            category_id = ensure_bulk_category(category_name, stats)
            model_id = ensure_bulk_model(category_id, model_name, stats)
            type_id = ensure_bulk_type(model_id, type_name, stats)

            existing_product_id = find_product_id_by_name(type_id, product_name)

            if existing_product_id:
                update_product_price(existing_product_id, price, changed_by=changed_by)

                if description:
                    update_product_description(existing_product_id, description)

                stats["products_updated"] += 1
                continue

            product_id = add_product(
                type_id=type_id,
                name=product_name,
                description=description,
                photo_file_id=None,
                price=price,
                emoji_id=None
            )

            if product_id:
                stats["products_created"] += 1
            else:
                errors.append(f"Строка {line_number}: не удалось добавить товар")

        except Exception as e:
            errors.append(f"Строка {line_number}: {e}")

    return stats, errors

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

    # ===== BULK CATALOG ADD =====

if admin_state == "bulk_catalog_add":
    if not is_admin_user(user_id) or not is_admin_logged(context):
        await update.message.reply_text("Нет доступа.")
        return

    stats, errors = process_bulk_catalog_text(text, changed_by=user_id)

    clear_admin_temp_data(context)

    result = (
        "📦 Массовое добавление каталога завершено ✅\n\n"
        f"Создано категорий: {stats['categories_created']}\n"
        f"Создано моделей: {stats['models_created']}\n"
        f"Создано видов товара: {stats['types_created']}\n"
        f"Создано товаров: {stats['products_created']}\n"
        f"Обновлено товаров: {stats['products_updated']}\n"
        f"Пропущено строк: {stats['skipped']}"
    )

    if errors:
        result += "\n\nОшибки:\n" + "\n".join(errors[:30])

        if len(errors) > 30:
            result += f"\n\nИ ещё ошибок: {len(errors) - 30}"

    await update.message.reply_text(
        result,
        reply_markup=admin_keyboard()
    )
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

    if text_clean.endswith("ℹ О нас"):
    await update.message.reply_text(
        wide_text(ABOUT_TEXT),
        reply_markup=reply_menu
    )
    return

await update.message.reply_text(
    "Нажмите кнопку 📦 Каталог, 🛒 Корзина или ℹ О нас внизу.",
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


