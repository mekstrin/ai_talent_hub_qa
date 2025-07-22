import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from gigachat import GigaChat
from parse_itmo import download_with_selenium
import time
import shutil
from secrets import GIGACHAT_API_KEY, TELEGRAM_TOKEN
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

GIGACHAT_FILE_IDS = []
GIGACHAT_API_URL = "https://gigachat.api.sbercloud.ru/api/v1/chat/completions"

# Состояния для диалога с пользователем
BACKGROUND = 0

# Настройка путей и имен файлов
META_INFO = {
    "Искуственный интеллект": {
        "url": "https://abit.itmo.ru/program/master/ai",
    },
    "Управление AI продуктами": {
        "url": "https://abit.itmo.ru/program/master/ai_product",
    }
}

logger = logging.getLogger(__name__)


class GigaChatClient:
    """Класс для работы с API GigaChat через официальный SDK"""

    def __init__(self, credentials, scope="GIGACHAT_API_PERS"):
        """
        Инициализация клиента GigaChat
        """
        self.gigachat = GigaChat(
            credentials=credentials,
            scope=scope,
            verify_ssl_certs=False
        )
        # Загружаем файлы при инициализации
        self.ensure_files_uploaded()

    def ensure_files_uploaded(self):
        """Проверка и загрузка файлов учебных планов в GigaChat"""
        logger.info("Проверка наличия файлов учебных планов")
        path = os.path.join(os.getcwd(), "downloads")
        # Проверяем наличие локальной директории
        shutil.rmtree(path, ignore_errors=True)
        os.makedirs(path, exist_ok=True)
        #
        # # Проверяем наличие и скачиваем файлы при необходимости
        for program, config in META_INFO.items():
            logger.info(f"Скачиваем файл учебного плана для {program}")
            download_with_selenium(config["url"], path)
            time.sleep(3)  # Даем время на завершение загрузки

        # Получаем список уже загруженных файлов
        try:
            uploaded_files = self.gigachat.get_files()
            for file in uploaded_files.data:
                self.gigachat.delete_file(file.id_)
            GIGACHAT_FILE_IDS.clear()
            for file in os.listdir(path):
                file_path = os.path.join(path, file)
                if file.endswith(".pdf") and os.path.isfile(file_path):
                    with open(file_path, "rb") as f:
                        uploaded_file = self.gigachat.upload_file(f, purpose="general")
                        GIGACHAT_FILE_IDS.append(uploaded_file.id_)
                        logger.info(f"Загружен файл {file}, ID: {uploaded_file.id_}")
        except Exception as e:
            logger.error(f"Ошибка при обработке файлов в GigaChat: {e}")

    def generate_answer(self, question, context):
        """Генерация ответа на основе контекста и вопроса с использованием файлов"""
        try:
            # Формируем запрос с вложениями файлов
            request_data = {
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Ты - помощник приёмной комиссии ИТМО. Ты отвечаешь на вопросы абитуриентов о магистерских программах по ИИ. "
                            "Используй информацию из предоставленных PDF-файлов учебных планов и контекста. "
                            "Если не можешь найти информацию, скажи что не знаешь ответа."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Контекст с веб-сайтов: {context}\n\nВопрос: {question}"
                    }
                ],
                "temperature": 0.1
            }

            if GIGACHAT_FILE_IDS:
                request_data["messages"][1]["attachments"] = GIGACHAT_FILE_IDS

            # Отправляем запрос к API
            response = self.gigachat.chat(request_data)

            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"Ошибка при обращении к GigaChat API: {e}")
            return f"Извините, произошла ошибка при обработке вашего запроса: {str(e)}"


class WebParser:
    """Класс для парсинга и анализа веб-страниц"""

    def __init__(self):
        self.cache = {}  # Кэш для страниц, чтобы не загружать одно и то же

    def get_page_content(self, url):
        """Получение содержимого страницы"""
        if url in self.cache:
            return self.cache[url]

        try:
            # Используем обычный requests для простого контента
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')
            # Извлекаем только текстовый контент
            text_content = self._extract_text_content(soup)

            self.cache[url] = text_content
            return text_content
        except Exception as e:
            logger.error(f"Ошибка при получении содержимого страницы {url}: {e}")
            return None

    def _extract_text_content(self, soup):
        """Извлечение текстового контента из HTML"""
        # Удаляем скрипты, стили и другие ненужные элементы
        for script in soup(["script", "style", "meta", "link"]):
            script.extract()

        # Получаем текст
        text = soup.get_text(separator="\n", strip=True)

        # Очищаем лишние пробелы и переносы строк
        lines = (line.strip() for line in text.splitlines())
        text = "\n".join(line for line in lines if line)

        return text

    def get_page_with_selenium(self, url):
        """Получение содержимого динамической страницы с помощью Selenium"""
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Запуск в фоновом режиме
        chrome_options.add_argument("--disable-gpu")

        try:
            driver = webdriver.Chrome(options=chrome_options)
            driver.get(url)

            # Ждем загрузки страницы
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            page_source = driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')
            text_content = self._extract_text_content(soup)

            self.cache[url] = text_content
            return text_content
        except Exception as e:
            logger.error(f"Ошибка при получении страницы через Selenium {url}: {e}")
            return None
        finally:
            if 'driver' in locals():
                driver.quit()

    def collect_content_from_urls(self):
        """Сбор контента со всех предопределенных URL"""
        all_content = []

        for program, config in META_INFO.items():
            content = self.get_page_content(config["url"])
            if not content:
                content = self.get_page_with_selenium(config["url"])

            if content:
                all_content.append(f"Содержимое страницы {program}:\n{content}")
        return "\n\n".join(all_content)

parser = WebParser()
all_content = parser.collect_content_from_urls()

# Инициализируем клиент GigaChat с учетом загрузки файлов
gigachat_client = GigaChatClient(GIGACHAT_API_KEY)


async def recommend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /recommend для запуска получения рекомендаций"""
    await update.message.reply_text(
        "Для подбора рекомендаций по выборным дисциплинам, расскажите о себе:\n\n"
        "- Ваше образование (специальность бакалавриата/специалитета)\n"
        "- Опыт работы\n"
        "- Навыки и технологии\n"
        "- Ваши интересы в области ИИ"
    )
    return BACKGROUND


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    question = update.message.text

    # Отправка сообщения о начале обработки
    processing_message = await update.message.reply_text(
        "Обрабатываю ваш запрос, это может занять некоторое время..."
    )

    # Генерируем ответ на основе вопроса
    answer = gigachat_client.generate_answer(question, all_content)

    # Удаляем сообщение о загрузке
    await processing_message.delete()

    # Отправляем ответ
    await update.message.reply_text(answer)


async def process_background(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка бэкграунда и генерация рекомендаций"""
    background = update.message.text

    loading_message = await update.message.reply_text("Анализирую учебные планы и подбираю рекомендации...")

    # Формируем запрос для получения рекомендаций
    question = (f"На основе моего бэкграунда ({background}) "
                f"Порекомендуй мне 3-4 выборные дисциплины из учебного плана. "
                f"Объясни, почему эти дисциплины подойдут мне с учетом моего опыта и интересов.")

    # Запрос к GigaChat с прикреплением файлов
    recommendation = gigachat_client.generate_answer(question, "")

    # Удаляем сообщение о загрузке
    await loading_message.delete()

    # Отправляем результат
    await update.message.reply_text(f"На основе вашего профиля, рекомендую:\n\n{recommendation}")

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена диалога"""
    await update.message.reply_text("Рекомендации отменены.")
    return ConversationHandler.END


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    await update.message.reply_text(
        "Я могу ответить на вопросы о магистерских программах ИТМО:\n"
        "- Искусственный интеллект (AI)\n"
        "- Управление AI-продуктами\n\n"
        "Доступные команды:\n"
        "/start - начало работы\n"
        "/help - справка\n"
        "/recommend - получить рекомендации по выборным дисциплинам\n\n"
        "Просто задайте вопрос, например:\n"
        "Какие вступительные экзамены нужно сдавать?"
    )


# Функции обработки команд бота
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    await update.message.reply_text(
        "Привет! Я бот-консультант по магистерским программам ИТМО в области ИИ.\n"
        "Задайте мне вопрос о программах 'Искусственный интеллект' и 'Управление AI продкутами'.\n"
    )


def main():
    """Запуск бота"""
    # Создаем приложение
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    # Добавляем диалог для получения рекомендаций
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("recommend", recommend)],
        states={
            BACKGROUND: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_background)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    application.add_handler(conv_handler)

    # Обработчик сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Инициализация выполнена, бот запущен.")
    # Запускаем бота
    application.run_polling()


if __name__ == '__main__':
    main()
