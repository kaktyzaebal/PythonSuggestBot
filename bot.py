# bot_unified.py — один бот для предложений и модерации

import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
)

# ─── НАСТРОЙКИ ──────────────────────────────────────────────────────────────

from config import BOT_TOKEN, ADMIN_IDS, DELAY_BEFORE_POST, CHANNEL_ID                     # 5 минут

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def get_keyboard(msg_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton("✅ Одобрить", callback_data=f"ok_{msg_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"no_{msg_id}")
    ]])


@dp.message(CommandStart())
async def cmd_start(m: Message):
    if m.from_user.id in ADMIN_IDS:
        await m.answer("Привет, админ! Я буду присылать тебе посты на проверку.")
    else:
        await m.answer(
            "Привет! 👋\n\n"
            "Пришли мне свою историю.\n"
            "Я отправлю её на модерацию админам."
        )


@dp.message()
async def handle_message(m: Message):
    # Админ пишет боту → игнорируем (кроме команд)
    if m.from_user.id in ADMIN_IDS:
        return

    # Обычный пользователь прислал пост
    try:
        # Пересылаем пост каждому админу с кнопками
        for admin_id in ADMIN_IDS:
            sent_msg = await bot.forward_message(
                chat_id=admin_id,
                from_chat_id=m.chat.id,
                message_id=m.message_id
            )
            await bot.send_message(
                admin_id,
                f"Новый пост от @{m.from_user.username or m.from_user.id}\n"
                f"Дата: {m.date.strftime('%d.%m.%Y %H:%M')}",
                reply_markup=get_keyboard(sent_msg.message_id - 1)
            )

        await m.reply("✅ Твой пост отправлен на модерацию!")
    except Exception as e:
        await m.reply("Не удалось отправить на модерацию 😔")
        logging.error(f"Ошибка: {e}")


@dp.callback_query(lambda c: c.data.startswith(("ok_", "no_")))
async def on_callback(c: CallbackQuery):
    if c.from_user.id not in ADMIN_IDS:
        await c.answer("Нет прав", show_alert=True)
        return

    action, msg_id = c.data.split("_", 1)
    msg_id = int(msg_id)

    if action == "no":
        await c.message.edit_text(
            c.message.text + "\n\n❌ Отклонено",
            reply_markup=None
        )
        await c.answer("Отклонено")
        return

    # Одобрено → отложенная публикация
    publish_time = datetime.now() + timedelta(seconds=DELAY_BEFORE_POST)

    await c.message.edit_text(
        c.message.text + f"\n\n✅ Одобрено → публикация через {DELAY_BEFORE_POST//60} мин",
        reply_markup=None
    )
    await c.answer("Пост поставлен в очередь")

    asyncio.create_task(
        delayed_publish(
            original_msg_id=msg_id,
            chat_id=c.message.chat.id,
            publish_time=publish_time
        )
    )


async def delayed_publish(original_msg_id: int, chat_id: int, publish_time: datetime):
    delay = (publish_time - datetime.now()).total_seconds()
    if delay > 0:
        await asyncio.sleep(delay)

    try:
        await bot.copy_message(
            chat_id=CHANNEL_ID,
            from_chat_id=chat_id,
            message_id=original_msg_id
        )
        logging.info(f"Опубликован пост {original_msg_id}")
    except Exception as e:
        logging.error(f"Ошибка публикации: {e}")


async def main():
    print(f"Бот запущен. Токен: {BOT_TOKEN[:10]}...")
    await dp.start_polling(bot)


if __name__ == "main":
    asyncio.run(main())