from dotenv import load_dotenv
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

dotenv_path = os.path.join(BASE_DIR, '.env')
load_dotenv(dotenv_path=dotenv_path)

APP_ID = os.getenv("APP_ID")
APP_HASH = os.getenv("APP_HASH")


if not APP_ID:
    raise ValueError("Не задан ID магазина. Укажите APP_ID в .env файле")

if not APP_HASH:
    raise ValueError("Не задан секретный ключ. Укажите APP_HASH в .env файле")

