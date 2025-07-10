import os
import logging
import re
import trafilatura
import google.generativeai as genai
import requests
from flask import Flask, request

from telegram import Update
from telegram.ext import Application, ContextTypes

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Переменные окружения
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
BASE_URL = os.environ.get("BASE_URL")
WEBHOOK_PATH = f"/{TELEGRAM_TOKEN}"
WEBHOOK_URL = f"{BASE_URL}{WEBHOOK_PATH}"

# Инициализация Flask и Telegram Application
flask_app = Flask(__name__)

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-pro")

PROMPT = """..."""  # оставь без изменений


def process_url(url: str) -> str:
    try:
        headers = {"User-Agent": "Mozilla/5.0 ..."}
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        text = trafilatura.extract(
            response.text,
            include_comments=False,
            include_tables=False,
            no_fallback=True,
        )

        if not text or len(text) < 200:
            return "Не удалось извлечь текст..."
        text = text[:15000]
        full_prompt = PROMPT.format(text=text)
        response_gemini = model.generate_content(full_prompt)
        return response_gemini.text

    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка скачивания: {e}")
        return f"Ошибка загрузки страницы: {e}"
    except Exception as e:
        logger.error(f"Ошибка генерации текста: {e}")
        return "Ошибка при обработке ссылки."


# Создаём Application (бот)
application = Application.builder().token(TELEGRAM_TOKEN).build()


@application.message()
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    text = update.message.text
    chat_id = update.message.chat_id

    if text == "/start":
        await context.bot.send_message(
            chat_id=chat_id,
            text="Привет! 👋 Отправь мне ссылку на статью...",
        )
        return

    url_match = re.search(r"https?://\S+", text)
    if url_match:
        url = url_match.group(0)
        await context.bot.send_message(
            chat_id=chat_id, text="Обрабатываю ссылку... 🧙‍♂️"
        )
        summary = process_url(url)
        await context.bot.send_message(
            chat_id=chat_id, text=summary, disable_web_page_preview=True
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id, text="Отправь ссылку на статью."
        )


# Webhook endpoint для Telegram
@flask_app.route(WEBHOOK_PATH, methods=["POST"])
async def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    await application.process_update(update)
    return "ok"


# Эндпоинт для установки webhook
@flask_app.route("/set_webhook", methods=["GET"])
def set_webhook():
    success = application.bot.set_webhook(url=WEBHOOK_URL)
    return "webhook setup ok" if success else "webhook setup failed"
