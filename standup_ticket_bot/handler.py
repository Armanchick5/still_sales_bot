from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from standup_ticket_bot.database import AsyncSessionLocal
from standup_ticket_bot.concert_repository import list_concerts
from standup_ticket_bot.keyboards import main_kb
from standup_ticket_bot.models.concert import SourceEnum

router = Router()

SOURCE_ICONS: dict[SourceEnum, str] = {
    SourceEnum.YANDEX: "®Яндекс",
    SourceEnum.GOSTANDUP: "GOSTANDUP",
    SourceEnum.TIMEPAD: "Timepad",
}

# Максимальная длина текста одного сообщения (~4096),
# оставляем запас для тегов и разделителей
MAX_MESSAGE_SIZE = 3800


async def _send_concerts(message: Message, concerts: list, title: str) -> None:
    if not concerts:
        await message.answer(
            "Концертов не найдено.",
            reply_markup=main_kb
        )
        return

    header = f"<b>{title}</b>\n\n"
    chunk = header

    for ev in concerts:
        icon = SOURCE_ICONS.get(ev.source, ev.source.name)
        # Переводим UTC время в московское (UTC+3)
        dt_local = ev.date + timedelta(hours=3)
        dt_str = dt_local.strftime("%Y-%m-%d %H:%M")

        # Вычисляем оставшиеся дни и процент продаж
        now = datetime.utcnow()
        delta = ev.date - now
        days_left = delta.total_seconds() / 86400
        sold_pct = ev.tickets_sold / ev.tickets_total if ev.tickets_total else 0

        # Определяем маркер цвета в зависимости от условий
        if days_left < 3:
            marker = "🔴 " if sold_pct < 0.7 else "🟢 "
        elif days_left < 7:
            marker = "🟠 " if sold_pct < 0.5 else "🟢 "
        elif days_left < 14:
            marker = "🟡 " if sold_pct < 0.3 else "🟢 "
        else:
            marker = "🟢 "

        # Формируем блок без ссылки
        block = (
            f"{marker}{icon}\n"
            f"<b>{ev.name}</b>\n"
            f"{dt_str}\n"
            f"{ev.tickets_sold}/{ev.tickets_total}\n\n"
        )

        # Если блок превышает размер сообщения, отправляем текущий и начинаем новый
        if len(chunk) + len(block) > MAX_MESSAGE_SIZE:
            await message.answer(
                chunk,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=main_kb
            )
            chunk = header + block
        else:
            chunk += block

    # Отправляем остаток
    if chunk.strip():
        await message.answer(
            chunk,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=main_kb
        )


@router.message(Command("start"))
async def start_handler(message: Message):
    await message.answer(
        "Привет! Я бот, который показывает предстоящие стендап-концерты.\n"
        "Выбери одну из кнопок ниже, чтобы увидеть концерты.",
        reply_markup=main_kb,
    )


@router.message(F.text == "Все концерты")
async def all_concerts_handler(message: Message):
    async with AsyncSessionLocal() as session:
        concerts = await list_concerts(session, days_ahead=None)
    await _send_concerts(message, concerts, "Все концерты")


@router.message(F.text == "Ближайшие 3 дня")
async def concerts_3_days_handler(message: Message):
    async with AsyncSessionLocal() as session:
        concerts = await list_concerts(session, days_ahead=3)
    await _send_concerts(message, concerts, "Концерты на ближайшие 3 дня")


@router.message(F.text == "Ближайшие 7 дней")
async def concerts_7_days_handler(message: Message):
    async with AsyncSessionLocal() as session:
        concerts = await list_concerts(session, days_ahead=7)
    await _send_concerts(message, concerts, "Концерты на ближайшие 7 дней")


@router.message(F.text == "Ближайшие 21 день")
async def concerts_21_days_handler(message: Message):
    async with AsyncSessionLocal() as session:
        concerts = await list_concerts(session, days_ahead=21)
    await _send_concerts(message, concerts, "Концерты на ближайшие 21 день")
