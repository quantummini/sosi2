# =========================
# STATE HELPERS
# =========================

def clear_admin_temp_data(context):
    keys_to_clear = [
        "new_product_brand_name",
        "new_product_category_name",
        "new_product_series_name",
        "new_product_model_name",
        "new_product_sim_name",
        "new_product_memory_name",
        "new_product_color_name",
        "new_product_name",
        "new_product_emoji_id",
        "new_product_description",
        "new_product_photo_file_id",
        "edit_product_id",
        "edit_catalog_field",
        "edit_level_field",
        "edit_level_value",
        "admin_login_input",
        "new_admin_id_input",
        "delete_admin_id_input",
    ]

    for key in keys_to_clear:
        context.user_data.pop(key, None)

    context.user_data["admin_state"] = None


def clear_order_data(context):
    keys = [
        "order_product_id",
        "order_name",
        "order_phone",
        "order_address",
        "checkout_items",
        "checkout_source",
    ]

    for key in keys:
        context.user_data.pop(key, None)

    context.user_data["order_state"] = None


async def cancel_order_flow(update: Update, context: ContextTypes.DEFAULT_TYPE, message="Оформление заказа отменено."):
    clear_order_data(context)
    await update.message.reply_text(
        message,
        reply_markup=reply_menu,
    )


def parse_price_to_int(price):
    digits = re.sub(r"\D", "", str(price or ""))
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def format_money(value):
    if value is None:
        return "не указано"
    return f"{value:,}".replace(",", " ")


def get_product_qty(context, product_id):
    return max(1, int(context.user_data.get(f"qty_{product_id}", 1)))


def set_product_qty(context, product_id, qty):
    qty = max(1, min(99, int(qty)))
    context.user_data[f"qty_{product_id}"] = qty
    return qty


def get_cart(context):
    return context.user_data.setdefault("cart", [])


def add_product_to_cart(context, product_id, qty=1):
    cart = get_cart(context)
    for _ in range(max(1, int(qty))):
        cart.append(product_id)
    context.user_data["cart"] = cart


def clear_cart(context):
    context.user_data["cart"] = []


def remove_cart_product(context, product_id):
    cart = get_cart(context)
    new_cart = [item_id for item_id in cart if item_id != product_id]
    if len(new_cart) == len(cart):
        return False
    context.user_data["cart"] = new_cart
    return True


def remove_cart_item_by_index(context, index):
    cart = get_cart(context)
    if index < 0 or index >= len(cart):
        return False
    cart.pop(index)
    context.user_data["cart"] = cart
    return True


def set_checkout_items(context, product_ids):
    context.user_data["checkout_items"] = list(product_ids)


def get_checkout_items(context):
    return context.user_data.get("checkout_items") or []


def clear_checkout_items(context):
    context.user_data.pop("checkout_items", None)


def build_product_path(product):
    if not product:
        return ""
    parts = [
        product[11],  # brand
        product[10],  # category
        product[12],  # series optional
        product[8],   # model
        product[6],   # sim optional
        product[13],  # memory
        product[14],  # color
    ]
    return " → ".join(part for part in parts if part)


def build_cart_lines(context, product_ids=None):
    if product_ids is None:
        product_ids = get_cart(context)

    counter = Counter(product_ids)
    lines = []
    valid_product_ids = []
    total_sum = 0
    has_total = False
    index = 1

    for product_id, qty in counter.items():
        product = get_product(product_id)
        if not product:
            continue

        real_product_id = product[0]
        product_name = product[1]
        price = product[4]

        valid_product_ids.extend([real_product_id] * qty)

        price_value = parse_price_to_int(price)
        if price_value is not None:
            item_total = price_value * qty
            total_sum += item_total
            has_total = True
            lines.append(
                f"{index}. #{real_product_id} — {product_name}\n"
                f"   Количество: {qty} шт.\n"
                f"   Цена за шт: {price}\n"
                f"   Общая цена: {format_money(item_total)}"
            )
        else:
            lines.append(
                f"{index}. #{real_product_id} — {product_name}\n"
                f"   Количество: {qty} шт.\n"
                f"   Цена за шт: {price}\n"
                f"   Общая цена: не посчитана"
            )

        index += 1

    if has_total:
        lines.append(f"\nИтого: {format_money(total_sum)}")

    return lines, valid_product_ids


def cart_markup(context):
    return InlineKeyboardMarkup([
        [success_button("✅ Оформить заказ", "checkout")],
        [danger_button("❌ Удалить товар", "cart_delete_menu")],
        [danger_button("🗑 Очистить корзину", "clear_cart")],
        [default_button(" Вернуться в каталог", "catalog")],
    ])


def cart_delete_markup(context):
    cart = get_cart(context)
    counter = Counter(cart)
    keyboard = []

    for product_id, qty in counter.items():
        product = get_product(product_id)
        if not product:
            continue
        keyboard.append([
            danger_button(
                f"Удалить #{product[0]} — {product[1]} ({qty} шт.)",
                f"remove_cart_product_{product_id}",
            )
        ])

    keyboard.append([danger_button("↩️ Назад в корзину", "cart")])
    keyboard.append([default_button(" Вернуться в каталог", "catalog")])
    return InlineKeyboardMarkup(keyboard)


async def safe_show_text(query, text, reply_markup=None):
    text = wide_text(text)

    try:
        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
        )
    except Exception:
        try:
            await query.message.delete()
        except Exception:
            pass

        await query.message.chat.send_message(
            text=text,
            reply_markup=reply_markup,
        )


def build_product_card_caption(product, qty):
    product_id = product[0]
    product_name = product[1]
    description = product[2]
    price = product[4]

    price_value = parse_price_to_int(price)
    total_price = price_value * qty if price_value is not None else None

    caption = (
        f"{product_name}\n\n"
        f"ID товара: #{product_id}\n"
        f"Количество: {qty} шт.\n"
        f"Цена за шт: {price}\n"
    )

    if total_price is not None:
        caption += f"Общая цена: {format_money(total_price)}\n"
    else:
        caption += "Общая цена: не посчитана\n"

    path = build_product_path(product)
    if path:
        caption += f"\nВыбрано:\n{path}\n"

    if description:
        caption += f"\nОписание:\n{description}\n"

    return caption


def product_card_keyboard(product_id, qty):
    return InlineKeyboardMarkup([
        [
            default_button("−", f"qty_minus_{product_id}"),
            default_button(str(qty), f"qty_show_{product_id}"),
            default_button("+", f"qty_plus_{product_id}"),
        ],
        [success_button("✅ Оформить заказ", f"buy_{product_id}")],
        [primary_button(" Корзина", f"addcart_{product_id}")],
        [default_button(" Вернуться в каталог", "catalog")],
    ])


async def update_product_card(query, context, product_id):
    product = get_product(product_id)
    if not product:
        await safe_show_text(query, "Товар не найден.")
        return

    qty = get_product_qty(context, product_id)
    caption = build_product_card_caption(product, qty)
    keyboard = product_card_keyboard(product_id, qty)

    if product[3]:
        try:
            await query.edit_message_caption(
                caption=caption,
                reply_markup=keyboard,
            )
            return
        except Exception:
            pass

    try:
        await query.edit_message_text(
            text=caption,
            reply_markup=keyboard,
        )
    except Exception:
        await safe_show_text(query, caption, keyboard)


async def show_product_card(query, product, context=None):
    product_id = product[0]
    photo_file_id = product[3]

    if context:
        qty = set_product_qty(context, product_id, get_product_qty(context, product_id))
    else:
        qty = 1

    caption = build_product_card_caption(product, qty)
    keyboard = product_card_keyboard(product_id, qty)

    if photo_file_id:
        try:
            await query.message.delete()
        except Exception:
            pass

        await query.message.chat.send_photo(
            photo=photo_file_id,
            caption=caption,
            reply_markup=keyboard,
        )
    else:
        await safe_show_text(query, caption, keyboard)
