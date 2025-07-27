# test_yandex_api.py
import asyncio
from standup_ticket_bot.parsers import _yandex_auth, parse_yandex


async def main():
    # Посмотрим, что генерит наша auth-функция
    auth = _yandex_auth()
    print("Auth из parsers.py:", auth)

    # А теперь запустим сам парсер
    events = await parse_yandex()
    print("Статус парсера:", "получил события" if events else "список пустой")
    print("Примеры:", events[:3])


if __name__ == "__main__":
    asyncio.run(main())
