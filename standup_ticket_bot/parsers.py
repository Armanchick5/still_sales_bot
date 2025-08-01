from __future__ import annotations

from datetime import datetime, timezone, date
from typing import List, Any, Dict
import time, hashlib, aiohttp, json
from urllib.parse import urlencode

from dateutil import parser as date_parser

from standup_ticket_bot.models.concert import SourceEnum
from dotenv import load_dotenv

load_dotenv()
import os

# ╔═══════════════════════════════════════════════════════════════════════╗
# ║                         YANDEX AFISHA (CRM)                           ║
# ╚═══════════════════════════════════════════════════════════════════════╝
YANDEX_API_URL = os.getenv(
    "YANDEX_API_URL",
    "https://api.tickets.yandex.net/api/crm/"
)

YANDEX_LOGIN = os.getenv("YANDEX_API_LOGIN")
YANDEX_PASSWORD = os.getenv("YANDEX_API_PASSWORD")
YANDEX_CITY_ID = int(os.getenv("YANDEX_CITY_ID", "34348482"))


def _yandex_auth() -> str:
    if YANDEX_LOGIN is None or YANDEX_PASSWORD is None:
        raise RuntimeError("YANDEX_API_LOGIN / PASSWORD are not set in .env")
    ts = str(int(time.time()))
    pwd_md5 = hashlib.md5(YANDEX_PASSWORD.encode()).hexdigest().upper()
    sha1 = hashlib.sha1(f"{pwd_md5}{ts}".encode()).hexdigest().upper()
    return f"{YANDEX_LOGIN}:{sha1}:{ts}"


async def _yandex_call(action: str, **extra: Any) -> Dict[str, Any]:
    params: Dict[str, Any] = {
        "action": action,
        "auth": _yandex_auth(),
        "format": "json",
        **extra,
    }
    params["city_id"] = YANDEX_CITY_ID
    url = YANDEX_API_URL.rstrip("/") + "/"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, ssl=False) as resp:
            raw = await resp.text()
    data = json.loads(raw)
    if data.get("status") != "0":
        raise RuntimeError(f"Yandex API error {action}: {data}")
    return data


def _flatten(lst: Any) -> List[Any]:
    flat: List[Any] = []
    for item in lst:
        if isinstance(item, list):
            flat.extend(item)
        else:
            flat.append(item)
    return flat


async def parse_yandex() -> List[dict]:
    # Используем crm.activity.list для полного списка мероприятий
    resp = await _yandex_call("crm.activity.list")
    activities = resp.get("result", [])
    if not activities:
        return []

    # Собираем статистику по событиям
    ids = ",".join(str(act["id"]) for act in activities)
    rep = await _yandex_call("crm.report.event", event_ids=ids)
    stats: Dict[str, dict] = {str(r["event_id"]): r for r in rep.get("result", [])}

    events: List[dict] = []
    for act in activities:
        eid = str(act["id"])
        st = stats.get(eid, {})
        sold = st.get("tickets_sold", 0)
        total = st.get("tickets_count") or st.get("tickets_available", 0) or sold
        # event_date содержит дату и время
        dt = date_parser.parse(act.get("event_date")).astimezone(timezone.utc).replace(tzinfo=None)

        events.append({
            "external_id": eid,
            "name": act.get("name", "").strip(),
            "date": dt,
            "tickets_sold": sold,
            "tickets_total": total,
            "url": f"https://afisha.yandex.ru/events/{eid}",
            "source": SourceEnum.YANDEX,
        })
    return events


# -------------------------------------------------------------------
# GoStandUp
# -------------------------------------------------------------------
GOSTANDUP_API_URL = os.getenv("GOSTANDUP_API_URL", "https://gostandup.ru/api/org")
GOSTANDUP_BEARER = os.getenv("GOSTANDUP_BEARER_TOKEN")
if not GOSTANDUP_BEARER: raise RuntimeError("GOSTANDUP_BEARER_TOKEN not set in .env")


async def parse_gostandup() -> List[dict]:
    headers = {"Authorization": f"Bearer {GOSTANDUP_BEARER}"}
    async with aiohttp.ClientSession() as session:
        async with session.get(GOSTANDUP_API_URL, headers=headers) as resp:
            resp.raise_for_status();
            data = await resp.json()
    items: List[dict] = []
    for ev in data.get("events", []):
        t = ev.get("tickets", {});
        seats = t.get("seats", {});
        amt = t.get("amount", {})
        sold = seats.get("sold") if seats.get("total") else amt.get("sold", 0)
        total = seats.get("total") or amt.get("total", 0)
        items.append({
            "external_id": str(ev["id"]),
            "name": ev.get("title", "").strip(),
            "date": date_parser.parse(ev.get("date", "")),
            "tickets_sold": sold, "tickets_total": total,
            "url": ev.get("link") or f"https://gostandup.ru/event/{ev['id']}",
            "source": SourceEnum.GOSTANDUP
        })
    return items


# -------------------------------------------------------------------
# Timepad
# -------------------------------------------------------------------
TIMEPAD_API_URL = os.getenv("TIMEPAD_API_URL", "https://api.timepad.ru/v1")
TIMEPAD_BEARER = os.getenv("TIMEPAD_BEARER_TOKEN")
TIMEPAD_ORG_ID = os.getenv("TIMEPAD_ORG_ID")
if not (TIMEPAD_BEARER and TIMEPAD_ORG_ID): raise RuntimeError("TIMEPAD creds missing")


async def fetch_registration(session: aiohttp.ClientSession, event_id: str) -> dict:
    url = f"{TIMEPAD_API_URL}/events/{event_id}.json";
    params = {"fields": "registration"}
    async with session.get(url, headers={"Authorization": f"Bearer {TIMEPAD_BEARER}"}, params=params) as resp:
        resp.raise_for_status();
        data = await resp.json()
    places = data.get("registration", {}).get("places", [])
    return places[0] if isinstance(places, list) and places else places or {}


async def parse_timepad() -> List[dict]:
    url = f"{TIMEPAD_API_URL}/events.json";
    headers = {"Authorization": f"Bearer {TIMEPAD_BEARER}"}
    params = {"organization_ids": TIMEPAD_ORG_ID, "fields": "dates,starts_at,ticket_types", "limit": 100, "skip": 0,
              "sort": "+starts_at"}
    items: List[dict] = []
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
        async with session.get(url, headers=headers, params=params) as resp:
            resp.raise_for_status();
            data = await resp.json()
        for ev in data.get("values", []):
            ext = str(ev.get("id"));
            name = (ev.get("name") or ev.get("title") or "").strip()
            ds = ev.get("dates");
            raw = ds and (ds[0].get("start") or ds[0].get("date")) or ev.get("starts_at")
            if not raw: continue
            dt = date_parser.parse(raw);
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt
            tt = ev.get("ticket_types", [])
            if tt:
                sold = sum(t.get("sold", 0) for t in tt); total = sum(t.get("total", t.get("count", 0)) for t in tt)
            else:
                reg = await fetch_registration(session, ext); sold = reg.get("registered", 0) or reg.get("count",
                                                                                                         0); total = reg.get(
                    "limit", 0) or reg.get("capacity", 0)
            items.append({"external_id": ext, "name": name, "date": dt, "tickets_sold": sold, "tickets_total": total,
                          "url": ev.get("url") or ev.get("site_url") or f"{TIMEPAD_API_URL}/events/{ext}",
                          "source": SourceEnum.TIMEPAD})
    return items
