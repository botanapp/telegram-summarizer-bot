import os
import logging
import re
import trafilatura
import requests
import google.generativeai as genai

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# Настройка логов
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Отправь мне ссылку — я сделаю пост.")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    match = re.search(r"https?://\S+", text)
    if match:
        await update.message.reply_text("Обрабатываю ссылку... 🧙‍♂️")
        summary = process_url(match.group(0))
        await update.message.reply_text(summary, disable_web_page_preview=True)
    else:
        await update.message.reply_text("Пожалуйста, пришли ссылку.")


def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
    )
    application.run_polling()


if __name__ == "__main__":
    main()
