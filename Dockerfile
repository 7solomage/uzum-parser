FROM python:3.9-slim

# Установка необходимых пакетов
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    chromium \
    chromium-driver

# Создание рабочей директории
WORKDIR /app

# Копирование файлов проекта
COPY . .

# Установка зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Переменная среды для ChromeDriver
ENV PYTHONUNBUFFERED=1
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver
ENV CHROME_BIN=/usr/bin/chromium

# Указание порта
EXPOSE 5000

# Команда запуска сервера
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
