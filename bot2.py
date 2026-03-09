# bot.py — объединённый бот для предложений постов и модерации
# Запуск: python bot.py

import asyncio
import logging
import json
import os
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

# ─── НАСТРОЙКИ (замени на свои значения) ────────────────────────────────────

from config import BOT_TOKEN,ADMIN_IDS,CHANNEL_ID, DELAY_BEFORE_POST                 # Задержка перед публикацией (секунды)
ADMIN_CHAT_ID = ADMIN_IDS
# Файлы для хранения данных
BAN_FILE = "bans.json"
POST_AUTHORS_FILE = "post_authors.json"

# ─── ЗАГРУЗКА / СОХРАНЕНИЕ ДАННЫХ ───────────────────────────────────────────

def load_json(path, default):
    """Загружает JSON из файла или возвращает значение по умолчанию"""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

def save_json(path, data):
    """Сохраняет данные в JSON файл"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# Загружаем данные при старте
banned_users = set(load_json(BAN_FILE, []))
post_authors = load_json(POST_AUTHORS_FILE, {})  # ключ: str(message_id), значение: user_id

def save_bans():
    """Сохраняет список забаненных пользователей"""
    save_json(BAN_FILE, list(banned_users))

def save_post_authors():
    """Сохраняет соответствие message_id -> user_id"""
    save_json(POST_AUTHORS_FILE, post_authors)

# ─── ИНИЦИАЛИЗАЦИЯ ──────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def get_keyboard(msg_id: int) -> InlineKeyboardMarkup:
    """Кнопки под сообщением. Формат callback: действие:msg_id:флаг(опционально)"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton("✅ Одобрить",        callback_data=f"ok:{msg_id}"),
            InlineKeyboardButton("✅ Анонимно",        callback_data=f"ok:{msg_id}:anon"),
        ],
        [
            InlineKeyboardButton("❌ Отклонить",       callback_data=f"no:{msg_id}"),
            InlineKeyboardButton("🚫 Забанить",        callback_data=f"ban:{msg_id}"),
        ]
    ])


@dp.message(CommandStart())
async def cmd_start(m: Message):
    """Обработка /start"""
    if m.chat.id == ADMIN_CHAT_ID:
        await m.answer("Привет, админ! Я буду присылать тебе посты на проверку.")
    else:
        await m.answer(
            "Привет! 👋\n\n"
            "Пришли мне пост, который хочешь опубликовать в канале.\n"
            "Я отправлю его на модерацию."
        )


@dp.message()
async def handle_suggestion(m: Message):
    """Обработка входящего поста от обычного пользователя"""
    user_id = m.from_user.id

    # Админ пишет боту → игнорируем
    if user_id == ADMIN_CHAT_ID:
        return

    # Пользователь забанен
    if user_id in banned_users:
        await m.reply("Ты забанен и не можешь предлагать посты.")
        return

    try:
        # Копируем оригинальное сообщение в чат админа
        copied = await bot.copy_message(
            chat_id=ADMIN_CHAT_ID,
            from_chat_id=m.chat.id,
            message_id=m.message_id
        )

        # Запоминаем, кто автор этого сообщения
        post_authors[str(copied.message_id)] = user_id
        save_post_authors()

        # Формируем подпись: два отступа + тэг пользователя
        username = m.from_user.username or f"ID {user_id}"
        caption = f"\n\n@{username}"

        # Отправляем подпись + кнопки под копией
        await bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=caption,
            reply_to_message_id=copied.message_id,
            reply_markup=get_keyboard(copied.message_id)
        )

        await m.reply("✅ Твой пост отправлен на модерацию!")

    except Exception as e:
        logging.error(f"Ошибка при отправке поста от {user_id}: {e}")
        await m.reply("Произошла ошибка при отправке. Попробуй позже.")


@dp.callback_query(lambda c: c.data and c.data[0].isalpha())
async def on_moderation(c: CallbackQuery):
    """Обработка нажатия кнопок модератором"""
    if c.from_user.id != ADMIN_CHAT_ID:
        await c.answer("Нет прав", show_alert=True)
        return

    # Парсим callback_data в формате "действие:msg_id:флаг"
    parts = c.data.split(":")
    action = parts[0]
    msg_id = int(parts[1])
    flags = parts[2:]  # например, ["anon"] для анонимного одобрения

    # Отклонение
    if action == "no":
        await c.message.edit_text(c.message.text + "\n\n❌ Отклонено", reply_markup=None)
        await c.answer("Отклонено")
        return

    # Бан пользователя
    if action == "ban":
        user_id = post_authors.get(str(msg_id))
        if user_id:
            banned_users.add(user_id)
            save_bans()
            await c.message.edit_text(c.message.text + "\n\n🚫 Пользователь забанен", reply_markup=None)
            await c.answer("Забанен")
        else:
            await c.answer("Не удалось определить автора", show_alert=True)
        return

    # Одобрение (с флагом "anon" или без)
    if action == "ok":
        is_anon = "anon" in flags
        publish_time = datetime.now() + timedelta(seconds=DELAY_BEFORE_POST)
        status = "Одобрено" if not is_anon else "Одобрено анонимно"
        await c.message.edit_text(
            c.message.text + f"\n\n✅ {status} → публикация через {DELAY_BEFORE_POST//60} мин",
            reply_markup=None
        )
        await c.answer("Пост в очереди")

        asyncio.create_task(
            delayed_publish(
                msg_id=msg_id,
                chat_id=ADMIN_CHAT_ID,
                publish_time=publish_time,
                is_anon=is_anon
            )
        )
        return

    # Если действие не распознано
    await c.answer("Неизвестное действие", show_alert=True)


async def delayed_publish(msg_id: int, chat_id: int, publish_time: datetime, is_anon: bool):
    """Отложенная публикация в канал"""
    # Ждём до указанного времени
    await asyncio.sleep(max(0, (publish_time - datetime.now()).total_seconds()))

    try:
        published = await bot.copy_message(
            chat_id=CHANNEL_ID,
            from_chat_id=chat_id,
            message_id=msg_id
        )

        # Если нужно анонимно и у сообщения есть подпись – удаляем её
        if is_anon:
            try:
                # Пытаемся отредактировать caption (работает для фото, видео и т.д.)
                await bot.edit_message_caption(
                    chat_id=CHANNEL_ID,
                    message_id=published.message_id,
                    caption=None
                )
            except Exception:
                # Если у сообщения нет caption (например, просто текст) – ничего не делаем
                pass

        logging.info(f"Опубликован пост {msg_id} (анонимно: {is_anon})")
    except Exception as e:
        logging.error(f"Ошибка публикации {msg_id}: {e}")


async def main():
    logging.info("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())