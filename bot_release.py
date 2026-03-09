# bot.py — бот для предложений постов и модерации
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
from aiogram.exceptions import TelegramAPIError

# ─── НАСТРОЙКИ (замени на свои значения) ────────────────────────────────────
BOT_TOKEN = ""
ADMIN_IDS = {123,321}
CHANNEL_ID = ""
DELAY_BEFORE_POST = 300

ADMIN_CHAT_ID = ADMIN_IDS  # должно быть целым числом

# Файлы для хранения данных
BAN_FILE = "bans.json"
POST_AUTHORS_FILE = "post_authors.json"
# Новый файл для хранения связи: signed_msg_id -> original_data
SIGNED_POSTS_FILE = "signed_posts.json"

# ─── ЗАГРУЗКА / СОХРАНЕНИЕ ДАННЫХ ───────────────────────────────────────────

def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

banned_users = set(load_json(BAN_FILE, []))
post_authors = load_json(POST_AUTHORS_FILE, {})          # original_msg_id -> {"user_id": id, "username": str}
signed_posts = load_json(SIGNED_POSTS_FILE, {})          # signed_msg_id -> original_msg_id

def save_bans():
    save_json(BAN_FILE, list(banned_users))

def save_post_authors():
    save_json(POST_AUTHORS_FILE, post_authors)

def save_signed_posts():
    save_json(SIGNED_POSTS_FILE, signed_posts)

# ─── ИНИЦИАЛИЗАЦИЯ ──────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

def get_keyboard(original_msg_id: int, signed_msg_id: int = None) -> InlineKeyboardMarkup:
    """
    Кнопки под сообщением.
    Для оригинального сообщения (без подписи) signed_msg_id = None.
    Для сообщения с подписью передаём original_msg_id и signed_msg_id.
    """
    if signed_msg_id is None:
        # Это оригинальное сообщение – не должно быть кнопок, его не модерируем напрямую
        return None
    else:
        # Сообщение с подписью – привязываем к original_msg_id
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Одобрить", callback_data=f"ok:{original_msg_id}"),
                InlineKeyboardButton(text="✅ Анонимно", callback_data=f"anon:{original_msg_id}"),
            ],
            [
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"no:{original_msg_id}"),
                InlineKeyboardButton(text="🚫 Забанить", callback_data=f"ban:{original_msg_id}"),
            ],
            [
                InlineKeyboardButton(text="⏫ Сейчас", callback_data=f"now:{original_msg_id}"),
                InlineKeyboardButton(text="⏫ Анонимно сейчас", callback_data=f"nowanon:{original_msg_id}"),
            ]
        ])

@dp.message(CommandStart())
async def cmd_start(m: Message):
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
    user_id = m.from_user.id
    if user_id == ADMIN_CHAT_ID:
        return
    if user_id in banned_users:
        await m.reply("Ты забанен и не можешь предлагать посты.")
        return

    try:
        # 1. Копируем оригинальное сообщение в чат админа (без подписи)
        original = await bot.copy_message(
            chat_id=ADMIN_CHAT_ID,
            from_chat_id=m.chat.id,
            message_id=m.message_id
        )
        logging.info(f"Оригинал скопирован, id={original.message_id}")

        # Запоминаем автора
        username = m.from_user.username or f"ID {user_id}"
        post_authors[str(original.message_id)] = {
            "user_id": user_id,
            "username": username
        }
        save_post_authors()

        # 2. Создаём сообщение с подписью
        signature = f"\n\n👤<i>{username}</i>"
        if m.text:
            text_with_signature = m.text + signature
            signed = await bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=text_with_signature,
                reply_to_message_id=original.message_id
            )
        elif m.caption:
            # Если есть медиа, копируем его с новым caption
            signed = await bot.copy_message(
                chat_id=ADMIN_CHAT_ID,
                from_chat_id=m.chat.id,
                message_id=m.message_id,
                caption=m.caption + signature
            )
        else:
            # Например, фото без подписи – добавляем подпись как caption
            signed = await bot.copy_message(
                chat_id=ADMIN_CHAT_ID,
                from_chat_id=m.chat.id,
                message_id=m.message_id,
                caption=signature.strip()
            )
        logging.info(f"Сообщение с подписью создано, id={signed.message_id}")

        # Запоминаем связь signed -> original
        signed_posts[str(signed.message_id)] = original.message_id
        save_signed_posts()

        # 3. Отправляем кнопки под сообщением с подписью
        await bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text="Действия с постом:",
            reply_to_message_id=signed.message_id,
            reply_markup=get_keyboard(original.message_id, signed.message_id)
        )

        await m.reply("✅ Твой пост отправлен на модерацию!")

    except Exception as e:
        logging.error(f"Ошибка при отправке поста от {user_id}: {e}", exc_info=True)
        await m.reply("Произошла ошибка. Попробуй позже.")

@dp.callback_query(lambda c: c.data and c.data[0].isalpha())
async def on_moderation(c: CallbackQuery):
    if c.from_user.id != ADMIN_CHAT_ID:
        await c.answer("Нет прав", show_alert=True)
        return

    parts = c.data.split(":")
    action = parts[0]
    original_msg_id = int(parts[1])
    # Для action = ok/anon/now/nowanon/ban/no

    # Получаем информацию об авторе
    author_info = post_authors.get(str(original_msg_id))

    # Отклонение
    if action == "no":
        await c.message.edit_text(c.message.text + "\n\n❌ Отклонено", reply_markup=None)
        await c.answer("Отклонено")
        return

    # Бан
    if action == "ban":
        if author_info:
            user_id = author_info.get("user_id")
            banned_users.add(user_id)
            save_bans()
            await c.message.edit_text(c.message.text + "\n\n🚫 Пользователь забанен", reply_markup=None)
            await c.answer("Забанен")
        else:
            await c.answer("Автор не найден", show_alert=True)
        return

    # Публикация (с задержкой или сейчас)
    if action in ("ok", "anon", "now", "nowanon"):
        is_anon = action in ("anon", "nowanon")
        is_instant = action in ("now", "nowanon")

        # Находим сообщение с подписью (signed) по original_msg_id
        # У нас есть signed_posts: signed -> original, нам нужно original -> signed
        # Поэтому переберём вручную (можно оптимизировать, но для курсовой ок)
        signed_msg_id = None
        for signed, orig in signed_posts.items():
            if orig == original_msg_id:
                signed_msg_id = int(signed)
                break

        if not signed_msg_id:
            await c.answer("Сообщение с подписью не найдено", show_alert=True)
            return

        # Выбираем, что копировать в канал
        if is_anon:
            # Анонимно – копируем оригинал (без подписи)
            source_msg_id = original_msg_id
            # Удаляем сообщение с подписью из чата админа (экономия места)
            try:
                await bot.delete_message(chat_id=ADMIN_CHAT_ID, message_id=signed_msg_id)
                logging.info(f"Удалено сообщение с подписью {signed_msg_id}")
            except TelegramAPIError:
                pass
        else:
            # С подписью – копируем сообщение с подписью
            source_msg_id = signed_msg_id

        # Функция публикации
        async def publish():
            if not is_instant:
                # Ждём
                await asyncio.sleep(DELAY_BEFORE_POST)
            try:
                published = await bot.copy_message(
                    chat_id=CHANNEL_ID,
                    from_chat_id=ADMIN_CHAT_ID,
                    message_id=source_msg_id
                )
                logging.info(f"Пост {original_msg_id} опубликован в канале, анонимно: {is_anon}")
            except Exception as e:
                logging.error(f"Ошибка публикации: {e}")

        # Запускаем публикацию
        asyncio.create_task(publish())

        # Обновляем статус в админском чате
        status_text = "Опубликовано сейчас" if is_instant else f"В очереди (через {DELAY_BEFORE_POST//60} мин)"
        await c.message.edit_text(
            c.message.text + f"\n\n✅ {'Анонимно' if is_anon else 'С подписью'} – {status_text}",
            reply_markup=None
        )
        await c.answer("Готово")
        return

    await c.answer("Неизвестное действие", show_alert=True)

async def main():
    logging.info("Бот запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())