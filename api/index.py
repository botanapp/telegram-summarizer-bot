import os
import logging
import re
import trafilatura
import google.generativeai as genai
import requests

from flask import Flask, request, jsonify
from asyncio import run
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

# --- ЛОГИРОВАНИЕ ---
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
BASE_URL = os.environ.get("BASE_URL")  # Например: https://your-bot.vercel.app
WEBHOOK_PATH = f"/{TELEGRAM_TOKEN}"
WEBHOOK_URL = f"{BASE_URL}{WEBHOOK_PATH}"

# --- ПРОВЕРКА ТОКЕНА ---
if not TELEGRAM_TOKEN:
    raise ValueError("Переменная TELEGRAM_TOKEN не установлена!")

# --- НАСТРОЙКА Gemini ---
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-pro")

# --- ПРОМПТ ---
PROMPT = """
Ты — ассистент, который помогает вести Telegram-канал.
Твоя задача — на основе текста веб-страницы сделать краткую и емкую заметку на русском языке.

Инструкции:
1. Внимательно изучи предоставленный текст.
2. Определи главную идею, ключевые тезисы и выводы.
3. Напиши саммари (краткую выжимку) на русском языке. Объем — 3-5 абзацев.
4. Стиль должен быть информативным, но легким для чтения, как для поста в Telegram.
5. Придумай яркий и цепляющий заголовок для поста.
6. Подбери 3-5 релевантных хештега.
7. В конце добавь эмодзи, соответствующий теме.

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


# --- ОБРАБОТКА URL ---
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
            return "Не удалось извлечь текст статьи. Возможно, страница пустая или нестандартная."

        text = text[:15000]
        prompt = PROMPT.format(text=text)
        result = model.generate_content(prompt)
        return result.text
    except Exception as e:
        logger.error(f"Ошибка обработки URL: {e}")
        return "Произошла ошибка при обработке ссылки. Попробуйте другую статью."


# --- ИНИЦИАЛИЗАЦИЯ Flask ---
flask_app = Flask(__name__)

# --- ИНИЦИАЛИЗАЦИЯ Telegram Application ---
application = Application.builder().token(TELEGRAM_TOKEN).build()


# --- ХЕНДЛЕР СООБЩЕНИЙ ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    chat_id = update.message.chat_id

    if text == "/start":
        await context.bot.send_message(
            chat_id=chat_id, text="Привет! 👋 Отправь мне ссылку на статью."
        )
        return

    match = re.search(r"https?://\S+", text)
    if match:
        url = match.group(0)
        await context.bot.send_message(
            chat_id=chat_id, text="Обрабатываю ссылку... 🧙‍♂️"
        )
        summary = process_url(url)
        await context.bot.send_message(
            chat_id=chat_id, text=summary, disable_web_page_preview=True
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Пожалуйста, отправь ссылку, начинающуюся с http или https.",
        )


# --- РЕГИСТРАЦИЯ ХЕНДЛЕРОВ ---
application.add_handler(MessageHandler(filters.TEXT, handle_message))


# --- ВЕБХУК-ХЕНДЛЕР ---
@flask_app.route(WEBHOOK_PATH, methods=["POST"])
def telegram_webhook():
    try:
        update = Update.de_json(request.get_json(force=True), application.bot)
        # Запускаем асинхронную обработку через run_coroutine_threadsafe
        from asyncio import get_event_loop, run_coroutine_threadsafe

        run_coroutine_threadsafe(application.process_update(update), application.loop)
    except Exception as e:
        logger.error(f"Ошибка при обработке запроса от Telegram: {e}")
    return jsonify({"ok": True})


# --- ХЕНДЛЕР ДЛЯ УСТАНОВКИ ВЕБХУКА ---
@flask_app.route("/set_webhook", methods=["GET"])
def set_webhook():
    try:
        run(application.bot.set_webhook(url=WEBHOOK_URL))
        return "webhook setup ok"
    except Exception as e:
        logger.error(f"Ошибка при установке webhook: {e}")
        return "webhook setup failed"


# --- ДЛЯ VERCEL: экспорт Flask app как `app` ---
app = flask_app  # 👈 это обязательно для Vercel!
