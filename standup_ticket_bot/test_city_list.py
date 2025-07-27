# test_city_list.py  (переименуйте, например, в test_parse_yandex.py)
import asyncio
from standup_ticket_bot.parsers import parse_yandex


async def main():
    events = await parse_yandex()
    print("Найдено мероприятий:", len(events))
    for ev in events[:5]:
        print(ev["external_id"], ev["name"], ev["date"])


if __name__ == "__main__":
    asyncio.run(main())
