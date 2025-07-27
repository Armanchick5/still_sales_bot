# import os
# import asyncio
#
# from aiogram import Bot, Dispatcher
# from aiogram.filters import Command
#
# from standup_ticket_bot.database import init_db, AsyncSessionLocal
# from standup_ticket_bot.parsers import parse_gostandup, parse_timepad, parse_yandex
# from standup_ticket_bot.concert_repository import upsert_concert
# from standup_ticket_bot.handler import router as base_router
#
# BOT_TOKEN = os.getenv("BOT_TOKEN")
# if not BOT_TOKEN:
#     raise RuntimeError("BOT_TOKEN не задан в .env")
#
#
# async def refresh_all_events():
#     async with AsyncSessionLocal() as session:
#         # GoStandUp + Timepad в одном upsert-запросе
#         try:
#             await upsert_concert(session, parse_gostandup, parse_timepad)
#         except Exception as e:
#             print("Ошибка обновления событий GOSTANDUP/TIMEPAD:", e)
#
#
# async def scheduler_loop():
#     while True:
#         await refresh_all_events()
#         await asyncio.sleep(5 * 60)
#
#
# async def main():
#     await init_db()
#
#     print("Первичное обновление событий…")
#     await refresh_all_events()
#     print("Первичное обновление завершено")
#
#     bot = Bot(token=BOT_TOKEN)
#     dp = Dispatcher()
#     dp.include_router(base_router)
#
#     @dp.message(Command("refresh"))
#     async def cmd_refresh(message):
#         await message.answer("Обновляю события…")
#         await refresh_all_events()
#         await message.answer("Готово!")
#
#     asyncio.create_task(scheduler_loop())
#     await dp.start_polling(bot)
#
#
# if __name__ == "__main__":
#     asyncio.run(main())

# standup_ticket_bot/main.py
#
# Полностью обновлённый файл запуска бота:
# • Поддерживает три парсера (Yandex CRM + GoStandUp + Timepad).
# • Любая ошибка отдельного парсера логируется, но не останавливает остальные.
# • Раз в 5 минут автоматически обновляет мероприятия.
# • Команда /refresh вручную запускает обновление.

# standup_ticket_bot/main.py
#
# Универсальный запуск бота:
#   • Upsert работает через одну функцию upsert_concert,
#     которой передаём САМИ парсер-функции (а не списки словарей).
#   • Все парсеры асинхронные — upsert_concert внутри разберётся,
#     await-ая их при необходимости.
#   • Ошибки каждого источника логируются и не ломают остальные.
#   • /refresh в чате принудительно обновляет базы.

import os
import asyncio
from typing import Callable

from aiogram import Bot, Dispatcher
from aiogram.filters import Command

from standup_ticket_bot.database import init_db, AsyncSessionLocal
from standup_ticket_bot.parsers import parse_yandex, parse_gostandup, parse_timepad
from standup_ticket_bot.concert_repository import upsert_concert
from standup_ticket_bot.handler import router as base_router
from dotenv import load_dotenv


load_dotenv()


BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан в .env")

PARSERS: tuple[Callable[..., list[dict]], ...] = (
    parse_yandex,
    parse_gostandup,  # async
    parse_timepad,  # async
)


async def refresh_all_events() -> None:
    """
    Вызывает upsert_concert один раз, передавая все парсер-функции.
    Любая ошибка выводится в консоль, но цикл не прерывается.
    """
    async with AsyncSessionLocal() as session:
        try:
            await upsert_concert(session, *PARSERS)
            print("✓  Данные всех источников обновлены")
        except Exception as e:
            print("‼️  Ошибка обновления мероприятий:", e)


async def scheduler_loop() -> None:
    """Фоновый планировщик — каждые 5 минут."""
    while True:
        await refresh_all_events()
        await asyncio.sleep(120 * 60)


async def main() -> None:
    await init_db()

    print("Первичное обновление событий…")
    await refresh_all_events()
    print("Первичное обновление завершено")

    # Telegram-бот
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(base_router)

    # /refresh — ручное обновление
    @dp.message(Command("refresh"))
    async def cmd_refresh(message):
        await message.answer("Обновляю события…")
        await refresh_all_events()
        await message.answer("Готово!")

    # Запускаем фоновый планировщик
    asyncio.create_task(scheduler_loop())

    # Стартуем polling
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
