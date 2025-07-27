# # standup_ticket_bot/schemas.py
#
# from datetime import datetime
# from enum import Enum
# from pydantic import BaseModel
#
# # Можно импортировать ваш enum из моделей, чтобы не дублировать строки
# from standup_ticket_bot.models.concert import SourceEnum as _SA_SourceEnum
#
#
# class SourceEnum(str, Enum):
#     YANDEX = _SA_SourceEnum.YANDEX.value
#     GOSTANDUP = _SA_SourceEnum.GOSTANDUP.value
#     TIMEPAD = _SA_SourceEnum.TIMEPAD.value
#
#
# class ConcertExternal(BaseModel):
#     external_id: str        # id события в стороннем сервисе
#     name: str               # название
#     date: datetime          # дата/время начала
#     tickets_sold: int       # сколько продано
#     tickets_total: int      # вместимость / всего билетов
#     url: str                # ссылка на страницу события
#     source: SourceEnum      # источник (YANDEX, GOSTANDUP или TIMEPAD)
#
#     class Config:
#         use_enum_values = True
# standup_ticket_bot/schemas.py

from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class YandexCRMItem(BaseModel):
    id: int
    name: str
    startDateTime: datetime
    ticketsSold: int
    ticketsQuantity: int
    url: Optional[str] = None


class YandexCRMResponse(BaseModel):
    count: int
    items: List[YandexCRMItem]
