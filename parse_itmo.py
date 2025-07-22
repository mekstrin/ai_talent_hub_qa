import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def download_with_selenium(url, download_path=None):
    """Скачивание файла с помощью Selenium, имитируя клик по кнопке"""

    # Настраиваем директорию для загрузки
    if download_path is None:
        download_path = os.path.join(os.getcwd(), "downloads")
    os.makedirs(download_path, exist_ok=True)

    # Настраиваем опции Chrome
    chrome_options = Options()
    prefs = {
        "download.default_directory": download_path,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": False
    }
    chrome_options.add_experimental_option("prefs", prefs)

    try:
        # Инициализируем драйвер
        driver = webdriver.Chrome(options=chrome_options)

        # Открываем страницу
        driver.get(url)
        print(f"Открыта страница: {url}")

        # Используем более точный селектор с родительским элементом
        button_selector = "div.StudyPlan_plan__button__R_2QR button.ButtonSimple_button__JbIQ5.ButtonSimple_button_masterProgram__JK8b_"

        button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, button_selector))
        )

        print("Кнопка найдена, выполняем клик...")
        button.click()

        # Ждем завершения загрузки
        print("Ожидание загрузки файла...")
        time.sleep(5)  # Ждем 5 секунд для завершения загрузки

        print(f"Файл должен быть загружен в: {download_path}")
        return True

    except Exception as e:
        print(f"Ошибка при скачивании файла: {e}")
        return False

    finally:
        if 'driver' in locals():
            driver.quit()