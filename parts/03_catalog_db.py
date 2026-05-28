# =========================
# CATALOG DB: new product ladder
# 1 brand -> 2 category -> 3 series optional -> 4 model
# -> 5 sim optional -> 6 memory -> 7 color -> product card
# =========================

CATALOG_COLUMNS = {
    "brand": "brand_name",
    "category": "category_name",
    "series": "series_name",
    "model": "model_name",
    "sim": "sim_name",
    "memory": "memory_name",
    "color": "color_name",
}

OPTIONAL_COLUMNS = {"series_name", "sim_name"}


def clean_catalog_value(value, optional=False):
    value = " ".join(str(value or "").strip().split())
    if optional and value.lower() in ["-", "нет", "не указано", "none", "null"]:
        return ""
    return value


def normalize_catalog_key(value):
    return " ".join(str(value or "").strip().split()).lower()


def normalize_filters(filters):
    result = {}
    for key, value in (filters or {}).items():
        if key not in CATALOG_COLUMNS.values():
            continue
        optional = key in OPTIONAL_COLUMNS
        result[key] = clean_catalog_value(value, optional=optional)
    return result


def build_products_where(filters=None, active_only=True):
    clauses = []
    params = []

    if active_only:
        clauses.append("is_active = TRUE")

    for column, value in normalize_filters(filters).items():
        clauses.append(f"COALESCE({column}, '') = %s")
        params.append(value)

    where_sql = " AND ".join(clauses) if clauses else "TRUE"
    return where_sql, params


def get_catalog_options(filters, column, include_empty=False):
    filters = normalize_filters(filters)
    where_sql, params = build_products_where(filters)

    empty_filter = "" if include_empty else f" AND COALESCE({column}, '') <> ''"

    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT MIN(id) AS representative_id, COALESCE({column}, '') AS value, COUNT(*) AS total
                FROM products
                WHERE {where_sql}
                  {empty_filter}
                GROUP BY COALESCE({column}, '')
                ORDER BY
                    CASE WHEN COALESCE({column}, '') = '' THEN 1 ELSE 0 END,
                    COALESCE({column}, '');
            """, params)
            return cur.fetchall()


def get_catalog_products(filters=None, limit=None):
    where_sql, params = build_products_where(filters)
    limit_sql = ""
    if limit:
        limit_sql = " LIMIT %s"
        params.append(limit)

    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT
                    id,
                    name,
                    description,
                    photo_file_id,
                    price,
                    type_id,
                    COALESCE(sim_name, ''),
                    model_id,
                    COALESCE(model_name, ''),
                    category_id,
                    COALESCE(category_name, ''),
                    COALESCE(brand_name, ''),
                    COALESCE(series_name, ''),
                    COALESCE(memory_name, ''),
                    COALESCE(color_name, '')
                FROM products
                WHERE {where_sql}
                ORDER BY brand_name, category_name, series_name, model_name, sim_name, memory_name, color_name, name, id
                {limit_sql};
            """, params)
            return cur.fetchall()


def count_catalog_products(filters=None):
    where_sql, params = build_products_where(filters)
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM products WHERE {where_sql};", params)
            return cur.fetchone()[0]


# =========================
# Compatibility names used by old command/keyboards code
# =========================

def get_categories():
    return [(representative_id, value) for representative_id, value, total in get_catalog_options({}, "brand_name")]


def get_categories_for_catalog():
    return [(representative_id, value, None) for representative_id, value, total in get_catalog_options({}, "brand_name")]


def get_category(category_id):
    product = get_product(category_id)
    if product:
        return (product[0], product[11])
    return None


def add_category(name, emoji_id=None):
    # В новой структуре отдельные пустые категории не нужны.
    # Функция оставлена, чтобы старые callback-кнопки не падали.
    return None


def rename_category(category_id, new_name, emoji_id=None):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE products
                SET brand_name = %s, updated_at = NOW()
                WHERE id = %s;
            """, (clean_catalog_value(new_name), category_id))


def delete_category(category_id):
    delete_product(category_id)


def get_models_by_category(category_id):
    product = get_product(category_id)
    if not product:
        return []
    return [(representative_id, value, "", None) for representative_id, value, total in get_catalog_options({"brand_name": product[11]}, "category_name")]


def get_model(model_id):
    product = get_product(model_id)
    if not product:
        return None
    return (product[0], product[8], "", product[9], product[10])


def get_all_models():
    rows = []
    for representative_id, value, total in get_catalog_options({}, "model_name"):
        product = get_product(representative_id)
        rows.append((representative_id, value, "", product[10] if product else ""))
    return rows


def add_model(category_id, name, description, emoji_id=None):
    return None


def rename_model(model_id, new_name):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE products SET model_name = %s, updated_at = NOW() WHERE id = %s;", (clean_catalog_value(new_name), model_id))


def update_model_description(model_id, new_description):
    update_product_description(model_id, new_description)


def delete_model(model_id):
    delete_product(model_id)


def get_types_by_model(model_id):
    product = get_product(model_id)
    if not product:
        return []
    filters = {
        "brand_name": product[11],
        "category_name": product[10],
        "model_name": product[8],
    }
    if product[12]:
        filters["series_name"] = product[12]
    return [(representative_id, value, "", None) for representative_id, value, total in get_catalog_options(filters, "sim_name", include_empty=True)]


def get_type(type_id):
    product = get_product(type_id)
    if not product:
        return None
    return (type_id, product[6], "", product[7], product[8], product[9], product[10])


def get_all_types():
    rows = []
    for representative_id, value, total in get_catalog_options({}, "sim_name", include_empty=True):
        product = get_product(representative_id)
        rows.append((representative_id, value or "Без симки", "", product[8] if product else "", product[10] if product else ""))
    return rows


def add_type(model_id, name, description, emoji_id=None):
    return None


def rename_type(type_id, new_name):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE products SET sim_name = %s, updated_at = NOW() WHERE id = %s;", (clean_catalog_value(new_name, optional=True), type_id))


def update_type_description(type_id, new_description):
    update_product_description(type_id, new_description)


def delete_type(type_id):
    delete_product(type_id)


# =========================
# Product CRUD
# =========================

def get_products_by_type(type_id):
    product = get_product(type_id)
    if not product:
        return []

    filters = {
        "brand_name": product[11],
        "category_name": product[10],
        "model_name": product[8],
    }
    if product[12]:
        filters["series_name"] = product[12]
    if product[6]:
        filters["sim_name"] = product[6]

    return [
        (p[0], p[1], p[2], p[3], p[4], None)
        for p in get_catalog_products(filters)
    ]


def get_product(product_id):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    id,
                    name,
                    description,
                    photo_file_id,
                    price,
                    type_id,
                    COALESCE(sim_name, ''),
                    model_id,
                    COALESCE(model_name, ''),
                    category_id,
                    COALESCE(category_name, ''),
                    COALESCE(brand_name, ''),
                    COALESCE(series_name, ''),
                    COALESCE(memory_name, ''),
                    COALESCE(color_name, '')
                FROM products
                WHERE id = %s AND is_active = TRUE;
            """, (product_id,))
            return cur.fetchone()


def get_all_products():
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    id,
                    COALESCE(brand_name, ''),
                    COALESCE(category_name, ''),
                    TRIM(BOTH ' ' FROM CONCAT_WS(' ',
                        NULLIF(series_name, ''),
                        NULLIF(model_name, ''),
                        NULLIF(sim_name, ''),
                        NULLIF(memory_name, ''),
                        NULLIF(color_name, '')
                    )) AS path_name,
                    name,
                    price
                FROM products
                WHERE is_active = TRUE
                ORDER BY brand_name, category_name, series_name, model_name, sim_name, memory_name, color_name, name, id;
            """)
            return cur.fetchall()


def find_catalog_product_id(brand_name, category_name, series_name, model_name, sim_name, memory_name, color_name, product_name):
    values = [
        clean_catalog_value(brand_name),
        clean_catalog_value(category_name),
        clean_catalog_value(series_name, optional=True),
        clean_catalog_value(model_name),
        clean_catalog_value(sim_name, optional=True),
        clean_catalog_value(memory_name),
        clean_catalog_value(color_name),
        clean_catalog_value(product_name),
    ]

    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id
                FROM products
                WHERE is_active = TRUE
                  AND LOWER(COALESCE(brand_name, '')) = LOWER(%s)
                  AND LOWER(COALESCE(category_name, '')) = LOWER(%s)
                  AND LOWER(COALESCE(series_name, '')) = LOWER(%s)
                  AND LOWER(COALESCE(model_name, '')) = LOWER(%s)
                  AND LOWER(COALESCE(sim_name, '')) = LOWER(%s)
                  AND LOWER(COALESCE(memory_name, '')) = LOWER(%s)
                  AND LOWER(COALESCE(color_name, '')) = LOWER(%s)
                  AND LOWER(name) = LOWER(%s)
                ORDER BY id
                LIMIT 1;
            """, values)
            row = cur.fetchone()
            return row[0] if row else None


def add_catalog_product(
    brand_name,
    category_name,
    series_name,
    model_name,
    sim_name,
    memory_name,
    color_name,
    product_name,
    description,
    photo_file_id,
    price,
    emoji_id=None,
):
    brand_name = clean_catalog_value(brand_name)
    category_name = clean_catalog_value(category_name)
    series_name = clean_catalog_value(series_name, optional=True)
    model_name = clean_catalog_value(model_name)
    sim_name = clean_catalog_value(sim_name, optional=True)
    memory_name = clean_catalog_value(memory_name)
    color_name = clean_catalog_value(color_name)
    product_name = clean_catalog_value(product_name)
    description = description or ""
    price = clean_catalog_value(price)

    if not all([brand_name, category_name, model_name, memory_name, color_name, product_name, price]):
        return None

    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO products
                (brand_name, category_name, series_name, model_name, sim_name, memory_name, color_name,
                 name, description, photo_file_id, price, emoji_id, is_active, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, NOW())
                RETURNING id;
            """, (
                brand_name, category_name, series_name, model_name, sim_name, memory_name, color_name,
                product_name, description, photo_file_id, price, emoji_id,
            ))
            return cur.fetchone()[0]


def add_product(type_id, name, description, photo_file_id, price, emoji_id=None):
    # Совместимость со старым ручным добавлением.
    product_type = get_type(type_id)
    if not product_type:
        return None
    return add_catalog_product(
        brand_name=product_type[6],
        category_name=product_type[4],
        series_name="",
        model_name=product_type[1],
        sim_name="",
        memory_name="Не указано",
        color_name="Не указано",
        product_name=name,
        description=description,
        photo_file_id=photo_file_id,
        price=price,
        emoji_id=emoji_id,
    )


def rename_product(product_id, new_name):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE products
                SET name = %s,
                    updated_at = NOW()
                WHERE id = %s;
            """, (clean_catalog_value(new_name), product_id))


def update_product_description(product_id, description):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE products
                SET description = %s,
                    updated_at = NOW()
                WHERE id = %s;
            """, (description or "", product_id))


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
            """, (clean_catalog_value(new_price), product_id))

            cur.execute("""
                INSERT INTO price_history (product_id, old_price, new_price, changed_by)
                VALUES (%s, %s, %s, %s);
            """, (product_id, old_price, clean_catalog_value(new_price), changed_by))
            return old_price


def update_product_catalog_fields(product_id, fields):
    allowed = {
        "brand_name", "category_name", "series_name", "model_name",
        "sim_name", "memory_name", "color_name",
    }
    assignments = []
    params = []
    for key, value in (fields or {}).items():
        if key not in allowed:
            continue
        assignments.append(f"{key} = %s")
        params.append(clean_catalog_value(value, optional=key in OPTIONAL_COLUMNS))

    if not assignments:
        return

    params.append(product_id)
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                UPDATE products
                SET {', '.join(assignments)}, updated_at = NOW()
                WHERE id = %s;
            """, params)


def delete_product(product_id):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE products
                SET is_active = FALSE,
                    updated_at = NOW()
                WHERE id = %s;
            """, (product_id,))
