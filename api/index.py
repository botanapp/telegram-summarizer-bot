import os
import logging
import re
import requests
import trafilatura
import google.generativeai as genai

from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import (
    Application,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)

import asyncio

# --- Настройка логов ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Переменные окружения ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
BASE_URL = os.environ.get("BASE_URL", "").rstrip("/")  # без завершающего /

WEBHOOK_PATH = f"/{TELEGRAM_TOKEN}"
WEBHOOK_URL = f"{BASE_URL}{WEBHOOK_PATH}"

# --- Настройка Flask ---
flask_app = Flask(__name__)
app = flask_app  # для Vercel

# --- Настройка Gemini ---
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-pro")


PROMPT = """
Ты — ассистент, который помогает вести Telegram-канал.
Твоя задача — на основе текста веб-страницы сделать краткую и емкую заметку на русском языке.

Инструкции:
1.  Внимательно изучи предоставленный текст.
2.  Определи главную идею, ключевые тезисы и выводы.
3.  Напиши саммари (краткую выжимку) на русском языке. Объем — 3-5 абзацев.
4.  Стиль должен быть информативным, но легким для чтения, как для поста в Telegram.
5.  Придумай яркий и цепляющий заголовок для поста.
6.  Подбери 3-5 релевантных хештега.
7.  В конце добавь эмодзи, соответствующий теме.

Структура ответа:
[Заголовок]

[Текст саммари]

[Хештеги]
[Эмодзи]

Вот текст для обработки:
---
{text}
---
"""


def process_url(url: str) -> str:
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        text = trafilatura.extract(resp.text, no_fallback=True)
        if not text or len(text) < 200:
            return "Не удалось извлечь текст страницы."
        text = text[:15000]
        result = model.generate_content(PROMPT.format(text=text))
        return result.text
    except Exception as e:
        logger.error(f"Ошибка при обработке ссылки: {e}")
        return "Ошибка при обработке страницы."


# --- Инициализация и запуск Telegram Application ---
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
application = Application.builder().token(TELEGRAM_TOKEN).build()
loop.run_until_complete(application.initialize())


# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"/start от chat_id={update.effective_chat.id}")
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Привет! 👋 Отправь мне ссылку — и я создам пост.",
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(
        f"Получено сообщение от {update.effective_chat.id}: {update.message.text}"
    )
    match = re.search(r"https?://\S+", update.message.text)
    if match:
        url = match.group(0)
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text="Обрабатываю ссылку... 🧙‍♂️"
        )
        summary = process_url(url)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=summary,
            disable_web_page_preview=True,
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text="Пожалуйста, отправь ссылку."
        )


application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))


# --- Webhook обработка ---
@flask_app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    try:
        logger.info("Webhook вызван — получили POST от Telegram.")
        data = request.get_json(force=True)
        logger.info(f"Raw update: {data}")
        update = Update.de_json(data, application.bot)
        logger.info(
            f"Update успешно десериализован. От chat_id={update.effective_chat.id}"
        )

        # Используем loop, без закрытия
        future = asyncio.run_coroutine_threadsafe(
            application.process_update(update), loop
        )
        future.result(timeout=10)  # дождаться результата, иначе завершится слишком рано

        return jsonify({"ok": True})
    except Exception as e:
        logger.error(f"Ошибка в webhook-хендлере: {e}")
        return jsonify({"ok": False})


# --- Установка webhook ---
from asyncio import run


@flask_app.route("/set_webhook", methods=["GET"])
def set_webhook():
    try:
        run(application.bot.set_webhook(url=WEBHOOK_URL))
        return "webhook setup ok"
    except Exception as e:
        logger.error(f"Ошибка установки webhook: {e}")
        return "webhook setup failed"
