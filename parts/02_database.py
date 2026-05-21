# =========================
# DATABASE
# =========================

def db_connect():
    database_url = get_database_url()
    if not database_url:
        raise RuntimeError("DATABASE_URL не найден. Добавь DATABASE_URL в Railway Variables.")
    return psycopg.connect(database_url, autocommit=True)


def init_db():
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS categories (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    emoji_id TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)
            cur.execute("ALTER TABLE categories ADD COLUMN IF NOT EXISTS emoji_id TEXT;")
            cur.execute("ALTER TABLE categories ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS models (
                    id SERIAL PRIMARY KEY,
                    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    emoji_id TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)
            cur.execute("ALTER TABLE models ADD COLUMN IF NOT EXISTS description TEXT DEFAULT '';")
            cur.execute("ALTER TABLE models ADD COLUMN IF NOT EXISTS emoji_id TEXT;")
            cur.execute("ALTER TABLE models ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS product_types (
                    id SERIAL PRIMARY KEY,
                    model_id INTEGER NOT NULL REFERENCES models(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    emoji_id TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)
            cur.execute("ALTER TABLE product_types ADD COLUMN IF NOT EXISTS description TEXT DEFAULT '';")
            cur.execute("ALTER TABLE product_types ADD COLUMN IF NOT EXISTS emoji_id TEXT;")
            cur.execute("ALTER TABLE product_types ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    id SERIAL PRIMARY KEY,
                    model_id INTEGER REFERENCES models(id) ON DELETE CASCADE,
                    type_id INTEGER REFERENCES product_types(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    photo_file_id TEXT,
                    price TEXT NOT NULL DEFAULT '',
                    emoji_id TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                );
            """)
            cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS category_id INTEGER REFERENCES categories(id) ON DELETE CASCADE;")
            cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS model_id INTEGER REFERENCES models(id) ON DELETE CASCADE;")
            cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS type_id INTEGER REFERENCES product_types(id) ON DELETE CASCADE;")
            cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS description TEXT DEFAULT '';")
            cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS photo_file_id TEXT;")
            cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS price TEXT NOT NULL DEFAULT '';")
            cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS emoji_id TEXT;")
            cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;")
            cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW();")

            # Безопасная миграция для старой базы Railway:
            # раньше products.category_id/model_id могли быть NOT NULL.
            # В новой структуре товар связан через type_id -> model_id -> category_id,
            # поэтому эти старые NOT NULL ограничения нужно снять.
            cur.execute("ALTER TABLE products ALTER COLUMN category_id DROP NOT NULL;")
            cur.execute("ALTER TABLE products ALTER COLUMN model_id DROP NOT NULL;")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    username TEXT,
                    full_name TEXT,
                    phone TEXT,
                    address TEXT,
                    product_id INTEGER,
                    product_name TEXT,
                    price TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)
            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS phone TEXT;")
            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS address TEXT;")
            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS product_id INTEGER;")
            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS product_name TEXT;")
            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS price TEXT;")
            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS items TEXT;")
            cur.execute("ALTER TABLE orders ALTER COLUMN items DROP NOT NULL;")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS price_history (
                    id SERIAL PRIMARY KEY,
                    product_id INTEGER,
                    old_price TEXT,
                    new_price TEXT,
                    changed_by BIGINT,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS admins (
                    id SERIAL PRIMARY KEY,
                    telegram_id BIGINT UNIQUE NOT NULL,
                    username TEXT,
                    full_name TEXT,
                    role TEXT DEFAULT 'admin',
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS admin_login_attempts (
                    id SERIAL PRIMARY KEY,
                    telegram_id BIGINT,
                    username TEXT,
                    full_name TEXT,
                    login TEXT,
                    success BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)


