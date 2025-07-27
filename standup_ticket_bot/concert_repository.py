import inspect
from datetime import datetime, timedelta
from typing import Optional, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from standup_ticket_bot.models.concert import Concert


async def list_concerts(
        session: AsyncSession,
        days_ahead: Optional[int] = None
) -> list[Concert]:
    """
    Если days_ahead задан, возвращает концерты с датой >= now и <= now+days_ahead.
    Если days_ahead is None, возвращает **только будущие** концерты.
    """
    now = datetime.utcnow()

    if days_ahead is not None:
        end = now + timedelta(days=days_ahead)
        stmt = (
            select(Concert)
            .where(Concert.date >= now, Concert.date <= end)
            .order_by(Concert.date)
        )
    else:
        # Для всех концертов — тоже отсекаем прошедшие
        stmt = (
            select(Concert)
            .where(Concert.date >= now)
            .order_by(Concert.date)
        )

    result = await session.execute(stmt)
    return result.scalars().all()


async def upsert_concert(
        session: AsyncSession,
        *parsers: Callable[..., list[dict]]
) -> None:
    """
    Для каждого parser-функции:
      1. Вызывает её (await если async, иначе синхронно).
      2. Получает list[dict] с ключами:
         external_id, name, date, tickets_sold, tickets_total, source, url
      3. Ищет в БД концерт с таким external_id+source.
      4. Если найден — обновляет его поля, иначе создаёт новый Concert.
    После обработки всех парсеров делает один commit().
    """
    for parser in parsers:
        events = await parser() if inspect.iscoroutinefunction(parser) else parser()

        for ev in events:
            stmt = select(Concert).where(
                Concert.external_id == ev["external_id"],
                Concert.source == ev["source"]
            )
            res = await session.execute(stmt)
            existing = res.scalars().first()

            if existing:
                existing.name = ev["name"]
                existing.date = ev["date"]
                existing.tickets_sold = ev["tickets_sold"]
                existing.tickets_total = ev["tickets_total"]
                existing.url = ev["url"]
            else:
                session.add(Concert(
                    external_id=ev["external_id"],
                    name=ev["name"],
                    date=ev["date"],
                    tickets_sold=ev["tickets_sold"],
                    tickets_total=ev["tickets_total"],
                    source=ev["source"],
                    url=ev["url"],
                ))

    await session.commit()
