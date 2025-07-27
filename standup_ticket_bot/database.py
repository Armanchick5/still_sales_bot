import os
from dotenv import load_dotenv, find_dotenv

# Загружаем .env из корня проекта
load_dotenv(find_dotenv())

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL не задан в .env")

# Создаём асинхронный движок и сессию
engine = create_async_engine(DATABASE_URL, echo=True)
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

Base = declarative_base()


async def init_db():
    """
    Создаёт все таблицы в БД (если их ещё нет).
    Вызывать перед любыми операциями с базой.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
