from __future__ import annotations

from datetime import datetime, timezone, date
from typing import List, Optional, Any, Dict
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
    """Return auth string in format required by CRM-API.

    LOGIN:SHA1( MD5(PASSWORD).upper() + TIMESTAMP ).upper():TIMESTAMP
    """
    if YANDEX_LOGIN is None or YANDEX_PASSWORD is None:
        raise RuntimeError("YANDEX_API_LOGIN / PASSWORD are not set in .env")

    ts = str(int(time.time()))
    md5 = hashlib.md5(YANDEX_PASSWORD.encode("utf-8")).hexdigest().upper()
    sha1 = hashlib.sha1(f"{md5}{ts}".encode("utf-8")).hexdigest().upper()
    return f"{YANDEX_LOGIN}:{sha1}:{ts}"


async def _yandex_call(action: str, **extra: Any) -> Dict[str, Any]:
    """Low-level wrapper around CRM-API.

    * **GET** request (the only allowed method)
    * All parameters (action, auth, city_id, format, etc.) are sent **ONLY**
      in the query string; body must be empty.
    * Response is JSON with mandatory ``status`` field.
    """
    params: Dict[str, Any] = {
        "action": action,
        "auth": _yandex_auth(),
        "format": "json",
        **extra,
    }
    # фильтруем по городу, без этого API выдаёт ошибку
    params["city_id"] = YANDEX_CITY_ID

    url = YANDEX_API_URL.rstrip("/") + "/"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, ssl=False) as resp:
            raw = await resp.text()

    try:
        data = json.loads(raw)
    except ValueError:
        raise RuntimeError(f"Yandex returned non-JSON ({resp.status}): {raw[:150]}…")

    if data.get("status") != "0":
        raise RuntimeError(f"Yandex API error {action}: {data}")
    return data


def _flatten(lst):
    """crm.*.list sometimes returns nested lists — flatten them."""
    flat: List[Any] = []
    for item in lst:
        flat.extend(item if isinstance(item, list) else [item])
    return flat


async def parse_yandex() -> List[dict]:
    # 1. List events
    ev_resp = await _yandex_call("crm.event.list")
    events_raw = _flatten(ev_resp.get("result", []))
    if not events_raw:
        return []

    # 2. Tickets report
    ids = ",".join(str(e["id"]) for e in events_raw)
    rep_resp = await _yandex_call("crm.report.event", event_ids=ids)

    stats: Dict[str, dict] = {}
    for row in rep_resp.get("result", []):
        eid = str(row["event_id"])
        s = stats.setdefault(eid, {"sold": 0, "count": 0, "avail": 0})
        s["sold"] += row.get("tickets_sold", 0)
        s["count"] = max(s["count"], row.get("tickets_count", 0))
        s["avail"] = row.get("tickets_available", s["avail"])

    events: List[dict] = []
    for ev in events_raw:
        eid = str(ev["id"])
        name = ev.get("name", "").strip()
        dt = date_parser.parse(ev.get("date")).astimezone(timezone.utc).replace(tzinfo=None)

        st = stats.get(eid, {})
        sold = st.get("sold", 0)
        total = st.get("count") or st.get("avail", 0) + sold or sold

        events.append({
            "external_id": eid,
            "name": name,
            "date": dt,
            "tickets_sold": sold,
            "tickets_total": total,
            "url": f"https://afisha.yandex.ru/events/{eid}",
            "source": SourceEnum.YANDEX,
        })
    return events


# --------------------- GoStandUp ---------------------
GOSTANDUP_API_URL = os.getenv("GOSTANDUP_API_URL", "https://gostandup.ru/api/org")
GOSTANDUP_BEARER = os.getenv("GOSTANDUP_BEARER_TOKEN")
if not GOSTANDUP_BEARER:
    raise RuntimeError("GOSTANDUP_BEARER_TOKEN not set in .env")


async def parse_gostandup() -> List[dict]:
    headers = {"Authorization": f"Bearer {GOSTANDUP_BEARER}"}
    async with aiohttp.ClientSession() as s:
        async with s.get(GOSTANDUP_API_URL, headers=headers) as r:
            r.raise_for_status()
            data = await r.json()
    items: List[dict] = []
    for ev in data.get("events", []):
        t, seats, amount = ev.get("tickets", {}), ev.get("tickets", {}).get("seats", {}), ev.get("tickets", {}).get(
            "amount", {})
        if seats.get("total", 0):
            sold, total = seats["sold"], seats["total"]
        else:
            sold, total = amount.get("sold", 0), amount.get("total", 0)
        items.append({
            "external_id": str(ev["id"]),
            "name": ev.get("title", "").strip(),
            "date": date_parser.parse(ev.get("date", "")),
            "tickets_sold": sold,
            "tickets_total": total,
            "url": ev.get("link") or f"https://gostandup.ru/event/{ev['id']}",
            "source": SourceEnum.GOSTANDUP
        })
    return items


# --------------------- Timepad ---------------------
TIMEPAD_API_URL = os.getenv("TIMEPAD_API_URL", "https://api.timepad.ru/v1")
TIMEPAD_BEARER = os.getenv("TIMEPAD_BEARER_TOKEN")
TIMEPAD_ORG_ID = os.getenv("TIMEPAD_ORG_ID")
if not (TIMEPAD_BEARER and TIMEPAD_ORG_ID):
    raise RuntimeError("TIMEPAD_BEARER_TOKEN and/or TIMEPAD_ORG_ID not set in .env")


async def fetch_registration(session: aiohttp.ClientSession, event_id: str) -> dict:
    url = f"{TIMEPAD_API_URL}/events/{event_id}.json"
    params = {"fields": "registration"}
    async with session.get(url, headers={"Authorization": f"Bearer {TIMEPAD_BEARER}"}, params=params) as r:
        r.raise_for_status()
        data = await r.json()
    places = data.get("registration", {}).get("places", [])
    return places[0] if isinstance(places, list) and places else (places if not isinstance(places, list) else {})


async def parse_timepad() -> List[dict]:
    url = f"{TIMEPAD_API_URL}/events.json"
    headers = {"Authorization": f"Bearer {TIMEPAD_BEARER}"}
    params = {"organization_ids": TIMEPAD_ORG_ID, "fields": "dates,starts_at,ticket_types", "limit": 100, "skip": 0,
              "sort": "+starts_at"}
    items: List[dict] = []
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, headers=headers, params=params) as r:
            r.raise_for_status()
            data = await r.json()
        for ev in data.get("values", []):
            ext_id, name = str(ev.get("id", "")), (ev.get("name") or ev.get("title") or "").strip()
            raw = ev.get("dates") and (ev["dates"][0].get("start") or ev["dates"][0].get("date")) or ev.get("starts_at")
            if not raw: continue
            dt = date_parser.parse(raw)
            if dt.tzinfo: dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            tt = ev.get("ticket_types", [])
            if tt:
                sold = sum(t.get("sold", 0) for t in tt)
                total = sum(t.get("total", t.get("count", 0)) for t in tt)
            else:
                reg = await fetch_registration(session, ext_id)
                sold = reg.get("registered", 0) or reg.get("count", 0)
                total = reg.get("limit", 0) or reg.get("capacity", 0)
            items.append({"external_id": ext_id, "name": name, "date": dt, "tickets_sold": sold, "tickets_total": total,
                          "url": ev.get("url") or ev.get("site_url") or f"{TIMEPAD_API_URL}/events/{ext_id}",
                          "source": SourceEnum.TIMEPAD})
    return items
