# =========================
# TEXT HANDLER
# =========================


def normalize_bulk_name(value):
    return " ".join((value or "").strip().split()).lower()


def parse_bulk_catalog_line(line):
    parts = [part.strip() for part in line.split("|")]

    # Full format:
    # Brand | Category | Series | Model | Sim | Memory | Color | Product | Price | Description
    if len(parts) >= 9:
        return {
            "brand_name": parts[0],
            "category_name": parts[1],
            "series_name": clean_catalog_value(parts[2], optional=True),
            "model_name": parts[3],
            "sim_name": clean_catalog_value(parts[4], optional=True),
            "memory_name": parts[5],
            "color_name": parts[6],
            "product_name": parts[7],
            "price": parts[8],
            "description": " | ".join(parts[9:]).strip() if len(parts) >= 10 else "",
        }

    # Short format without series and sim:
    # Brand | Category | Model | Memory | Color | Product | Price | Description
    if len(parts) >= 7:
        return {
            "brand_name": parts[0],
            "category_name": parts[1],
            "series_name": "",
            "model_name": parts[2],
            "sim_name": "",
            "memory_name": parts[3],
            "color_name": parts[4],
            "product_name": parts[5],
            "price": parts[6],
            "description": " | ".join(parts[7:]).strip() if len(parts) >= 8 else "",
        }

    return None


def process_bulk_catalog_text(raw_text, changed_by=None):
    stats = {
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

        item = parse_bulk_catalog_line(line)
        if not item:
            stats["skipped"] += 1
            errors.append(
                f"Строка {line_number}: неверный формат. Нужен полный формат из 9 колонок или короткий из 7 колонок."
            )
            continue

        brand_name = clean_catalog_value(item["brand_name"])
        category_name = clean_catalog_value(item["category_name"])
        series_name = clean_catalog_value(item["series_name"], optional=True)
        model_name = clean_catalog_value(item["model_name"])
        sim_name = clean_catalog_value(item["sim_name"], optional=True)
        memory_name = clean_catalog_value(item["memory_name"])
        color_name = clean_catalog_value(item["color_name"])
        product_name = clean_catalog_value(item["product_name"])
        price = clean_catalog_value(item["price"])
        description = item["description"]

        if not all([brand_name, category_name, model_name, memory_name, color_name, product_name, price]):
            stats["skipped"] += 1
            errors.append(
                f"Строка {line_number}: пустое обязательное поле. Нужны бренд, категория, модель, память, цвет, товар и цена."
            )
            continue

        try:
            existing_product_id = find_catalog_product_id(
                brand_name,
                category_name,
                series_name,
                model_name,
                sim_name,
                memory_name,
                color_name,
                product_name,
            )

            if existing_product_id:
                update_product_price(existing_product_id, price, changed_by=changed_by)
                if description:
                    update_product_description(existing_product_id, description)
                stats["products_updated"] += 1
                continue

            product_id = add_catalog_product(
                brand_name=brand_name,
                category_name=category_name,
                series_name=series_name,
                model_name=model_name,
                sim_name=sim_name,
                memory_name=memory_name,
                color_name=color_name,
                product_name=product_name,
                description=description,
                photo_file_id=None,
                price=price,
                emoji_id=None,
            )

            if product_id:
                stats["products_created"] += 1
            else:
                stats["skipped"] += 1
                errors.append(f"Строка {line_number}: не удалось добавить товар")

        except Exception as e:
            stats["skipped"] += 1
            errors.append(f"Строка {line_number}: {e}")

    return stats, errors


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    text_clean = text.strip()

    user = update.effective_user
    user_id = user.id
    username = f"@{user.username}" if user.username else None
    full_name = user.full_name

    admin_state = context.user_data.get("admin_state")
    order_state = context.user_data.get("order_state")

    # ===== ORDER CANCEL / MENU =====

    if order_state and text_clean in ["❌ Отменить оформление", "/cancel", "отмена", "Отмена"]:
        await cancel_order_flow(update, context)
        return

    if order_state and text_clean.endswith("Каталог"):
        await cancel_order_flow(update, context, "Оформление заказа отменено. Открываю каталог.")
        await send_catalog(update, context)
        return

    if order_state and text_clean.endswith("Корзина"):
        await cancel_order_flow(update, context, "Оформление заказа отменено. Открываю корзину.")
        await send_cart_message(update, context)
        return

    # ===== ADMIN CANCEL =====

    if admin_state and text_clean.lower() in ["назад", "отмена", "/cancel"]:
        clear_admin_temp_data(context)
        await update.message.reply_text(
            ADMIN_PANEL_TEXT,
            reply_markup=admin_keyboard(),
        )
        return

    # ===== ADD PRODUCT PRICE AFTER PHOTO =====

    if admin_state == "add_product_price":
        if not is_admin_user(user_id) or not is_admin_logged(context):
            await update.message.reply_text("Нет доступа.")
            return

        price = text.strip()
        if not price:
            await update.message.reply_text(
                "Цена пустая. Введите цену товара, например: 100 000",
                reply_markup=cancel_admin_keyboard(),
            )
            return

        data = {
            "brand_name": context.user_data.get("new_product_brand_name"),
            "category_name": context.user_data.get("new_product_category_name"),
            "series_name": context.user_data.get("new_product_series_name", ""),
            "model_name": context.user_data.get("new_product_model_name"),
            "sim_name": context.user_data.get("new_product_sim_name", ""),
            "memory_name": context.user_data.get("new_product_memory_name"),
            "color_name": context.user_data.get("new_product_color_name"),
            "product_name": context.user_data.get("new_product_name"),
            "description": context.user_data.get("new_product_description", ""),
            "photo_file_id": context.user_data.get("new_product_photo_file_id"),
            "emoji_id": context.user_data.get("new_product_emoji_id"),
        }

        required = [
            data["brand_name"],
            data["category_name"],
            data["model_name"],
            data["memory_name"],
            data["color_name"],
            data["product_name"],
        ]
        if not all(required):
            clear_admin_temp_data(context)
            await update.message.reply_text(
                "Ошибка добавления товара. Не хватает обязательных полей. Попробуйте добавить товар заново.",
                reply_markup=admin_keyboard(),
            )
            return

        try:
            existing_product_id = find_catalog_product_id(
                data["brand_name"],
                data["category_name"],
                data["series_name"],
                data["model_name"],
                data["sim_name"],
                data["memory_name"],
                data["color_name"],
                data["product_name"],
            )

            if existing_product_id:
                old_price = update_product_price(existing_product_id, price, changed_by=user_id)
                update_product_description(existing_product_id, data["description"])
                if data["photo_file_id"]:
                    update_product_photo(existing_product_id, data["photo_file_id"])
                product_id = existing_product_id
                action_text = f"Товар уже был в каталоге, обновил его ✅\n\nБыло: {old_price}\nСтало: {price}"
            else:
                product_id = add_catalog_product(
                    brand_name=data["brand_name"],
                    category_name=data["category_name"],
                    series_name=data["series_name"],
                    model_name=data["model_name"],
                    sim_name=data["sim_name"],
                    memory_name=data["memory_name"],
                    color_name=data["color_name"],
                    product_name=data["product_name"],
                    description=data["description"],
                    photo_file_id=data["photo_file_id"],
                    price=price,
                    emoji_id=data["emoji_id"],
                )
                action_text = "Товар добавлен ✅"

        except Exception as e:
            clear_admin_temp_data(context)
            await update.message.reply_text(
                f"Ошибка сохранения товара:\n{e}",
                reply_markup=admin_keyboard(),
            )
            return

        clear_admin_temp_data(context)
        await update.message.reply_text(
            (
                f"{action_text}\n\n"
                f"ID: {product_id}\n"
                f"Бренд: {data['brand_name']}\n"
                f"Категория: {data['category_name']}\n"
                f"Серия: {data['series_name'] or 'не указана'}\n"
                f"Модель: {data['model_name']}\n"
                f"Симка: {data['sim_name'] or 'не указана'}\n"
                f"Память: {data['memory_name']}\n"
                f"Цвет: {data['color_name']}\n"
                f"Название: {data['product_name']}\n"
                f"Цена: {price}\n"
                f"Фото: {'есть' if data['photo_file_id'] else 'нет'}"
            ),
            reply_markup=admin_keyboard(),
        )
        return

    # ===== ORDER FLOW =====

    if order_state == "wait_order_name":
        context.user_data["order_name"] = text
        context.user_data["order_state"] = "wait_order_phone"
        await update.message.reply_text("Введите номер телефона:", reply_markup=order_menu)
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
                reply_markup=order_menu,
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
            reply_markup=order_menu,
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
                reply_markup=order_menu,
            )
            return

        checkout_items = get_checkout_items(context)
        lines, valid_product_ids = build_cart_lines(context, checkout_items)

        if not valid_product_ids:
            clear_order_data(context)
            await update.message.reply_text(
                "Нет товаров для оформления. Заказ отменён.",
                reply_markup=reply_menu,
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
                    price=product[4],
                )

            order_text = build_admin_order_text(
                order_number=order_number,
                order_name=order_name,
                order_phone=order_phone,
                order_address=order_address,
                lines=lines,
                username=username,
                user_id=user.id,
            )

            await context.bot.send_message(chat_id=admin_id, text=order_text)

        except Exception as e:
            await update.message.reply_text(
                f"Ошибка оформления заказа:\n{e}",
                reply_markup=reply_menu,
            )
            return

        pretty_text = build_pretty_order_text(
            order_number=order_number,
            order_name=order_name,
            order_phone=order_phone,
            order_address=order_address,
            lines=lines,
        )

        if ORDER_SUCCESS_STICKER:
            try:
                await context.bot.send_sticker(
                    chat_id=update.effective_chat.id,
                    sticker=ORDER_SUCCESS_STICKER,
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
            reply_markup=reply_menu,
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
                text="Теперь введите пароль:",
            )
            context.user_data["admin_password_prompt_id"] = message.message_id
        else:
            context.user_data["admin_state"] = None
            save_admin_login_attempt(user_id, username, full_name, text, False)
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Неверный логин.")
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
                    ),
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
                reply_markup=admin_keyboard(),
            )
        else:
            context.user_data["admin_logged"] = False
            context.user_data["admin_state"] = None
            save_admin_login_attempt(user_id, username, full_name, login, False)
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Неверный пароль.")
        return

    # ===== ADD ADMIN =====

    if admin_state == "add_admin_id":
        if not is_main_admin(user_id) or not is_admin_logged(context):
            await update.message.reply_text("Нет доступа.")
            return

        try:
            new_admin_id = int(text.strip())
        except ValueError:
            await update.message.reply_text(
                "Telegram ID должен быть числом.\n\nНапример: 707131428",
                reply_markup=cancel_admin_keyboard(),
            )
            return

        add_admin_to_db(telegram_id=new_admin_id, username=None, full_name="Добавлен владельцем")
        clear_admin_temp_data(context)
        await update.message.reply_text(
            (
                "Админ добавлен ✅\n\n"
                f"Telegram ID: {new_admin_id}\n\n"
                "Теперь этот сотрудник сможет войти через /admin по логину и паролю."
            ),
            reply_markup=admin_keyboard(),
        )
        return

    if admin_state == "delete_admin_id":
        if not is_main_admin(user_id) or not is_admin_logged(context):
            await update.message.reply_text("Нет доступа.")
            return

        try:
            admin_id_to_delete = int(text.strip())
        except ValueError:
            await update.message.reply_text(
                "Telegram ID должен быть числом.\n\nНапример: 707131428",
                reply_markup=cancel_admin_keyboard(),
            )
            return

        if admin_id_to_delete == get_admin_id():
            clear_admin_temp_data(context)
            await update.message.reply_text("Основного админа удалить нельзя.", reply_markup=admin_keyboard())
            return

        deleted_count = delete_admin_from_db(admin_id_to_delete)
        clear_admin_temp_data(context)

        if deleted_count:
            await update.message.reply_text(
                f"Админ удалён ✅\n\nTelegram ID: {admin_id_to_delete}",
                reply_markup=admin_keyboard(),
            )
        else:
            await update.message.reply_text(
                f"Админ не найден.\n\nTelegram ID: {admin_id_to_delete}",
                reply_markup=admin_keyboard(),
            )
        return

    # ===== MANUAL ADD PRODUCT =====

    if admin_state == "add_product_brand":
        if not is_admin_user(user_id) or not is_admin_logged(context):
            await update.message.reply_text("Нет доступа.")
            return
        value, emoji_id = extract_text_and_custom_emoji(update.message)
        if not value:
            await update.message.reply_text("Бренд пустой. Введите бренд, например: Apple", reply_markup=cancel_admin_keyboard())
            return
        context.user_data["new_product_brand_name"] = value
        context.user_data["admin_state"] = "add_product_category"
        await update.message.reply_text("Введите категорию.\n\nНапример: Смартфоны", reply_markup=cancel_admin_keyboard())
        return

    if admin_state == "add_product_category":
        if not is_admin_user(user_id) or not is_admin_logged(context):
            await update.message.reply_text("Нет доступа.")
            return
        value, emoji_id = extract_text_and_custom_emoji(update.message)
        if not value:
            await update.message.reply_text("Категория пустая. Введите категорию.", reply_markup=cancel_admin_keyboard())
            return
        context.user_data["new_product_category_name"] = value
        context.user_data["admin_state"] = "add_product_series"
        await update.message.reply_text(
            "Введите серию.\n\nНапример: 15 серия\nЕсли серии нет, отправьте -",
            reply_markup=cancel_admin_keyboard(),
        )
        return

    if admin_state == "add_product_series":
        if not is_admin_user(user_id) or not is_admin_logged(context):
            await update.message.reply_text("Нет доступа.")
            return
        value, emoji_id = extract_text_and_custom_emoji(update.message)
        context.user_data["new_product_series_name"] = clean_catalog_value(value, optional=True)
        context.user_data["admin_state"] = "add_product_model"
        await update.message.reply_text("Введите модель.\n\nНапример: iPhone 15 Pro", reply_markup=cancel_admin_keyboard())
        return

    if admin_state == "add_product_model":
        if not is_admin_user(user_id) or not is_admin_logged(context):
            await update.message.reply_text("Нет доступа.")
            return
        value, emoji_id = extract_text_and_custom_emoji(update.message)
        if not value:
            await update.message.reply_text("Модель пустая. Введите модель.", reply_markup=cancel_admin_keyboard())
            return
        context.user_data["new_product_model_name"] = value
        context.user_data["admin_state"] = "add_product_sim"
        await update.message.reply_text(
            "Введите симку.\n\nНапример: eSIM, 2 SIM\nЕсли симку указывать не нужно, отправьте -",
            reply_markup=cancel_admin_keyboard(),
        )
        return

    if admin_state == "add_product_sim":
        if not is_admin_user(user_id) or not is_admin_logged(context):
            await update.message.reply_text("Нет доступа.")
            return
        value, emoji_id = extract_text_and_custom_emoji(update.message)
        context.user_data["new_product_sim_name"] = clean_catalog_value(value, optional=True)
        context.user_data["admin_state"] = "add_product_memory"
        await update.message.reply_text("Введите память.\n\nНапример: 256GB", reply_markup=cancel_admin_keyboard())
        return

    if admin_state == "add_product_memory":
        if not is_admin_user(user_id) or not is_admin_logged(context):
            await update.message.reply_text("Нет доступа.")
            return
        value, emoji_id = extract_text_and_custom_emoji(update.message)
        if not value:
            await update.message.reply_text("Память пустая. Введите память.", reply_markup=cancel_admin_keyboard())
            return
        context.user_data["new_product_memory_name"] = value
        context.user_data["admin_state"] = "add_product_color"
        await update.message.reply_text("Введите цвет.\n\nНапример: Blue", reply_markup=cancel_admin_keyboard())
        return

    if admin_state == "add_product_color":
        if not is_admin_user(user_id) or not is_admin_logged(context):
            await update.message.reply_text("Нет доступа.")
            return
        value, emoji_id = extract_text_and_custom_emoji(update.message)
        if not value:
            await update.message.reply_text("Цвет пустой. Введите цвет.", reply_markup=cancel_admin_keyboard())
            return
        context.user_data["new_product_color_name"] = value
        context.user_data["admin_state"] = "add_product_name"
        await update.message.reply_text(
            (
                "Введите полное название товара.\n\n"
                "Например:\n"
                "iPhone 15 Pro 256GB eSIM Blue\n\n"
                "Можно отправить premium emoji + текст."
            ),
            reply_markup=cancel_admin_keyboard(),
        )
        return

    if admin_state == "add_product_name":
        if not is_admin_user(user_id) or not is_admin_logged(context):
            await update.message.reply_text("Нет доступа.")
            return
        product_name, emoji_id = extract_text_and_custom_emoji(update.message)
        if not product_name:
            await update.message.reply_text("Название товара пустое.", reply_markup=cancel_admin_keyboard())
            return
        context.user_data["new_product_name"] = product_name
        context.user_data["new_product_emoji_id"] = emoji_id
        context.user_data["admin_state"] = "add_product_description"
        await update.message.reply_text(
            "Введите описание товара.\n\nЕсли описание не нужно, напишите -",
            reply_markup=cancel_admin_keyboard(),
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
            "Отправьте фото товара.\n\nЕсли фото не нужно, напишите -",
            reply_markup=cancel_admin_keyboard(),
        )
        return

    if admin_state == "add_product_photo":
        if not is_admin_user(user_id) or not is_admin_logged(context):
            await update.message.reply_text("Нет доступа.")
            return
        if text == "-":
            context.user_data["new_product_photo_file_id"] = None
            context.user_data["admin_state"] = "add_product_price"
            await update.message.reply_text("Введите цену товара:", reply_markup=cancel_admin_keyboard())
            return
        await update.message.reply_text("Нужно отправить фото или написать -", reply_markup=cancel_admin_keyboard())
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
        await update.message.reply_text(f"Название товара обновлено ✅\n\nНовое название: {text}", reply_markup=admin_keyboard())
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
        await update.message.reply_text("Описание товара обновлено ✅", reply_markup=admin_keyboard())
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
            await update.message.reply_text("Фото товара удалено ✅", reply_markup=admin_keyboard())
            return
        await update.message.reply_text("Отправьте новое фото или напишите - чтобы удалить фото.", reply_markup=cancel_admin_keyboard())
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
            f"Цена товара обновлена ✅\n\nБыло: {old_price}\nСтало: {text}",
            reply_markup=admin_keyboard(),
        )
        return

    if admin_state == "edit_catalog_field":
        if not is_admin_user(user_id) or not is_admin_logged(context):
            await update.message.reply_text("Нет доступа.")
            return
        product_id = context.user_data.get("edit_product_id")
        field_name = context.user_data.get("edit_catalog_field")
        if not product_id or not field_name:
            clear_admin_temp_data(context)
            await update.message.reply_text("Ошибка. Товар не найден.", reply_markup=admin_keyboard())
            return
        update_product_catalog_fields(product_id, {field_name: text})
        clear_admin_temp_data(context)
        await update.message.reply_text("Поле товара обновлено ✅", reply_markup=admin_keyboard())
        return

    # ===== BULK CATALOG ADD =====

    if admin_state == "bulk_catalog_add":
        if not is_admin_user(user_id) or not is_admin_logged(context):
            await update.message.reply_text("Нет доступа.")
            return
        stats, errors = process_bulk_catalog_text(text, changed_by=user_id)
        clear_admin_temp_data(context)

        result = (
            "📦 Массовое добавление каталога завершено ✅\n\n"
            f"Создано товаров: {stats['products_created']}\n"
            f"Обновлено товаров: {stats['products_updated']}\n"
            f"Пропущено строк: {stats['skipped']}"
        )

        if errors:
            result += "\n\nОшибки:\n" + "\n".join(errors[:30])
            if len(errors) > 30:
                result += f"\n\nИ ещё ошибок: {len(errors) - 30}"

        await update.message.reply_text(result, reply_markup=admin_keyboard())
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

        await update.message.reply_text(result, reply_markup=admin_keyboard())
        return

    # ===== NORMAL TEXT =====

    if text_clean.endswith("Каталог"):
        await send_catalog(update, context)
        return

    if text_clean.endswith("Корзина"):
        await send_cart_message(update, context)
        return

    if text_clean.endswith("О нас"):
        await update.message.reply_text(wide_text(ABOUT_TEXT), reply_markup=reply_menu)
        return

    await update.message.reply_text(
        "Нажмите кнопку Каталог, Корзина или О нас внизу.",
        reply_markup=reply_menu,
    )


async def send_cart_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines, valid_product_ids = build_cart_lines(context)

    if not valid_product_ids:
        await update.message.reply_text(
            wide_text("Корзина\n\nКорзина пока пустая."),
            reply_markup=reply_menu,
        )
        return

    text_msg = (
        "Корзина\n\n"
        + "\n".join(lines)
        + f"\n\nПозиций в корзине: {len(valid_product_ids)}"
    )

    await update.message.reply_text(text_msg, reply_markup=cart_markup(context))
