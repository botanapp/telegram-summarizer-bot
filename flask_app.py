import os
import logging
import re
import telegram
import trafilatura
import google.generativeai as genai
import requests
from flask import Flask, request
import config


TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
BASE_URL = os.environ.get("BASE_URL")
WEBHOOK_URL = f"{BASE_URL}/{TELEGRAM_TOKEN}"


# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

if not TELEGRAM_TOKEN:
    # Эта ошибка будет видна в логах Render при старте приложения
    logger.critical(
        "КРИТИЧЕСКАЯ ОШИБКА: TELEGRAM_TOKEN не найден! Приложение не может стартовать."
    )
    # Можно даже вызвать ошибку, чтобы приложение "упало" и сразу сообщило о проблеме
    raise ValueError("Переменная TELEGRAM_TOKEN не установлена!")

# Инициализируем бота ОДИН РАЗ, так как это нужно в любом случае.
bot = telegram.Bot(TELEGRAM_TOKEN)

app = Flask(__name__)

# Настройка Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-pro")

# Наш промпт для нейросети. Он — сердце нашего бота.
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
    """Главная функция: скачивает, извлекает текст и генерирует пост."""
    try:
        # --- НАШЕ УЛУЧШЕНИЕ ---
        # 1. Заголовки, которые притворяются обычным браузером
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
        }

        # 2. Скачиваем страницу с помощью requests, передавая наши заголовки
        response = requests.get(
            url, headers=headers, timeout=15
        )  # timeout чтобы не ждать вечно
        response.raise_for_status()  # Эта строка вызовет ошибку, если сайт ответил кодом 4xx или 5xx (напр. 404 Not Found)

        # 3. Передаем скачанный HTML-контент в trafilatura для извлечения текста
        # Мы больше не используем fetch_url, а сразу extract
        text = trafilatura.extract(
            response.text,
            include_comments=False,
            include_tables=False,
            no_fallback=True,
        )
        # --- КОНЕЦ УЛУЧШЕНИЯ ---

        if not text or len(text) < 200:
            return "Не удалось извлечь основной текст статьи. Страница может быть слишком короткой или иметь нестандартную структуру (или требовать JavaScript)."

        max_length = 15000
        text = text[:max_length]

        full_prompt = PROMPT.format(text=text)
        response_gemini = model.generate_content(full_prompt)

        return response_gemini.text

    # Добавляем обработку ошибок от requests
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при скачивании URL: {e}")
        return f"Не удалось скачать содержимое по ссылке. Сайт недоступен или заблокировал запрос. (Ошибка: {e})"
    except Exception as e:
        logger.error(f"Произошла ошибка при обработке URL или генерации текста: {e}")
        return "Произошла внутренняя ошибка при обработке. Попробуйте другую ссылку."


@app.route(f"/{TELEGRAM_TOKEN}", methods=["POST"])
def webhook_handler():
    if request.method == "POST":
        try:
            update = telegram.Update.de_json(request.get_json(force=True), bot)

            # Игнорируем обновления, которые не являются сообщениями
            if not update.message:
                logger.info(
                    "Получено обновление без сообщения (например, редактирование). Игнорируем."
                )
                return "ok"

            chat_id = update.message.chat.id
            text = update.message.text

            if text == "/start":
                bot.send_message(
                    chat_id=chat_id,
                    text="Привет! 👋 Отправь мне ссылку на статью, и я сделаю из нее пост для твоего канала.",
                )
                return "ok"

            # Ищем ссылку в любом месте сообщения, а не только в начале
            url_match = re.search(r"https?://\S+", text)
            if url_match:
                url = url_match.group(0)  # Извлекаем найденную ссылку
                bot.send_message(
                    chat_id=chat_id, text="Принял ссылку. Начинаю обработку... 🧙‍♂️"
                )
                summary = process_url(url)
                bot.send_message(
                    chat_id=chat_id, text=summary, disable_web_page_preview=True
                )
            else:
                bot.send_message(
                    chat_id=chat_id,
                    text="Пожалуйста, отправь мне валидную ссылку, начинающуюся с http:// или https://",
                )

        except Exception as e:
            # Логируем любую неожиданную ошибку здесь
            logger.error(f"Критическая ошибка в webhook_handler: {e}")

    return "ok"


# Этот маршрут нужен только для первоначальной установки вебхука
@app.route("/set_webhook", methods=["GET", "POST"])
def set_webhook():
    s = bot.set_webhook(WEBHOOK_URL)
    if s:
        return "webhook setup ok"
    else:
        return "webhook setup failed"
