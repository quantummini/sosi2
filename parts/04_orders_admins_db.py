# =========================
# ORDERS / ADMINS
# =========================

def save_order(user_id, username, full_name, phone, address, product_id, product_name, price, order_number=None):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO orders
                (user_id, username, full_name, phone, address, product_id, product_name, price, order_number)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
            """, (user_id, username, full_name, phone, address, product_id, product_name, price, str(order_number) if order_number else None))


def get_orders_relation_size_bytes():
    """Физический размер таблицы orders вместе с индексами."""
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_total_relation_size('orders'::regclass);")
            row = cur.fetchone()
            return int(row[0] or 0) if row else 0


def get_orders_live_rows_size_bytes():
    """Примерный размер живых строк заказов.

    После DELETE PostgreSQL не всегда сразу уменьшает файл таблицы на диске,
    но освобожденное место переиспользуется новыми заказами. Поэтому для
    решения "старые заменяются новыми" ориентируемся на живые строки.
    """
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COALESCE(SUM(pg_column_size(o)), 0) FROM orders o;")
            row = cur.fetchone()
            return int(row[0] or 0) if row else 0


def delete_oldest_order_groups(batch_size=300):
    """Удаляет самые старые заказы целиком.

    Если у заказа есть order_number, удаляются все товарные строки этого заказа.
    Старые записи без order_number удаляются как отдельные заказы.
    """
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                WITH oldest_groups AS (
                    SELECT
                        COALESCE(order_number, 'row:' || id::text) AS order_key,
                        MIN(created_at) AS first_created_at,
                        MIN(id) AS first_id
                    FROM orders
                    GROUP BY COALESCE(order_number, 'row:' || id::text)
                    ORDER BY first_created_at ASC, first_id ASC
                    LIMIT %s
                ), deleted_rows AS (
                    DELETE FROM orders o
                    USING oldest_groups g
                    WHERE COALESCE(o.order_number, 'row:' || o.id::text) = g.order_key
                    RETURNING o.id
                )
                SELECT COUNT(*) FROM deleted_rows;
            """, (batch_size,))
            row = cur.fetchone()
            return int(row[0] or 0) if row else 0


def vacuum_orders_after_cleanup():
    try:
        with db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("VACUUM ANALYZE orders;")
    except Exception:
        # VACUUM не критичен: PostgreSQL всё равно сможет переиспользовать
        # освобожденное место после обычного autovacuum.
        pass


def enforce_orders_storage_limit():
    """Оставляет новые заказы, а самые старые удаляет при превышении 3 ГБ.

    Лимит берется из ORDERS_STORAGE_LIMIT_GB, по умолчанию 3 ГБ.
    Чистка запускается после оформления нового заказа. Когда физический размер
    orders доходит до лимита, бот удаляет старые заказы до безопасного уровня
    живых данных. Новые заказы остаются.
    """
    limit_bytes = get_orders_storage_limit_bytes()
    target_bytes = get_orders_cleanup_target_bytes()

    try:
        physical_bytes = get_orders_relation_size_bytes()
    except Exception:
        return {"deleted_rows": 0, "physical_bytes": 0, "live_bytes": 0, "limit_bytes": limit_bytes}

    if physical_bytes < limit_bytes:
        return {
            "deleted_rows": 0,
            "physical_bytes": physical_bytes,
            "live_bytes": 0,
            "limit_bytes": limit_bytes,
        }

    try:
        live_bytes = get_orders_live_rows_size_bytes()
    except Exception:
        live_bytes = physical_bytes

    deleted_total = 0
    rounds = 0

    while live_bytes > target_bytes and rounds < 30:
        deleted = delete_oldest_order_groups(batch_size=300)
        deleted_total += deleted
        rounds += 1

        if deleted <= 0:
            break

        try:
            live_bytes = get_orders_live_rows_size_bytes()
        except Exception:
            break

    if deleted_total > 0:
        vacuum_orders_after_cleanup()

    return {
        "deleted_rows": deleted_total,
        "physical_bytes": physical_bytes,
        "live_bytes": live_bytes,
        "limit_bytes": limit_bytes,
    }


def get_recent_orders(days=3, limit=120):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    id,
                    order_number,
                    user_id,
                    username,
                    full_name,
                    phone,
                    address,
                    product_id,
                    product_name,
                    price,
                    created_at
                FROM orders
                WHERE created_at >= NOW() - (%s * INTERVAL '1 day')
                ORDER BY created_at DESC, id DESC
                LIMIT %s;
            """, (days, limit))
            return cur.fetchall()


def format_order_created_at(created_at):
    if not created_at:
        return "дата не указана"

    try:
        return created_at.strftime("%d.%m.%Y %H:%M")
    except Exception:
        return str(created_at)


def build_recent_orders_text(days=3, limit=120, max_chars=3600):
    rows = get_recent_orders(days=days, limit=limit)

    if not rows:
        return f"📋 Заказы за {days} дня\n\nЗаказов за последние {days} дня нет."

    groups = {}
    order_keys = []

    for row in rows:
        (
            order_row_id,
            order_number,
            user_id,
            username,
            full_name,
            phone,
            address,
            product_id,
            product_name,
            price,
            created_at,
        ) = row

        group_key = f"order_{order_number}" if order_number else f"row_{order_row_id}"

        if group_key not in groups:
            groups[group_key] = {
                "order_row_id": order_row_id,
                "order_number": order_number,
                "user_id": user_id,
                "username": username,
                "full_name": full_name,
                "phone": phone,
                "address": address,
                "created_at": created_at,
                "items": [],
            }
            order_keys.append(group_key)

        groups[group_key]["items"].append({
            "product_id": product_id,
            "product_name": product_name,
            "price": price,
        })

    lines = [
        f"📋 Заказы за {days} дня",
        f"Показано заказов: {len(order_keys)}",
        f"Показано товарных позиций: {len(rows)}",
        "",
    ]

    shown_groups = 0

    for index, group_key in enumerate(order_keys, start=1):
        group = groups[group_key]
        order_label = f"#{group['order_number']}" if group.get("order_number") else f"запись #{group['order_row_id']}"
        username = group.get("username") or "username не указан"
        full_name = group.get("full_name") or "имя не указано"
        phone = group.get("phone") or "телефон не указан"
        address = group.get("address") or "адрес не указан"
        user_id = group.get("user_id") or "ID не указан"
        date_text = format_order_created_at(group.get("created_at"))

        item_lines = []
        for item in group["items"]:
            item_product_id = item.get("product_id") or "?"
            item_product_name = item.get("product_name") or "товар не указан"
            item_price = item.get("price") or "цена не указана"
            item_lines.append(f"• #{item_product_id} — {item_product_name} — {item_price}")

        block = (
            f"{index}. 🧾 Заказ {order_label}\n"
            f"Дата: {date_text}\n"
            f"Клиент: {full_name}\n"
            f"Телефон: {phone}\n"
            f"Адрес: {address}\n"
            f"Telegram: {username}\n"
            f"Telegram ID: {user_id}\n"
            f"Товары:\n"
            + "\n".join(item_lines)
            + "\n"
        )

        current_text = "\n".join(lines)
        if len(current_text) + len(block) + 80 > max_chars:
            remaining = len(order_keys) - shown_groups
            lines.append(f"...и ещё заказов: {remaining}")
            lines.append("Откройте кнопку ещё раз позже или смотрите свежие заказы выше.")
            break

        lines.append(block)
        shown_groups += 1

    return "\n".join(lines).strip()


def is_admin_in_db(telegram_id):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM admins WHERE telegram_id = %s;", (telegram_id,))
            return cur.fetchone() is not None


def add_admin_to_db(telegram_id, username, full_name):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO admins (telegram_id, username, full_name)
                VALUES (%s, %s, %s)
                ON CONFLICT (telegram_id)
                DO UPDATE SET
                    username = EXCLUDED.username,
                    full_name = EXCLUDED.full_name;
            """, (telegram_id, username, full_name))


def get_admins_list():
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT telegram_id, username, full_name, role, created_at
                FROM admins
                ORDER BY created_at DESC;
            """)
            return cur.fetchall()


def delete_admin_from_db(telegram_id):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM admins
                WHERE telegram_id = %s;
            """, (telegram_id,))
            return cur.rowcount


def save_admin_login_attempt(telegram_id, username, full_name, login, success):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO admin_login_attempts
                (telegram_id, username, full_name, login, success)
                VALUES (%s, %s, %s, %s, %s);
            """, (telegram_id, username, full_name, login, success))


def is_admin_user(user_id):
    main_admin_id = get_admin_id()

    if main_admin_id and user_id == main_admin_id:
        return True

    return is_admin_in_db(user_id)


def is_admin_logged(context):
    return context.user_data.get("admin_logged") is True


def is_main_admin(user_id):
    main_admin_id = get_admin_id()
    return bool(main_admin_id and user_id == main_admin_id)


async def try_delete_message(context, chat_id, message_id):
    if not chat_id or not message_id:
        return

    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass


async def delete_saved_prompt(context, chat_id, key):
    message_id = context.user_data.pop(key, None)
    await try_delete_message(context, chat_id, message_id)


