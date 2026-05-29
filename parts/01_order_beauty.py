# =========================
# ORDER BEAUTY
# =========================

def generate_order_number():
    return random.randint(100000, 999999)


def build_pretty_order_text(order_number, order_name, order_phone, order_address, lines):
    # Сообщение отправляется с ParseMode.HTML, поэтому пользовательские данные
    # обязательно экранируем. Иначе имя/адрес с символами <, >, & ломали ответ.
    safe_order_number = html_escape(str(order_number or ""))
    safe_order_name = html_escape(str(order_name or ""))
    safe_order_phone = html_escape(str(order_phone or ""))
    safe_order_address = html_escape(str(order_address or ""))
    items_text = "\n".join(html_escape(str(line)) for line in lines)

    return (
        "━━━━━━━━━━━━━━━━━━\n"
        "✅ <b>ЗАКАЗ ОФОРМЛЕН</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"🧾 <b>Номер заказа:</b> <code>#{safe_order_number}</code>\n"
        f"👤 <b>ФИО:</b> {safe_order_name}\n"
        f"📞 <b>Телефон:</b> {safe_order_phone}\n"
        f"📍 <b>Адрес:</b> {safe_order_address}\n\n"
        f"📦 <b>Состав заказа:</b>\n{items_text}\n\n"
        "🙏 <b>Спасибо за покупку!</b>\n"
        "Менеджер скоро свяжется с вами для подтверждения заказа."
    )


def build_admin_order_text(order_number, order_name, order_phone, order_address, lines, username, user_id):
    items_text = "\n".join(lines)

    return (
        "🆕 Новый заказ!\n\n"
        f"Номер заказа: #{order_number}\n\n"
        f"Товары:\n{items_text}\n\n"
        f"Имя клиента: {order_name}\n"
        f"Телефон: {order_phone}\n"
        f"Адрес: {order_address}\n\n"
        f"Telegram: {username or 'username не указан'}\n"
        f"Telegram ID: {user_id}\n\n"
        f"Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )


