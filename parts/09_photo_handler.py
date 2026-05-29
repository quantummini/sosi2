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


