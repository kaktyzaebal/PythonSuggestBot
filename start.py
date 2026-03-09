# start.py — запускает оба бота в одном процессе

import asyncio
import logging

from bot import dp as suggest_dp, bot as suggest_bot


logging.basicConfig(level=logging.INFO)

async def main():
    # Запускаем оба polling параллельно
    await asyncio.gather(
        suggest_dp.start_polling(suggest_bot, allowed_updates=["message"]),

    )

if __name__ == "__main__":
    asyncio.run(main())