FROM python:3.11-slim

WORKDIR /app

# Копируем и ставим зависимости
COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# Копируем весь проект
COPY . .

# Запускаем модуль
CMD ["python", "-m", "standup_ticket_bot.main"]
