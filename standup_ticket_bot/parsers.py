from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List
import os, time, hashlib, aiohttp, json
from dateutil import parser as date_parser

from standup_ticket_bot.models.concert import SourceEnum
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# ╔═══════════════════════════════════════════════════════════════════════╗
# ║                         YANDEX AFISHA (CRM)                           ║
# ╚═══════════════════════════════════════════════════════════════════════╝
YANDEX_API_URL = os.getenv("YANDEX_API_URL", "https://api.tickets.yandex.net/api/crm/")
YANDEX_LOGIN = os.getenv("YANDEX_API_LOGIN")
YANDEX_PASSWORD = os.getenv("YANDEX_API_PASSWORD")
YANDEX_CITY_ID = os.getenv("YANDEX_CITY_ID", "34348482")


def _yandex_auth() -> str:
    """LOGIN:sha1(md5(PASSWORD)+TS):TS  — всё в нижнем регистре."""
    if not (YANDEX_LOGIN and YANDEX_PASSWORD):
        raise RuntimeError("YANDEX_API_LOGIN / PASSWORD отсутствуют в .env")

    ts = str(int(time.time()))
    pwd_md5 = hashlib.md5(YANDEX_PASSWORD.encode()).hexdigest()
    sha1 = hashlib.sha1(f"{pwd_md5}{ts}".encode()).hexdigest()
    return f"{YANDEX_LOGIN}:{sha1}:{ts}"


async def _yandex_call(action: str, **extra: Any) -> Dict[str, Any]:
    params: Dict[str, Any] = {
        "action": action,
        "auth": _yandex_auth(),
        "city_id": YANDEX_CITY_ID,
        "format": "json",
        **extra,
    }
    url = YANDEX_API_URL.rstrip("/") + "/"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            raw = await resp.text()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError(f"Yandex вернул не-JSON ({resp.status}): {raw[:150]}")
    if data.get("status") != "0":
        raise RuntimeError(f"Yandex API error {action}: {data}")
    return data


def _flatten(lst: Any) -> List[Any]:
    """crm.*.list иногда отдаёт список списков – расплющиваем."""
    flat: List[Any] = []
    for item in lst:
        flat.extend(item if isinstance(item, list) else [item])
    return flat


async def parse_yandex() -> List[dict]:
    """Возвращает только будущие события из Яндекс Афиши с данными по билетам."""
    # 1. Сеансы (events)
    ev_resp = await _yandex_call("crm.event.list")
    events_raw = _flatten(ev_resp.get("result", []))
    if not events_raw:
        return []

    # 2. Отчёт по билетам
    ids = ",".join(str(e["id"]) for e in events_raw)
    rep_resp = await _yandex_call("crm.report.event", event_ids=ids)

    # Собираем статистику: для каждого event_id суммируем sold и total (sold+available)
    stats: Dict[str, dict] = {}
    for row in rep_resp.get("result", []):
        eid = str(row["event_id"])
        sold = row.get("tickets_sold", 0)
        avail = row.get("tickets_available", 0)
        total = sold + avail

        s = stats.setdefault(eid, {"sold": 0, "total": 0})
        s["sold"] += sold
        s["total"] += total

    # 3. Формируем итоговый список, фильтруя прошедшие
    items: List[dict] = []
    now = datetime.utcnow()
    for ev in events_raw:
        eid = str(ev["id"])
        name = ev.get("name", "").strip()
        dt = date_parser.parse(ev.get("date", "")).astimezone(timezone.utc).replace(tzinfo=None)
        if dt < now:
            continue

        st = stats.get(eid, {"sold": 0, "total": 0})
        sold = st["sold"]
        tickets_total = st["total"]

        items.append({
            "external_id": eid,
            "name": name,
            "date": dt,
            "tickets_sold": sold,
            "tickets_total": tickets_total,
            "url": f"https://afisha.yandex.ru/events/{eid}",
            "source": SourceEnum.YANDEX,
        })
    return items


# -------------------------------------------------------------------
# GoStandUp
# -------------------------------------------------------------------
GOSTANDUP_API_URL = os.getenv("GOSTANDUP_API_URL", "https://gostandup.ru/api/org")
GOSTANDUP_BEARER = os.getenv("GOSTANDUP_BEARER_TOKEN")
if not GOSTANDUP_BEARER:
    raise RuntimeError("GOSTANDUP_BEARER_TOKEN не задан в .env")


async def parse_gostandup() -> List[dict]:
    headers = {"Authorization": f"Bearer {GOSTANDUP_BEARER}"}
    async with aiohttp.ClientSession() as session:
        async with session.get(GOSTANDUP_API_URL, headers=headers) as resp:
            resp.raise_for_status()
            data = await resp.json()

    items: List[dict] = []
    for ev in data.get("events", []):
        t = ev.get("tickets", {})
        seats = t.get("seats", {})
        amount = t.get("amount", {})
        if seats.get("total", 0):
            sold, total = seats["sold"], seats["total"]
        else:
            sold, total = amount.get("sold", 0), amount.get("total", 0)

        url = ev.get("link") or ev.get("url") or f"https://gostandup.ru/event/{ev['id']}"
        items.append({
            "external_id": str(ev["id"]),
            "name": ev.get("title", "").strip(),
            "date": date_parser.parse(ev.get("date", "")),
            "tickets_sold": sold,
            "tickets_total": total,
            "url": url,
            "source": SourceEnum.GOSTANDUP,
        })
    return items


# -------------------------------------------------------------------
# Timepad
# -------------------------------------------------------------------
TIMEPAD_API_URL = os.getenv("TIMEPAD_API_URL", "https://api.timepad.ru/v1")
TIMEPAD_BEARER = os.getenv("TIMEPAD_BEARER_TOKEN")
TIMEPAD_ORG_ID = os.getenv("TIMEPAD_ORG_ID")
if not (TIMEPAD_BEARER and TIMEPAD_ORG_ID):
    raise RuntimeError("TIMEPAD_BEARER_TOKEN и/или TIMEPAD_ORG_ID не заданы в .env")


async def fetch_registration(session: aiohttp.ClientSession, event_id: str) -> dict:
    url = f"{TIMEPAD_API_URL}/events/{event_id}.json"
    params = {"fields": "registration"}
    async with session.get(url, headers={"Authorization": f"Bearer {TIMEPAD_BEARER}"}, params=params) as resp:
        resp.raise_for_status()
        data = await resp.json()
    places = data.get("registration", {}).get("places", [])
    if isinstance(places, list):
        return places[0] if places else {}
    return places


async def parse_timepad() -> List[dict]:
    url = f"{TIMEPAD_API_URL}/events.json"
    headers = {"Authorization": f"Bearer {TIMEPAD_BEARER}"}
    params = {
        "organization_ids": TIMEPAD_ORG_ID,
        "fields": "dates,ticket_types,starts_at",
        "limit": 100,
        "skip": 0,
        "sort": "+starts_at",
    }
    timeout = aiohttp.ClientTimeout(total=30)
    items: List[dict] = []
    now = datetime.utcnow()

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, headers=headers, params=params) as resp:
            resp.raise_for_status()
            data = await resp.json()
        for ev in data.get("values", []):
            ext_id = str(ev.get("id", ""))
            name = (ev.get("name", "") or ev.get("title", "")).strip()
            # Обработка даты
            ds = None
            if ev.get("dates"):
                ds = ev["dates"][0].get("start") or ev["dates"][0].get("date")
            else:
                ds = ev.get("starts_at")
            if not ds:
                continue
            dt = date_parser.parse(ds)
            if dt.tzinfo:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            if dt < now:
                continue

            ticket_types = ev.get("ticket_types", [])
            if ticket_types:
                sold = sum(tt.get("sold", 0) for tt in ticket_types)
                total = sum(tt.get("total", tt.get("count", 0)) for tt in ticket_types)
            else:
                reg = await fetch_registration(session, ext_id)
                sold = reg.get("registered", 0) or reg.get("count", 0)
                total = reg.get("limit", 0) or reg.get("capacity", 0)

            items.append({
                "external_id": ext_id,
                "name": name,
                "date": dt,
                "tickets_sold": sold,
                "tickets_total": total,
                "url": ev.get("url") or ev.get("site_url") or f"{TIMEPAD_API_URL}/events/{ext_id}",
                "source": SourceEnum.TIMEPAD,
            })
    return items
