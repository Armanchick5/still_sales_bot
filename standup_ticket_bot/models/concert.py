import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Enum as SQLEnum
from standup_ticket_bot.database import Base


class SourceEnum(enum.Enum):
    YANDEX = "YANDEX"
    GOSTANDUP = "GOSTANDUP"
    TIMEPAD = "TIMEPAD"


class Concert(Base):
    __tablename__ = "concerts"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String, index=True, nullable=False)
    name = Column(String, index=True, nullable=False)
    date = Column(DateTime, index=True, nullable=False)
    tickets_sold = Column(Integer, nullable=False)
    tickets_total = Column(Integer, nullable=False)
    source = Column(SQLEnum(SourceEnum), nullable=False)
    url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
