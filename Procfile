# Telegram Bot
# Разделённая версия проекта.
#
# Важно:
# Логика специально исполняется через parts/*.py в одном общем namespace,
# чтобы сохранить поведение рабочего большого bot.py без рискованного рефакторинга.
# Следующий шаг можно делать уже более чистым: переносить функции в нормальные import-модули.

from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
PARTS_DIR = BASE_DIR / "parts"

PART_FILES = [
    "00_config_env.py",
    "01_order_beauty.py",
    "02_database.py",
    "03_catalog_db.py",
    "04_orders_admins_db.py",
    "05_keyboards.py",
    "06_state_helpers.py",
    "07_jobs_commands.py",
    "08_text_handler.py",
    "09_photo_handler.py",
    "10_callback_handler.py",
    "11_main.py",
]


for part_file in PART_FILES:
    part_path = PARTS_DIR / part_file
    code = part_path.read_text(encoding="utf-8")
    exec(compile(code, str(part_path), "exec"), globals())


if __name__ == "__main__":
    main()
