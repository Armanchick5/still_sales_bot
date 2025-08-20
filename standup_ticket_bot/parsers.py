from __future__ import annotations

"""Parsers for Yandex Afisha (CRM), GoStandUp, and Timepad.

Все функции асинхронные и возвращают список словарей одинаковой структуры:
    {
        "external_id": str,
        "name": str,
        "date": datetime,               # naive-UTC
        "tickets_sold": int,
        "tickets_total": int,
        "url": str,
        "source": SourceEnum,
    }
"""

from datetime import datetime, timezone
from typing import List, Any, Dict
import time
import hashlib
import json
import itertools
import aiohttp
import os

from dateutil import parser as date_parser
from dotenv import load_dotenv

from standup_ticket_bot.models.concert import SourceEnum

load_dotenv()

# ╔═══════════════════════════════════════════════════════════════════════╗
# ║                         YANDEX AFISHA (CRM)                           ║
# ╚═══════════════════════════════════════════════════════════════════════╝
YANDEX_API_URL = os.getenv("YANDEX_API_URL", "https://api.tickets.yandex.net/api/crm/")
YANDEX_LOGIN = os.getenv("YANDEX_API_LOGIN")
YANDEX_PASSWORD = os.getenv("YANDEX_API_PASSWORD")
YANDEX_CITY_ID = int(os.getenv("YANDEX_CITY_ID", "34348482"))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _yandex_auth() -> str:
    """LOGIN:sha1(md5(PASSWORD)+TS):TS  — всё в нижнем регистре (hex)."""
    if not (YANDEX_LOGIN and YANDEX_PASSWORD):
        raise RuntimeError("YANDEX_API_LOGIN / PASSWORD отсутствуют в .env")

    ts = str(int(time.time()))
    pwd_md5 = hashlib.md5(YANDEX_PASSWORD.encode()).hexdigest()   # lower
    sha1 = hashlib.sha1(f"{pwd_md5}{ts}".encode()).hexdigest()    # lower
    return f"{YANDEX_LOGIN}:{sha1}:{ts}"


a_sync_session: aiohttp.ClientSession | None = None
def _session() -> aiohttp.ClientSession:
    """Single shared ClientSession (lazy)."""
    global a_sync_session
    if a_sync_session is None or a_sync_session.closed:
        a_sync_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
    return a_sync_session


# ---------- helpers for robust json parsing ----------
def _safe_json(raw: str):
    """Возвращает первый валидный JSON из raw.
    Если ничего валидного нет — поднимает RuntimeError c снитпетом ответа.
    """
    raw = (raw or "").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Попробуем вытащить первый JSON-объект/массив из начала строки
        decoder = json.JSONDecoder()
        try:
            obj, _ = decoder.raw_decode(raw)
            return obj
        except Exception:
            # Последняя попытка: отрезать «мусор» после последней скобки
            last = max(raw.find("{"), raw.find("["))
            last_close = max(raw.rfind("}"), raw.rfind("]"))
            if last != -1 and last_close != -1 and last_close > last:
                candidate = raw[: last_close + 1]
                try:
                    return json.loads(candidate)
                except Exception:
                    pass
    # Всё совсем плохо — покажем кусочек ответа для диагностики
    snippet = raw[:800].replace("\n", "\\n")
    raise RuntimeError(f"Non-JSON API response. Snippet: {snippet}")


async def _yandex_call(action: str, **extra: Any) -> Dict[str, Any]:
    """Low-level wrapper around Yandex CRM API."""
    params: Dict[str, Any] = {
        "action": action,
        "auth": _yandex_auth(),
        "city_id": YANDEX_CITY_ID,
        "format": "json",
        **extra,
    }
    url = YANDEX_API_URL.rstrip("/") + "/"
    async with _session().get(url, params=params) as resp:
        raw = await resp.text()
    data: Dict[str, Any] = _safe_json(raw)

    if data.get("status") != "0":
        raise RuntimeError(f"Yandex API error {action}: {data}")
    return data


def _flatten(lst: List[Any]) -> List[Any]:
    """crm.*.list иногда отдаёт список списков – расплющиваем."""
    return list(itertools.chain.from_iterable((i if isinstance(i, list) else [i]) for i in lst))


def _parse_dt(raw: str) -> datetime:
    """Return **naive-UTC** datetime from API date string.

    Если в строке даты есть tz, приводим к UTC и убираем tzinfo,
    чтобы сравнение с datetime.utcnow() было корректным.
    """
    dt = date_parser.parse(raw) if raw else datetime.min
    if dt.tzinfo:  # aware → normalize to UTC
        dt = dt.astimezone(timezone.utc)
    return dt.replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def parse_yandex() -> List[dict]:
    """Return future Yandex Afisha events with ticket stats."""
    # 1. Сеансы (events)
    ev_resp = await _yandex_call("crm.event.list")
    events_raw = _flatten(ev_resp.get("result", []))
    if not events_raw:
        return []

    # 2. Отчёт по билетам (batched by IDs)
    ids = ",".join(str(e["id"]) for e in events_raw)
    rep_resp = await _yandex_call("crm.report.event", event_ids=ids)

    # 2.1. Собираем корректную статистику по каждому event_id
    stats: Dict[str, dict] = {}
    for row in rep_resp.get("result", []):
        eid = str(row["event_id"])
        sold  = row.get("tickets_sold", 0)
        avail = row.get("tickets_available", 0)
        total = sold + avail

        s = stats.setdefault(eid, {"sold": 0, "total": 0})
        s["sold"]  += sold
        s["total"] += total

    # 3. Формируем итоговый список, фильтруя прошедшие
    items: List[dict] = []
    now = datetime.utcnow()

    for ev in events_raw:
        if ev.get("status") != 1:  # пропускаем закрытые/неактуальные сеансы
            continue

        eid = str(ev["id"])
        name = ev.get("name", "").strip()
        dt = _parse_dt(ev.get("date", ""))

        # Отброс прошедших событий
        if dt < now:
            continue

        st = stats.get(eid, {"sold": 0, "total": 0})
        items.append({
            "external_id": eid,
            "name": name,
            "date": dt,
            "tickets_sold": st["sold"],
            "tickets_total": st["total"],
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
    raise RuntimeError("GOSTANDUP_BEARER_TOKEN not set in .env")


async def parse_gostandup() -> List[dict]:
    headers = {"Authorization": f"Bearer {GOSTANDUP_BEARER}"}
    async with _session().get(GOSTANDUP_API_URL, headers=headers) as resp:
        resp.raise_for_status()
        raw = await resp.text()
        data = _safe_json(raw)

    items: List[dict] = []
    for ev in data.get("events", []):
        t = ev.get("tickets", {}) or {}
        seats = t.get("seats", {}) or {}
        amt = t.get("amount", {}) or {}

        # Текущая логика (если нужно — можно суммировать оба блока):
        sold = seats.get("sold") if seats.get("total") else amt.get("sold", 0)
        total = seats.get("total") or amt.get("total", 0)

        items.append({
            "external_id": str(ev["id"]),
            "name": (ev.get("title") or "").strip(),
            "date": _parse_dt(ev.get("date", "")),
            "tickets_sold": sold,
            "tickets_total": total,
            "url": ev.get("link") or ev.get("url") or f"https://gostandup.ru/event/{ev['id']}",
            "source": SourceEnum.GOSTANDUP
        })
    return items


# -------------------------------------------------------------------
# Timepad
# -------------------------------------------------------------------
TIMEPAD_API_URL = os.getenv("TIMEPAD_API_URL", "https://api.timepad.ru/v1")
TIMEPAD_BEARER = os.getenv("TIMEPAD_BEARER_TOKEN")
TIMEPAD_ORG_ID = os.getenv("TIMEPAD_ORG_ID")
if not (TIMEPAD_BEARER and TIMEPAD_ORG_ID):
    raise RuntimeError("TIMEPAD creds missing")


async def fetch_registration(session: aiohttp.ClientSession, event_id: str) -> dict:
    url = f"{TIMEPAD_API_URL}/events/{event_id}.json"
    params = {"fields": "registration"}
    async with session.get(url, headers={"Authorization": f"Bearer {TIMEPAD_BEARER}"}, params=params) as resp:
        resp.raise_for_status()
        raw = await resp.text()
        data = _safe_json(raw)
    places = data.get("registration", {}).get("places", [])
    return places[0] if isinstance(places, list) and places else places or {}


async def parse_timepad() -> List[dict]:
    url = f"{TIMEPAD_API_URL}/events.json"
    headers = {"Authorization": f"Bearer {TIMEPAD_BEARER}"}
    params = {
        "organization_ids": TIMEPAD_ORG_ID,
        "fields": "dates,starts_at,ticket_types",
        "limit": 100,
        "skip": 0,
        "sort": "+starts_at",
    }
    items: List[dict] = []
    session = _session()

    async with session.get(url, headers=headers, params=params) as resp:
        resp.raise_for_status()
        raw = await resp.text()
        data = _safe_json(raw)

    for ev in data.get("values", []):
        ext = str(ev.get("id"))
        name = (ev.get("name") or ev.get("title") or "").strip()

        ds = ev.get("dates")
        raw_dt = (ds and (ds[0].get("start") or ds[0].get("date"))) or ev.get("starts_at")
        if not raw_dt:
            continue

        dt = _parse_dt(raw_dt)

        tt = ev.get("ticket_types", []) or []
        if tt:
            sold = sum((t.get("sold") or 0) for t in tt)
            total = sum((t.get("total") or t.get("count") or 0) for t in tt)
        else:
            reg = await fetch_registration(session, ext)
            sold = reg.get("registered", 0) or reg.get("count", 0)
            total = reg.get("limit", 0) or reg.get("capacity", 0)

        items.append({
            "external_id": ext,
            "name": name,
            "date": dt,
            "tickets_sold": sold,
            "tickets_total": total,
            "url": ev.get("url") or ev.get("site_url") or f"{TIMEPAD_API_URL}/events/{ext}",
            "source": SourceEnum.TIMEPAD,
        })

    return items
