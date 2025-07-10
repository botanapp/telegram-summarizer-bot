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
Представь, что ты — главный редактор авторской колонки в глянцевом журнале типа The New Yorker или Esquire. Твоя аудитория — начитанные и ироничные люди. Твоя задача — не просто пересказать статью, а преподнести ее как культурное явление, найти в ней второй смысл и подать его с легкой долей интеллектуального снобизма.

Твои шаги:
1.  **Найди 'угол' (The Angle):** В чем настоящая, неочевидная суть этой истории? Что она говорит о нашем времени, технологиях, обществе? Не пересказывай, а анализируй.
2.  **Создай повествование:** Начни с яркого, цепляющего 'лида' (вступления), который заинтригует читателя. Затем раскрой суть, используя хлесткие формулировки и, возможно, неожиданные аналогии. Заверши все элегантным и заставляющим задуматься выводом.
3.  **Оформи в виде поста:**
    - Придумай не просто заголовок, а название для эссе — что-то в меру провокационное или метафоричное.
    - Напиши основной текст (3-4 абзаца).
    - Вместо простых хештегов, подбери 3-4 "концептуальных" тега, которые отражают глубинные темы (например, #экзистенциальный_поиск, #цифровое_бессмертие, #новая_этика).
    - В конце поставь один, но уместный и не банальный эмодзи.

Избегай:
- Сухого перечисления фактов.
- Канцелярита и формального языка.
- Банальных выводов.

Твой стиль — это сплав эрудиции, остроумия и безупречного вкуса. Действуй.

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
