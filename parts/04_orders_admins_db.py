# =========================
# ORDERS / ADMINS
# =========================

def save_order(user_id, username, full_name, phone, address, product_id, product_name, price):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO orders
                (user_id, username, full_name, phone, address, product_id, product_name, price)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
            """, (user_id, username, full_name, phone, address, product_id, product_name, price))


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


