# Bot — split project

Это безопасно разделённая версия бота.

## Файлы

- `bot.py` — точка входа Railway.
- `parts/00_config_env.py` — импорты, переменные Railway, тексты.
- `parts/01_order_beauty.py` — красивое оформление заказа.
- `parts/02_database.py` — `init_db()`.
- `parts/03_catalog_db.py` — категории, модели, виды товара, товары.
- `parts/04_orders_admins_db.py` — заказы, админы.
- `parts/05_keyboards.py` — клавиатуры и кнопки.
- `parts/06_state_helpers.py` — корзина, состояния, карточка товара.
- `parts/07_jobs_commands.py` — команды `/start`, `/admin`, `/price`.
- `parts/08_text_handler.py` — обработка текста.
- `parts/09_photo_handler.py` — обработка фото.
- `parts/10_callback_handler.py` — обработка inline-кнопок.
- `parts/11_main.py` — запуск приложения.

## Почему так

Это первый безопасный этап разделения. Логика исполняется в одном общем namespace через `exec`,
чтобы не сломать рабочий бот и не переписывать импорты на 4000 строк сразу.

После проверки на Railway можно будет сделать второй этап:
нормальные модули через `import`, без `exec`.

## Railway

Start command должен остаться:

```bash
python bot.py
```

## Deploy

```bash
git add .
git commit -m "Split bot into files"
git push
```
