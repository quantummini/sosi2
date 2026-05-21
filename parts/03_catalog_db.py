# =========================
# CATEGORY DB
# =========================

def get_categories():
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name
                FROM categories
                WHERE is_active = TRUE
                ORDER BY id;
            """)
            return cur.fetchall()


def get_categories_for_catalog():
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name, emoji_id
                FROM categories
                WHERE is_active = TRUE
                ORDER BY id;
            """)
            return cur.fetchall()


def get_category(category_id):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name
                FROM categories
                WHERE id = %s AND is_active = TRUE;
            """, (category_id,))
            return cur.fetchone()


def add_category(name, emoji_id=None):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO categories (name, emoji_id, is_active)
                VALUES (%s, %s, TRUE)
                ON CONFLICT (name)
                DO UPDATE SET
                    is_active = TRUE,
                    emoji_id = EXCLUDED.emoji_id
                RETURNING id;
            """, (name, emoji_id))
            return cur.fetchone()[0]


def rename_category(category_id, new_name, emoji_id=None):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE categories
                SET name = %s,
                    emoji_id = %s
                WHERE id = %s;
            """, (new_name, emoji_id, category_id))


def delete_category(category_id):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE categories
                SET is_active = FALSE
                WHERE id = %s;
            """, (category_id,))


# =========================
# MODEL DB
# =========================

def get_models_by_category(category_id):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name, description, emoji_id
                FROM models
                WHERE category_id = %s AND is_active = TRUE
                ORDER BY id;
            """, (category_id,))
            return cur.fetchall()


def get_model(model_id):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT m.id, m.name, m.description, c.id, c.name
                FROM models m
                JOIN categories c ON c.id = m.category_id
                WHERE m.id = %s
                  AND m.is_active = TRUE
                  AND c.is_active = TRUE;
            """, (model_id,))
            return cur.fetchone()


def get_all_models():
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT m.id, m.name, m.description, c.name
                FROM models m
                JOIN categories c ON c.id = m.category_id
                WHERE m.is_active = TRUE
                  AND c.is_active = TRUE
                ORDER BY c.id, m.id;
            """)
            return cur.fetchall()


def add_model(category_id, name, description, emoji_id=None):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO models (category_id, name, description, emoji_id)
                VALUES (%s, %s, %s, %s)
                RETURNING id;
            """, (category_id, name, description, emoji_id))
            return cur.fetchone()[0]


def rename_model(model_id, new_name):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE models SET name = %s WHERE id = %s;", (new_name, model_id))


def update_model_description(model_id, new_description):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE models SET description = %s WHERE id = %s;", (new_description, model_id))


def delete_model(model_id):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE models SET is_active = FALSE WHERE id = %s;", (model_id,))


# =========================
# PRODUCT TYPE DB
# =========================

def get_types_by_model(model_id):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name, description, emoji_id
                FROM product_types
                WHERE model_id = %s AND is_active = TRUE
                ORDER BY id;
            """, (model_id,))
            return cur.fetchall()


def get_type(type_id):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    t.id,
                    t.name,
                    t.description,
                    m.id,
                    m.name,
                    c.id,
                    c.name
                FROM product_types t
                JOIN models m ON m.id = t.model_id
                JOIN categories c ON c.id = m.category_id
                WHERE t.id = %s
                  AND t.is_active = TRUE
                  AND m.is_active = TRUE
                  AND c.is_active = TRUE;
            """, (type_id,))
            return cur.fetchone()


def get_all_types():
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    t.id,
                    t.name,
                    t.description,
                    m.name,
                    c.name
                FROM product_types t
                JOIN models m ON m.id = t.model_id
                JOIN categories c ON c.id = m.category_id
                WHERE t.is_active = TRUE
                  AND m.is_active = TRUE
                  AND c.is_active = TRUE
                ORDER BY c.id, m.id, t.id;
            """)
            return cur.fetchall()


def add_type(model_id, name, description, emoji_id=None):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO product_types (model_id, name, description, emoji_id)
                VALUES (%s, %s, %s, %s)
                RETURNING id;
            """, (model_id, name, description, emoji_id))
            return cur.fetchone()[0]


def rename_type(type_id, new_name):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE product_types SET name = %s WHERE id = %s;", (new_name, type_id))


def update_type_description(type_id, new_description):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE product_types SET description = %s WHERE id = %s;", (new_description, type_id))


def delete_type(type_id):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE product_types SET is_active = FALSE WHERE id = %s;", (type_id,))


# =========================
# PRODUCT DB
# =========================

def get_products_by_type(type_id):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name, description, photo_file_id, price, emoji_id
                FROM products
                WHERE type_id = %s AND is_active = TRUE
                ORDER BY id;
            """, (type_id,))
            return cur.fetchall()


def get_product(product_id):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    p.id,
                    p.name,
                    p.description,
                    p.photo_file_id,
                    p.price,
                    t.id,
                    t.name,
                    m.id,
                    m.name,
                    c.id,
                    c.name
                FROM products p
                JOIN product_types t ON t.id = p.type_id
                JOIN models m ON m.id = t.model_id
                JOIN categories c ON c.id = m.category_id
                WHERE p.id = %s
                  AND p.is_active = TRUE
                  AND t.is_active = TRUE
                  AND m.is_active = TRUE
                  AND c.is_active = TRUE;
            """, (product_id,))
            return cur.fetchone()


def get_all_products():
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    p.id,
                    c.name,
                    m.name,
                    t.name,
                    p.name,
                    p.price
                FROM products p
                JOIN product_types t ON t.id = p.type_id
                JOIN models m ON m.id = t.model_id
                JOIN categories c ON c.id = m.category_id
                WHERE p.is_active = TRUE
                  AND t.is_active = TRUE
                  AND m.is_active = TRUE
                  AND c.is_active = TRUE
                ORDER BY c.id, m.id, t.id, p.id;
            """)
            return cur.fetchall()


def add_product(type_id, name, description, photo_file_id, price, emoji_id=None):
    product_type = get_type(type_id)

    if not product_type:
        return None

    # get_type возвращает:
    # 0 type_id, 1 type_name, 2 type_description,
    # 3 model_id, 4 model_name, 5 category_id, 6 category_name
    model_id = product_type[3]
    category_id = product_type[5]

    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO products
                (category_id, model_id, type_id, name, description, photo_file_id, price, emoji_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
            """, (category_id, model_id, type_id, name, description, photo_file_id, price, emoji_id))
            return cur.fetchone()[0]


def rename_product(product_id, new_name):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE products
                SET name = %s,
                    updated_at = NOW()
                WHERE id = %s;
            """, (new_name, product_id))


def update_product_description(product_id, description):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE products
                SET description = %s,
                    updated_at = NOW()
                WHERE id = %s;
            """, (description, product_id))


def update_product_photo(product_id, photo_file_id):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE products
                SET photo_file_id = %s,
                    updated_at = NOW()
                WHERE id = %s;
            """, (photo_file_id, product_id))


def update_product_price(product_id, new_price, changed_by=None):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT price FROM products WHERE id = %s;", (product_id,))
            row = cur.fetchone()

            if not row:
                return None

            old_price = row[0]

            cur.execute("""
                UPDATE products
                SET price = %s,
                    updated_at = NOW()
                WHERE id = %s;
            """, (new_price, product_id))

            cur.execute("""
                INSERT INTO price_history (product_id, old_price, new_price, changed_by)
                VALUES (%s, %s, %s, %s);
            """, (product_id, old_price, new_price, changed_by))

            return old_price


def delete_product(product_id):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE products
                SET is_active = FALSE,
                    updated_at = NOW()
                WHERE id = %s;
            """, (product_id,))


