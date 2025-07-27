from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import select

from standup_ticket_bot.database import AsyncSessionLocal
from standup_ticket_bot.models.concert import Concert
from standup_ticket_bot.handlers.utils import format_concert_row

router = Router()


async def _fetch_concerts(days: int | None = None) -> list[Concert]:
    async with AsyncSessionLocal() as session:
        stmt = select(Concert)
        if days is not None:
            now = datetime.utcnow()
            stmt = stmt.where(Concert.date.between(now, now + timedelta(days=days)))
        result = await session.execute(stmt)
        return result.scalars().all()


async def _send_concerts(message: Message, concerts: list[Concert]) -> None:
    if not concerts:
        await message.answer("Концертов не найдено.")
        return

    rows = [format_concert_row(c) for c in concerts]
    await message.answer("\n".join(rows))


@router.message(Command("all"))
@router.message(F.text == "Все концерты")
async def all_concerts_handler(message: Message) -> None:
    concerts = await _fetch_concerts()
    await _send_concerts(message, concerts)


@router.message(F.text == "Ближайшие 3 дня")
async def concerts_3_days_handler(message: Message) -> None:
    concerts = await _fetch_concerts(days=3)
    await _send_concerts(message, concerts)


@router.message(F.text == "Ближайшие 7 дней")
async def concerts_7_days_handler(message: Message) -> None:
    concerts = await _fetch_concerts(days=7)
    await _send_concerts(message, concerts)


@router.message(F.text == "Ближайшие 21 день")
async def concerts_21_days_handler(message: Message) -> None:
    concerts = await _fetch_concerts(days=21)
    await _send_concerts(message, concerts)
