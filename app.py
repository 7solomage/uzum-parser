from flask import Flask, request, jsonify
import requests
import json
import time
import random
import logging
import os
import re
from urllib.parse import urlparse, urljoin, parse_qs
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

# Настройка приложения Flask
app = Flask(__name__)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Заголовки для имитации браузера
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
}

class UzumParser:
    def __init__(self):
        self.base_url = "https://uzum.uz"
        self.driver = None
        
    def _setup_selenium(self):
        """Настройка Selenium WebDriver"""
        if self.driver is not None:
            return self.driver
            
        logger.info("Инициализация Selenium WebDriver")
        try:
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument(f"user-agent={HEADERS['User-Agent']}")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_argument("--disable-extensions")
            
            # На сервере может потребоваться указать путь к chromedriver
            # service = Service('/usr/bin/chromedriver')
            # self.driver = webdriver.Chrome(service=service, options=chrome_options)
            
            self.driver = webdriver.Chrome(options=chrome_options)
            logger.info("Selenium WebDriver успешно инициализирован")
            return self.driver
        except Exception as e:
            logger.error(f"Ошибка при инициализации Selenium: {e}")
            return None
    
    def _close_selenium(self):
        """Закрытие Selenium WebDriver"""
        if self.driver:
            try:
                self.driver.quit()
                self.driver = None
                logger.info("Selenium WebDriver закрыт")
            except Exception as e:
                logger.error(f"Ошибка при закрытии Selenium: {e}")
    
    def get_product_details(self, product_url):
        """Получение информации о товаре через Selenium"""
        if not product_url:
            logger.error("URL товара не определен")
            return None
        
        driver = self._setup_selenium()
        if not driver:
            logger.error("Не удалось инициализировать Selenium")
            return None
        
        logger.info(f"Загрузка страницы товара через Selenium: {product_url}")
        
        try:
            driver.get(product_url)
            
            # Ждем загрузки основных элементов товара
            wait_time = 5
            logger.info(f"Ожидание {wait_time} секунд для полной загрузки страницы")
            time.sleep(wait_time)
            
            # Извлекаем ID товара из URL
            product_id = None
            parts = product_url.split('/')
            for i, part in enumerate(parts):
                if part == 'product' and i+1 < len(parts):
                    product_id = parts[i+1].split('?')[0]
                    break
            
            # Получаем данные о товаре
            product_data = self._extract_data_from_js(driver)
            if product_data:
                # Добавляем URL товара
                product_data['url'] = product_url
                return product_data
            
            # Если не удалось извлечь данные из JS, пробуем парсить HTML
            return self._parse_html(driver, product_url)
        
        except Exception as e:
            logger.error(f"Ошибка при получении данных о товаре через Selenium: {e}")
            return None
        finally:
            # Закрываем Selenium после использования
            self._close_selenium()
    
    def _extract_data_from_js(self, driver):
        """Извлечение данных о товаре из JavaScript переменных"""
        logger.info("Попытка извлечь данные о товаре из JavaScript переменных")
        
        js_scripts = [
            # Попытка найти данные о товаре в глобальных переменных
            """
            var productData = null;
            
            // Ищем в window.__INITIAL_STATE__
            if (window.__INITIAL_STATE__) {
                if (window.__INITIAL_STATE__.pdp && window.__INITIAL_STATE__.pdp.data) {
                    productData = window.__INITIAL_STATE__.pdp.data;
                } else if (window.__INITIAL_STATE__.product) {
                    productData = window.__INITIAL_STATE__.product;
                }
            }
            
            // Ищем в window.__NUXT__
            if (!productData && window.__NUXT__) {
                if (window.__NUXT__.state && window.__NUXT__.state.pdp && window.__NUXT__.state.pdp.data) {
                    productData = window.__NUXT__.state.pdp.data;
                } else if (window.__NUXT__.state && window.__NUXT__.state.product) {
                    productData = window.__NUXT__.state.product;
                }
            }
            
            // Ищем в window.__NEXT_DATA__
            if (!productData && window.__NEXT_DATA__) {
                if (window.__NEXT_DATA__.props && window.__NEXT_DATA__.props.pageProps && window.__NEXT_DATA__.props.pageProps.product) {
                    productData = window.__NEXT_DATA__.props.pageProps.product;
                }
            }
            
            return productData;
            """
        ]
        
        for i, script in enumerate(js_scripts):
            try:
                result = driver.execute_script(script)
                if result:
                    logger.info(f"Получены данные о товаре через JS скрипт #{i+1}")
                    return self._process_js_data(result)
            except Exception as e:
                logger.error(f"Ошибка при выполнении JS скрипта #{i+1}: {e}")
        
        logger.warning("Не удалось получить данные о товаре через JavaScript")
        return None
    
    def _process_js_data(self, data):
        """Обработка данных о товаре, полученных из JavaScript"""
        product_data = {}
        
        try:
            # Название товара
            if 'title' in data:
                product_data['name'] = data['title']
            elif 'name' in data:
                product_data['name'] = data['name']
            else:
                product_data['name'] = 'Название не найдено'
            
            # Описание товара
            description = None
            if 'description' in data:
                description = data['description']
            elif 'detail' in data and 'description' in data['detail']:
                description = data['detail']['description']
            
            product_data['description'] = description or 'Описание отсутствует'
            
            # Цена товара
            if 'price' in data:
                if isinstance(data['price'], dict):
                    price = data['price'].get('current') or data['price'].get('price')
                else:
                    price = data['price']
                
                if price:
                    product_data['price'] = f"{price:,.0f} сум"
                    product_data['price_raw'] = price  # Добавляем числовое значение для сортировки
                else:
                    product_data['price'] = 'Цена не указана'
                    product_data['price_raw'] = 0
            else:
                product_data['price'] = 'Цена не указана'
                product_data['price_raw'] = 0
            
            # Изображения товара
            images = []
            for img_field in ['photos', 'images', 'gallery', 'mediaList']:
                if img_field in data and isinstance(data[img_field], list):
                    for img in data[img_field]:
                        if isinstance(img, str):
                            images.append(img)
                        elif isinstance(img, dict):
                            for key in ['url', 'src', 'original', 'path']:
                                if key in img:
                                    images.append(img[key])
                                    break
            
            # Нормализация URL изображений
            normalized_images = []
            for img_url in images:
                if img_url.startswith('//'):
                    img_url = 'https:' + img_url
                elif img_url.startswith('/'):
                    img_url = urljoin(self.base_url, img_url)
                normalized_images.append(img_url)
            
            product_data['images'] = normalized_images if normalized_images else []
            
            # Добавляем строку с изображениями через запятую для удобства импорта
            product_data['images_str'] = ','.join(product_data['images'])
            
            # Проверяем наличие информации о цветах
            if 'colors' in data and isinstance(data['colors'], list) and data['colors']:
                product_data['colors'] = []
                for color in data['colors']:
                    if isinstance(color, dict):
                        color_name = color.get('name', '')
                        color_id = color.get('id', '')
                        if color_name:
                            product_data['colors'].append({
                                'name': color_name,
                                'id': color_id
                            })
                
                # Добавляем строку с цветами через запятую
                product_data['colors_str'] = ','.join([c['name'] for c in product_data['colors']])
            
            # Доступность товара
            if 'availableAmount' in data:
                product_data['availability'] = data['availableAmount'] > 0
            elif 'inStock' in data:
                product_data['availability'] = data['inStock']
            else:
                product_data['availability'] = True  # Предполагаем, что товар доступен по умолчанию
            
            logger.info(f"Успешно обработаны данные о товаре из JS: {product_data['name']}")
            return product_data
        
        except Exception as e:
            logger.error(f"Ошибка при обработке данных из JS: {e}")
            return None
    
    def _parse_html(self, driver, product_url):
        """Парсинг HTML-страницы товара"""
        logger.info("Парсинг HTML-страницы товара")
        
        product_data = {
            'name': 'Название не найдено',
            'description': 'Описание отсутствует',
            'price': 'Цена не указана',
            'price_raw': 0,
            'images': [],
            'images_str': '',
            'colors': [],
            'colors_str': '',
            'availability': True,
            'url': product_url
        }
        
        try:
            # Используем BeautifulSoup для парсинга
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            # Название товара
            title_selectors = [
                'h1.title', 'h1.product-title', '.product-title', '.product-name',
                'h1[itemprop="name"]', '.product-info h1', '.product-detail h1'
            ]
            
            for selector in title_selectors:
                title_element = soup.select_one(selector)
                if title_element and title_element.text.strip():
                    product_data['name'] = title_element.text.strip()
                    logger.info(f"Найдено название товара: {product_data['name']}")
                    break
            
            # Описание товара
            description_selectors = [
                '.product-description', '.description', '[itemprop="description"]',
                '.product-details', '.product-info .description', '.details-container'
            ]
            
            for selector in description_selectors:
                desc_element = soup.select_one(selector)
                if desc_element and desc_element.text.strip():
                    product_data['description'] = desc_element.text.strip()
                    logger.info(f"Найдено описание товара (первые 50 символов): {product_data['description'][:50]}...")
                    break
            
            # Цена товара
            price_selectors = [
                '.product-price', '.price', '[itemprop="price"]',
                '.current-price', '.price-current', '.product-info .price'
            ]
            
            for selector in price_selectors:
                price_element = soup.select_one(selector)
                if price_element and price_element.text.strip():
                    price_text = price_element.text.strip()
                    product_data['price'] = price_text
                    
                    # Попытка извлечь числовое значение цены
                    price_digits = re.sub(r'[^\d]', '', price_text)
                    if price_digits:
                        try:
                            product_data['price_raw'] = int(price_digits)
                        except ValueError:
                            pass
                    
                    logger.info(f"Найдена цена товара: {product_data['price']}")
                    break
            
            # Изображения товара
            image_selectors = [
                '.product-gallery img', '.product-images img', '.gallery img',
                '.product-photo img', '.swiper-slide img'
            ]
            
            for selector in image_selectors:
                img_elements = soup.select(selector)
                if img_elements:
                    for img in img_elements:
                        img_url = img.get('src') or img.get('data-src')
                        if img_url:
                            # Нормализуем URL
                            if img_url.startswith('//'):
                                img_url = 'https:' + img_url
                            elif img_url.startswith('/'):
                                img_url = urljoin(self.base_url, img_url)
                            
                            product_data['images'].append(img_url)
                    
                    product_data['images_str'] = ','.join(product_data['images'])
                    logger.info(f"Найдено {len(product_data['images'])} изображений товара")
                    break
            
            # Если не нашли изображения через селекторы, ищем через метатеги
            if not product_data['images']:
                meta_img = soup.select_one('meta[property="og:image"]')
                if meta_img and meta_img.get('content'):
                    img_url = meta_img.get('content')
                    # Нормализуем URL
                    if img_url.startswith('//'):
                        img_url = 'https:' + img_url
                    elif img_url.startswith('/'):
                        img_url = urljoin(self.base_url, img_url)
                    
                    product_data['images'].append(img_url)
                    product_data['images_str'] = img_url
                    logger.info(f"Найдено изображение товара через метатег: {img_url}")
            
            # Попытка найти цвета
            color_selectors = [
                '.colors-list .color-item', '.color-options .color-option',
                '.color-selector .color'
            ]
            
            for selector in color_selectors:
                color_elements = soup.select(selector)
                if color_elements:
                    for elem in color_elements:
                        color_name = elem.get('title') or elem.get('data-color') or elem.text.strip()
                        if color_name:
                            product_data['colors'].append({
                                'name': color_name,
                                'id': elem.get('data-id', '')
                            })
                    
                    product_data['colors_str'] = ','.join([c['name'] for c in product_data['colors']])
                    logger.info(f"Найдено {len(product_data['colors'])} цветов товара")
                    break
            
            return product_data
            
        except Exception as e:
            logger.error(f"Ошибка при парсинге HTML: {e}")
            return product_data
    
    def get_shop_products(self, shop_url, limit=None, max_pages=None):
        """Получение ссылок на товары из магазина с поддержкой пагинации"""
        if not shop_url:
            logger.error("URL магазина не определен")
            return []
        
        logger.info(f"Получение товаров из магазина: {shop_url}")
        
        # Извлекаем ID магазина или имя из URL
        shop_id = shop_url.split('/')[-1].split('?')[0]
        
        driver = self._setup_selenium()
        if not driver:
            logger.error("Не удалось инициализировать Selenium")
            return []
        
        all_product_links = []
        current_page = 1
        
        try:
            # Загружаем первую страницу
            logger.info(f"Загрузка первой страницы магазина: {shop_url}")
            driver.get(shop_url)
            
            # Ждем загрузки страницы
            wait_time = 5
            logger.info(f"Ожидание {wait_time} секунд для полной загрузки страницы")
            time.sleep(wait_time)
            
            # Цикл по страницам магазина
            while True:
                logger.info(f"Обработка страницы {current_page} магазина {shop_id}")
                
                # Прокручиваем страницу вниз для загрузки всех товаров (ленивая загрузка)
                self._scroll_page(driver)
                
                # Ищем ссылки на товары на текущей странице
                try:
                    # Пытаемся найти через JavaScript
                    js_links = self._extract_product_links_js(driver)
                    if js_links:
                        all_product_links.extend(js_links)
                        logger.info(f"Найдено {len(js_links)} ссылок на товары через JavaScript на странице {current_page}")
                except Exception as e:
                    logger.error(f"Ошибка при извлечении ссылок через JavaScript: {e}")
                
                # Если через JavaScript не нашли, парсим HTML
                if not js_links:
                    html_links = self._extract_product_links_html(driver)
                    if html_links:
                        all_product_links.extend(html_links)
                        logger.info(f"Найдено {len(html_links)} ссылок на товары через HTML на странице {current_page}")
                
                # Проверяем, есть ли следующая страница
                next_page_exists = False
                
                # Проверяем через JavaScript наличие кнопки следующей страницы
                try:
                    next_page_exists = driver.execute_script("""
                        const paginationElements = document.querySelectorAll('.pagination a, .page-navigation a, .pager a');
                        for (const elem of paginationElements) {
                            if (elem.textContent.trim() === '→' || 
                                elem.textContent.trim() === 'Next' || 
                                elem.textContent.trim() === 'Следующая' ||
                                elem.textContent.trim() === 'Keyingi' ||
                                elem.getAttribute('aria-label') === 'Next page' ||
                                elem.classList.contains('next-page')) {
                                return true;
                            }
                        }
                        return false;
                    """)
                except Exception as e:
                    logger.error(f"Ошибка при проверке наличия следующей страницы: {e}")
                
                # Условия выхода из цикла
                if not next_page_exists:
                    logger.info(f"Достигнута последняя страница магазина {shop_id}")
                    break
                
                if max_pages and current_page >= max_pages:
                    logger.info(f"Достигнуто максимальное количество страниц ({max_pages})")
                    break
                
                # Переходим на следующую страницу
                try:
                    success = driver.execute_script("""
                        const paginationElements = document.querySelectorAll('.pagination a, .page-navigation a, .pager a');
                        for (const elem of paginationElements) {
                            if (elem.textContent.trim() === '→' || 
                                elem.textContent.trim() === 'Next' || 
                                elem.textContent.trim() === 'Следующая' ||
                                elem.textContent.trim() === 'Keyingi' ||
                                elem.getAttribute('aria-label') === 'Next page' ||
                                elem.classList.contains('next-page')) {
                                elem.click();
                                return true;
                            }
                        }
                        return false;
                    """)
                    
                    if success:
                        current_page += 1
                        logger.info(f"Переход на страницу {current_page}")
                        # Ждем загрузки следующей страницы
                        time.sleep(wait_time)
                    else:
                        logger.warning("Не удалось перейти на следующую страницу")
                        break
                except Exception as e:
                    logger.error(f"Ошибка при переходе на следующую страницу: {e}")
                    break
            
            # Удаляем дубликаты
            all_product_links = list(set(all_product_links))
            logger.info(f"Всего найдено {len(all_product_links)} уникальных ссылок на товары в магазине {shop_id}")
            
            # Ограничиваем количество ссылок, если нужно
            if limit and len(all_product_links) > limit:
                all_product_links = all_product_links[:limit]
                logger.info(f"Ограничено количество ссылок до {limit}")
            
            return all_product_links
