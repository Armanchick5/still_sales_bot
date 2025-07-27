import os
from dotenv import load_dotenv, find_dotenv

# Загружаем .env
load_dotenv(find_dotenv())

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Яндекс CRM
YANDEX_API_URL = os.getenv("YANDEX_API_URL")
YANDEX_API_LOGIN = os.getenv("YANDEX_API_LOGIN")
YANDEX_API_PASSWORD = os.getenv("YANDEX_API_PASSWORD")

# GoStandUp
GOSTANDUP_API_URL = os.getenv("GOSTANDUP_API_URL")
GOSTANDUP_BEARER_TOKEN = os.getenv("GOSTANDUP_BEARER_TOKEN")

# Timepad
TIMEPAD_API_URL = os.getenv("TIMEPAD_API_URL")
TIMEPAD_BEARER_TOKEN = os.getenv("TIMEPAD_BEARER_TOKEN")
TIMEPAD_ORG_ID = os.getenv("TIMEPAD_ORG_ID")

# Проверка обязательных переменных
missing = []
for var in [
    ("BOT_TOKEN", os.getenv("BOT_TOKEN")),
    ("DATABASE_URL", os.getenv("DATABASE_URL")),
    ("YANDEX_API_URL", YANDEX_API_URL),
    ("YANDEX_API_LOGIN", YANDEX_API_LOGIN),
    ("YANDEX_API_PASSWORD", YANDEX_API_PASSWORD),
    ("GOSTANDUP_API_URL", GOSTANDUP_API_URL),
    ("GOSTANDUP_BEARER_TOKEN", GOSTANDUP_BEARER_TOKEN),
    ("TIMEPAD_API_URL", TIMEPAD_API_URL),
    ("TIMEPAD_BEARER_TOKEN", TIMEPAD_BEARER_TOKEN),
    ("TIMEPAD_ORG_ID", TIMEPAD_ORG_ID),
]:
    if not var[1]:
        missing.append(var[0])

if missing:
    raise RuntimeError(f"Не заданы в .env: {', '.join(missing)}")
