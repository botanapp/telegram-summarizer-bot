import os
import logging
import re
import trafilatura
import google.generativeai as genai
import requests

from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import (
    Application,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    filters,
)
import asyncio

# --- ЛОГИРОВАНИЕ ---
import sys

logging.basicConfig(
    stream=sys.stdout,
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# --- ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
BASE_URL = os.environ.get("BASE_URL").rstrip("/")  # https://your-vercel-app.vercel.app
WEBHOOK_PATH = f"/{TELEGRAM_TOKEN}"
WEBHOOK_URL = f"{BASE_URL}{WEBHOOK_PATH}"

# --- Проверки ---
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN не задан")

# --- Flask-приложение ---
flask_app = Flask(__name__)
app = flask_app  # для Vercel

# --- Настройка Gemini ---
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-pro")

PROMPT = """..."""  # как у тебя


# --- Обработка статьи ---
def process_url(url: str) -> str:
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        text = trafilatura.extract(
            response.text,
            include_comments=False,
            include_tables=False,
            no_fallback=True,
        )

        if not text or len(text) < 200:
            return "Не удалось извлечь текст страницы."
        text = text[:15000]
        result = model.generate_content(PROMPT.format(text=text))
        return result.text
    except Exception as e:
        logger.error(f"Ошибка при обработке URL: {e}")
        return "Ошибка при обработке ссылки."


# --- Telegram Application ---
application = Application.builder().token(TELEGRAM_TOKEN).build()


# --- Обработчик /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"/start от chat_id={update.effective_chat.id}")
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Привет! 👋 Отправь мне ссылку на статью — я сделаю пост для Telegram.",
    )


# --- Обработчик всех текстов ---
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(
        f"Текстовое сообщение от chat_id={update.effective_chat.id}: {update.message.text}"
    )
    text = update.message.text
    match = re.search(r"https?://\S+", text)
    if match:
        url = match.group(0)
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text="Обрабатываю ссылку..."
        )
        result = process_url(url)
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text=result, disable_web_page_preview=True
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text="Пожалуйста, пришли ссылку."
        )


# --- Регистрируем хендлеры ---
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

# --- /set_webhook (синхронно!) ---
from asyncio import run


@flask_app.route("/set_webhook", methods=["GET"])
def set_webhook():
    try:
        run(application.bot.set_webhook(url=WEBHOOK_URL))
        return "webhook setup ok"
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return "webhook setup failed"


# --- Webhook обработчик (/TOKEN) ---
@flask_app.route(WEBHOOK_PATH, methods=["POST"])
def telegram_webhook():
    try:
        logger.info("Webhook вызван — получили POST от Telegram.")
        data = request.get_json(force=True)
        logger.info(f"Raw update: {data}")
        update = Update.de_json(data, application.bot)
        logger.info(
            f"Update успешно десериализован. От chat_id={update.effective_chat.id if update.effective_chat else 'unknown'}"
        )
        asyncio.get_event_loop().create_task(application.process_update(update))
        return jsonify({"ok": True})
    except Exception as e:
        logger.error(f"Ошибка в webhook-хендлере: {e}")
        return jsonify({"ok": False})
