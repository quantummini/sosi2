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
