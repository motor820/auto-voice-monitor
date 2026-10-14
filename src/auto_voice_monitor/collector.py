"""Automotive owner-review collection; no account credentials required."""
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

API_URL = "https://koubeiipv6.app.autohome.com.cn/pc/series/list"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AutoVoiceMonitor/0.1)", "Referer": "https://k.autohome.com.cn/"}
SECTION_NAMES = {
    "最满意": "most_satisfied", "最不满意": "least_satisfied", "空间": "space",
    "驾驶感受": "driving", "续航": "range", "外观": "exterior", "内饰": "interior",
    "性价比": "value", "智能化": "intelligence",
}

def now_utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def source_url(show_id):
    # Koubeiid is NOT the URL identifier. The detail path uses showId.
    return f"https://k.autohome.com.cn/detail/view_{show_id}.html" if show_id else None

def valid_source_url(url):
    u = urlparse(url or "")
    return u.scheme == "https" and u.netloc == "k.autohome.com.cn" and u.path.startswith("/detail/view_")

def fetch_page(session, series_id, page, page_size=20):
    params = {"pm": 3, "seriesId": series_id, "pageIndex": page, "pageSize": page_size,
              "yearid": 0, "ge": 0, "seriesSummaryKey": 0, "order": 0}
    response = session.get(API_URL, params=params, headers=HEADERS, timeout=25)
    response.raise_for_status()
    payload = response.json()
    if payload.get("returncode") != 0 or not isinstance(payload.get("result", {}).get("list"), list):
        raise RuntimeError(f"unexpected API response for series {series_id}, page {page}: {payload.get('message')}")
    return payload["result"]

def fetch_sections(session, url):
    if not valid_source_url(url):
        return {}
    response = session.get(url, headers=HEADERS, timeout=25)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    sections = {}
    for block in soup.select(".kb-item"):
        title = block.find(["h1", "h3"])
        text = block.select_one("p.kb-item-msg")
        if not title or not text:
            continue
        key = next((field for label, field in SECTION_NAMES.items() if label in title.get_text(" ", strip=True)), None)
        if key:
            value = text.get_text("\n", strip=True)
            if value:
                sections[key] = value
    return sections

def normalize(item, brand, series, sections):
    review_id = str(item.get("Koubeiid") or "").strip()
    if not review_id:
        return None
    show_id = str(item.get("showId") or "").strip()
    parts = []
    for entry in item.get("contents") or []:
        body = BeautifulSoup(str(entry.get("content") or ""), "html.parser").get_text(" ", strip=True)
        if body:
            parts.append(body)
    text = "\n".join(dict.fromkeys(parts))
    for value in sections.values():
        if value not in text:
            text += ("\n" if text else "") + value
    digest = hashlib.sha256(json.dumps({"text": text, "sections": sections}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return {"source": "autohome", "source_review_id": review_id, "brand_id": brand["id"],
            "brand_name": brand["name"], "series_id": int(series["id"]), "series_name": series["name"],
            "show_id": show_id or None, "source_url": source_url(show_id),
            "published_at": item.get("posttime"), "content_hash": digest, "review_text": text,
            "sections_json": json.dumps(sections, ensure_ascii=False),
            "raw_json": json.dumps(item, ensure_ascii=False)}

def upsert(conn, row):
    now = now_utc()
    old = conn.execute("SELECT id, content_hash, source_url FROM reviews WHERE source=? AND source_review_id=? AND series_id=?",
                       (row["source"], row["source_review_id"], row["series_id"])).fetchone()
    if old:
        changed = old["content_hash"] != row["content_hash"] or old["source_url"] != row["source_url"]
        conn.execute("UPDATE reviews SET last_seen_at=?, changed_at=CASE WHEN ? THEN ? ELSE changed_at END, "
                     "show_id=?, source_url=?, published_at=?, content_hash=?, review_text=?, sections_json=?, raw_json=? "
                     "WHERE id=?", (now, int(changed), now, row["show_id"], row["source_url"], row["published_at"],
                                  row["content_hash"], row["review_text"], row["sections_json"], row["raw_json"], old["id"]))
        return "changed" if changed else "known"
    conn.execute("INSERT INTO reviews(source,source_review_id,brand_id,brand_name,series_id,series_name,show_id,source_url,"
                 "published_at,first_seen_at,last_seen_at,changed_at,content_hash,review_text,sections_json,raw_json) "
                 "VALUES(:source,:source_review_id,:brand_id,:brand_name,:series_id,:series_name,:show_id,:source_url,"
                 ":published_at,:first_seen_at,:last_seen_at,:changed_at,:content_hash,:review_text,:sections_json,:raw_json)",
                 {**row, "first_seen_at": now, "last_seen_at": now, "changed_at": now})
    return "inserted"

def sync_series(conn, session, brand, series, *, max_pages=3, full_history=False, detail_limit=20, interval=1.5):
    started = now_utc()
    cursor = conn.execute("INSERT INTO run_log(started_at,status,brand_id,series_id) VALUES(?,?,?,?)",
                          (started, "running", brand["id"], int(series["id"])))
    run_id = cursor.lastrowid
    counts = {"pages": 0, "seen": 0, "inserted": 0, "changed": 0}
    detailed = 0
    try:
        page = 1
        while page <= max_pages:
            result = fetch_page(session, int(series["id"]), page)
            items = result.get("list") or []
            counts["pages"] += 1
            if not items:
                break
            known_on_page = 0
            for item in items:
                rid = str(item.get("Koubeiid") or "").strip()
                if not rid:
                    continue
                counts["seen"] += 1
                old = conn.execute("SELECT id,sections_json FROM reviews WHERE source='autohome' AND source_review_id=? AND series_id=?",
                                   (rid, int(series["id"]))).fetchone()
                if old:
                    known_on_page += 1
                url = source_url(item.get("showId"))
                sections = {}
                if (not old or full_history) and detailed < detail_limit and url:
                    try:
                        time.sleep(interval)
                        sections = fetch_sections(session, url)
                    except (requests.RequestException, ValueError):
                        pass  # list text survives; next backfill can retry detail
                    detailed += 1
                if old:
                    sections = {**json.loads(old["sections_json"]), **sections}
                row = normalize(item, brand, series, sections)
                if row:
                    outcome = upsert(conn, row)
                    if outcome in counts:
                        counts[outcome] += 1
            conn.commit()
            if not full_history and known_on_page == len(items):
                break
            if page >= int(result.get("pagecount") or page):
                break
            page += 1
            time.sleep(interval)
        conn.execute("UPDATE run_log SET finished_at=?,status='ok',pages=?,seen=?,inserted=?,changed=? WHERE id=?",
                     (now_utc(), counts["pages"], counts["seen"], counts["inserted"], counts["changed"], run_id))
        conn.commit()
    except Exception as exc:
        conn.execute("UPDATE run_log SET finished_at=?,status='error',pages=?,seen=?,inserted=?,changed=?,error=? WHERE id=?",
                     (now_utc(), counts["pages"], counts["seen"], counts["inserted"], counts["changed"], str(exc)[:500], run_id))
        conn.commit()
        raise
    return counts
