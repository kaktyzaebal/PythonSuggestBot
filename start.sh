#!/usr/bin/env bash
# start.sh — портативный запуск бота с проверкой зависимостей

set -euo pipefail

echo "========================================"
echo "Запуск Telegram-бота через start.py"
echo "Проверка зависимостей..."
echo "========================================"

# Проверяем наличие requirements.txt
if [ ! -f "requirements.txt" ]; then
    echo "Ошибка: файл requirements.txt не найден!"
    exit 1
fi

# Проверяем наличие start.py
if [ ! -f "start.py" ]; then
    echo "Ошибка: файл start.py не найден!"
    exit 1
fi

# Установка/обновление зависимостей
echo "Установка/обновление пакетов из requirements.txt..."
pip install -r requirements.txt --quiet --upgrade || {
    echo "Ошибка при установке зависимостей!"
    exit 1
}

echo "Зависимости проверены и установлены ✓"

# Если используешь виртуальное окружение — раскомментируй
# source venv/bin/activate

# Запускаем start.py
echo "Запускаю start.py..."
python start.py &

# Запоминаем PID
BOT_PID=$!

sleep 2  # даём время на запуск

# Проверяем, жив ли процесс
if ps -p $BOT_PID > /dev/null; then
    echo ""
    echo "Бот успешно запущен!"
    echo "PID процесса: $BOT_PID"
    echo ""
    echo "Чтобы остановить бота выполни:"
    echo "  kill $BOT_PID"
    echo "или просто нажми Ctrl+C в этом терминале"
else
    echo "Ошибка: бот не запустился (проверь логи выше)"
    exit 1
fi

# Держим терминал открытым, чтобы видеть логи бота
wait $BOT_PID