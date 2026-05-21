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
        'Добро пожаловать!'
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


