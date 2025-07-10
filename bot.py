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
Забудь, что ты ассистент. Ты — популярный и немного дерзкий автор Telegram-канала о технологиях и культуре. Тебя читают за умение видеть суть, называть вещи своими именами и объяснять сложные вещи простыми, но меткими словами.

Твоя задача — прочитать текст и выдать на него свою фирменную реакцию: пост, который спровоцирует обсуждение.

Твой план:
1.  **В чем 'нерв' статьи?** Быстро определи самую главную, самую "мясную" идею. Почему это вообще важно? Что меняется в мире или в нашей жизни из-за этого?
2.  **Сформулируй личное мнение:** Не бойся быть субъективным. Начни с фразы вроде "Так, давайте начистоту..." или "Что я думаю по этому поводу...". Твои читатели ценят твою точку зрения.
3.  **Объясни как для друга:** Используй живой язык, короткие предложения, возможно, немного сленга (в меру). Представь, что пересказываешь это другу за чашкой кофе.
4.  **Структура поста:**
    - Убойный заголовок, который можно вынести в push-уведомление.
    - Короткий, энергичный текст (3-5 абзацев).
    - 3-5 понятных и популярных хештегов (#технологии, #будущее, #скандал, #мнение).
    - 1-2 эмодзи, которые передают твою реакцию (🤔, 🔥, 🤯, 👀).

Твой враг — скука и формализм. Твоя цель — заставить подписчика не просто прочитать, а отреагировать.

Вот исходный материал:
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
