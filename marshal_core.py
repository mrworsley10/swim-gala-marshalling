"""Marshalling app: reading start lists (every club) and saving / loading the shared room.
No Streamlit in here, so it can be tested on its own. The database is passed in (a Supabase client)."""
import io
import random
import re
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
import urllib3
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------------------------
# READING A START LIST (same readers as the Swim Gala Hub, but they keep every club)
# ---------------------------------------------------------------------------------------------
_GENERIC_MEET_WORDS = ("sportsystems", "results service", "live results", "services", "start list", "session", "heat", "pdf", "results", "welcome", "index", "menu", "untitled")


def fetch_url_content(url):
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9,en-US;q=0.8",
    }
    response = requests.get(url, headers=headers, timeout=20, verify=False)
    response.raise_for_status()
    return response


def _good_meet_name(txt):
    t = re.sub(r"\s+", " ", str(txt or "")).strip()
    if len(t) < 4 or len(t) > 80:
        return None
    low = t.lower()
    if any(re.search(r"\b" + re.escape(w) + r"s?\b", low) for w in _GENERIC_MEET_WORDS):
        return None
    if re.fullmatch(r"[\d\W_]+", t):
        return None
    return t


def extract_meet_name_from_soup(soup):
    if soup.title:
        good = _good_meet_name(soup.title.get_text(strip=True))
        if good:
            return good
    for tag in soup.find_all(["h1", "h2", "h3", "h4", "b", "strong", "font", "caption", "th"], limit=40):
        good = _good_meet_name(tag.get_text(" ", strip=True))
        if good:
            return good
    return None


def is_valid_swimmer_name(name):
    if not name or len(name) < 2:
        return False
    if not re.search(r"[a-zA-Z]", name):
        return False
    blocked = {"name", "swimmer", "aad", "lane", "comp.no", "comp no", "comp", "club", "event", "heat", "entry", "time", "place", "pos"}
    if name.lower().strip() in blocked:
        return False
    return True


def get_event_num(event_str):
    m = re.search(r"Event\s+(\d+)", str(event_str), re.IGNORECASE)
    return int(m.group(1)) if m else 9999


def infer_session_number(event_str, current_session=1):
    e_num = get_event_num(event_str)
    if e_num != 9999 and e_num >= 100:
        return e_num // 100
    return current_session


def _entry(club, session, name, age, event, heat, lane, entry_time):
    return {"club": club, "session": session, "swimmer": name, "age": age, "event": event, "heat": heat, "lane": lane, "entry": entry_time}


def parse_html_soup(soup):
    """One SportSystems start-list page: every row of every club."""
    entries = []
    current_event, current_heat, current_session = None, "1", 1
    for elem in soup.find_all(["h1", "h2", "h3", "h4", "h5", "p", "div", "tr"]):
        text = elem.get_text(strip=True)
        if not text:
            continue
        session_match = re.search(r"Session\s+(\d+)", text, re.IGNORECASE)
        if session_match:
            current_session = int(session_match.group(1))
        event_match = re.search(r"(Event\s+\d+.*?)(?=\s+Heat|\n|$)", text, re.IGNORECASE)
        if event_match and elem.name in ["h1", "h2", "h3", "h4", "h5", "p", "div"]:
            current_event = event_match.group(1).strip()
        heat_match = re.search(r"Heat(?:\s+Number\s*-\s*|\s+)(\d+)", text, re.IGNORECASE)
        if heat_match and elem.name in ["h1", "h2", "h3", "h4", "h5", "p", "div", "tr"]:
            current_heat = heat_match.group(1)
        if elem.name == "tr" and current_event is not None:
            cells = [td.get_text(strip=True) for td in elem.find_all(["td", "th"])]
            if not cells:
                continue
            lane_str = cells[0].strip()
            if not lane_str.isdigit():
                continue
            entry_time = "N/A"
            for i in range(len(cells) - 1, 0, -1):
                val = cells[i].strip()
                if not val:
                    continue
                if re.match(r"^[\d\:\.]+$", val) or val.upper() in ["NT", "S/T", "NONE"]:
                    entry_time = val
                    break
            name, age, name_i = "", "", 0
            for i in range(1, len(cells)):
                val = cells[i].strip()
                if not val:
                    continue
                if not name and is_valid_swimmer_name(val):
                    name = val.title()
                    name_i = i
                elif name and not age and val.isdigit() and 7 <= int(val) <= 99:
                    age = val
            club = ""
            for j in range(name_i + 1, len(cells)) if name else []:
                v = cells[j].strip()
                if not v or v.isdigit() or re.match(r"^[\d:\.]+$", v) or v.upper() in ("NT", "S/T", "NONE", "N/A"):
                    continue
                club = v
                break
            if name:
                entries.append(_entry(club, infer_session_number(current_event, current_session), name, age, current_event,
                                      int(current_heat) if current_heat.isdigit() else current_heat, int(lane_str), entry_time))
    return entries


MC_ROW = re.compile(r"^(?:H(\d+)\s+)?L(\d+)\s+\((\d+)\)\s+(.+?)(?:\s*(S[BM]?\d{1,2}))?\s+(\d{1,2})\s+(.+?)\s+(\d+:\d{2}\.\d{2}|\d{1,3}\.\d{2}|NT|S/T)?\s*$")
MC_START = re.compile(r"^(?:H\d+\s+)?L\d+\s+\(\d+\)\s")


def pdf_to_lines(pdf):
    """Text lines from a PDF. Meet Centre start lists put two columns of heats on each page, so those pages are read
    left column then right column."""
    lines = []
    for page in pdf.pages:
        words = page.extract_words()
        half = page.width / 2
        lanes = [w for w in words if re.fullmatch(r"L\d", w["text"])]
        if any(w["x0"] < half for w in lanes) and any(w["x0"] > half for w in lanes):
            tops = [w["top"] for w in words if re.fullmatch(r"Event|H\d+", w["text"])]
            y = max(min(tops) - 1, 1) if tops else 1
            for box in ((0, 0, page.width, y), (0, y, half, page.height), (half, y, page.width, page.height)):
                t = page.crop(box).extract_text()
                if t:
                    lines.extend(t.split("\n"))
        else:
            t = page.extract_text()
            if t:
                lines.extend(t.split("\n"))
    return lines


def parse_meet_centre_lines(lines):
    entries = []
    current_event, current_heat, current_session = None, "1", 1
    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue
        sm = re.search(r"Session\s+(\d+)", line_str, re.IGNORECASE)
        if sm:
            current_session = int(sm.group(1))
        if re.match(r"Event\s+\d+", line_str, re.IGNORECASE):
            current_event = line_str
            continue
        m = MC_ROW.match(line_str)
        if not m or current_event is None:
            continue
        heat, lane, _seed, name, _cls, age, club, entry = m.groups()
        if heat:
            current_heat = heat
        if not is_valid_swimmer_name(name):
            continue
        entries.append(_entry(club.strip(), infer_session_number(current_event, current_session), name.strip().title(), age,
                              current_event, int(current_heat), int(lane), entry if entry else "N/A"))
    return entries


def read_pdf_files(files):
    """Meet Centre start-list PDFs (one or several). Returns the entries; raises ValueError if nothing could be read."""
    import pdfplumber
    out = []
    for f in files:
        f.seek(0)
        with pdfplumber.open(io.BytesIO(f.read())) as pdf:
            lines = pdf_to_lines(pdf)
        if any(MC_START.match(l.strip()) for l in lines):
            out.extend(parse_meet_centre_lines(lines))
    if not out:
        raise ValueError("No swimmers found. Only Meet Centre start-list PDFs are supported here. For SportSystems use the link instead.")
    return out


def read_url(url):
    """A SportSystems start-list link (and the pages it links to). Returns (entries, gala name)."""
    entries, visited, pages = [], {url}, [url]
    soup = BeautifulSoup(fetch_url_content(url).text, "html.parser")
    name = extract_meet_name_from_soup(soup) or ""
    for frame in soup.find_all(["frame", "iframe"]):
        if frame.get("src"):
            pages.append(urljoin(url, frame.get("src")))
    links = []
    for p in pages:
        try:
            p_soup = BeautifulSoup(fetch_url_content(p).text, "html.parser")
            if not name:
                name = extract_meet_name_from_soup(p_soup) or ""
            entries.extend(parse_html_soup(p_soup))
            for a in p_soup.find_all("a", href=True):
                full = urljoin(p, a["href"])
                if urlparse(full).netloc == urlparse(url).netloc and full not in visited and full.lower().endswith((".htm", ".html")):
                    links.append(full)
                    visited.add(full)
        except Exception:
            continue
    for link in links:
        try:
            entries.extend(parse_html_soup(BeautifulSoup(fetch_url_content(link).text, "html.parser")))
        except Exception:
            continue
    if not entries:
        raise ValueError("Could not find start-list tables in that link.")
    return entries, name


def tidy(entries):
    """Entries -> one row per swim: session, event_no, event, heat, lane, swimmer, club, age, entry. A swim read twice is kept once,
    and each event keeps one name. Rows without a heat and lane are dropped."""
    df = pd.DataFrame(entries)
    cols = ["session", "event_no", "event", "heat", "lane", "swimmer", "club", "age", "entry"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    df["event_no"] = df["event"].map(get_event_num)
    df["heat"] = pd.to_numeric(df["heat"], errors="coerce")
    df["lane"] = pd.to_numeric(df["lane"], errors="coerce")
    df = df.dropna(subset=["heat", "lane"])
    df = df[df["event_no"] != 9999].copy()
    df["heat"] = df["heat"].astype(int)
    df["lane"] = df["lane"].astype(int)
    df["session"] = pd.to_numeric(df["session"], errors="coerce").fillna(1).astype(int)
    first = {}
    for en, ev in zip(df["event_no"], df["event"]):
        first.setdefault(en, ev)
    df["event"] = df["event_no"].map(first)
    df["club"] = df["club"].fillna("").astype(str).str.strip()
    df = df.drop_duplicates(subset=["session", "event_no", "heat", "lane", "swimmer"])
    return df.sort_values(["session", "event_no", "heat", "lane"]).reset_index(drop=True)[cols]


def event_title(event):
    """'Event 102 Mixed 11 Yrs/Over 50m Freestyle' -> '102 · Mixed 11 Yrs/Over 50m Freestyle'."""
    m = re.match(r"\s*Event\s+(\d+)\s*(.*)", str(event), re.IGNORECASE)
    return f"{m.group(1)} · {m.group(2).strip(' -')}" if m else str(event)


def summary(df):
    return {"swims": len(df), "swimmers": df["swimmer"].nunique() if len(df) else 0, "clubs": df["club"].nunique() if len(df) else 0,
            "events": df["event_no"].nunique() if len(df) else 0, "heats": len(df.groupby(["session", "event_no", "heat"])) if len(df) else 0,
            "sessions": sorted(df["session"].unique().tolist()) if len(df) else []}


# ---------------------------------------------------------------------------------------------
# THE SHARED ROOM (Supabase)
# ---------------------------------------------------------------------------------------------
PAGE = 1000


def _fetch_all(query_fn):
    """Supabase returns at most 1000 rows a call, so read in pages."""
    rows, start = [], 0
    while True:
        res = query_fn().range(start, start + PAGE - 1).execute()
        got = res.data or []
        rows.extend(got)
        if len(got) < PAGE:
            return rows
        start += PAGE


def create_room(db, df, meet, stations):
    """Save a new marshalling room and its swims. Returns the PIN."""
    pin = None
    for _ in range(30):
        cand = str(random.randint(10000, 99999))
        if not (db.table("marshal_rooms").select("room_pin").eq("room_pin", cand).execute().data or []):
            pin = cand
            break
    if pin is None:
        raise RuntimeError("Could not find a free PIN. Try again.")
    db.table("marshal_rooms").insert({"room_pin": pin, "meet_name": meet or "", "stations": int(stations)}).execute()
    recs = [{"room_pin": pin, "session": int(r.session), "event_no": int(r.event_no), "event": str(r.event), "heat": int(r.heat), "lane": int(r.lane),
             "swimmer": str(r.swimmer), "club": str(r.club), "age": str(r.age or ""), "entry": str(r.entry or "")} for r in df.itertuples()]
    try:
        for i in range(0, len(recs), 300):
            db.table("marshal_swims").insert(recs[i:i + 300]).execute()
    except Exception:
        delete_room(db, pin)
        raise
    return pin


def load_room(db, pin):
    res = db.table("marshal_rooms").select("*").eq("room_pin", str(pin)).execute()
    return (res.data or [None])[0]


def load_swims(db, pin):
    rows = _fetch_all(lambda: db.table("marshal_swims").select("session,event_no,event,heat,lane,swimmer,club,age,entry").eq("room_pin", str(pin)).order("id"))
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["session", "event_no", "event", "heat", "lane", "swimmer", "club", "age", "entry"])
    return df.sort_values(["session", "event_no", "heat", "lane"]).reset_index(drop=True)


def load_ticks(db, pin):
    """{(session, event_no, heat): {station numbers that have ticked it}}"""
    rows = _fetch_all(lambda: db.table("marshal_ticks").select("session,event_no,heat,station").eq("room_pin", str(pin)).order("id"))
    out = {}
    for r in rows:
        if int(r["session"]) == PAPER_MARK:   # a "this station is on paper" marker, not a real tick
            continue
        out.setdefault((int(r["session"]), int(r["event_no"]), int(r["heat"])), set()).add(int(r["station"]))
    return out


# A station on paper is stored as a marker row in marshal_ticks (session 0, event 0, heat 0), so no database change is needed.
PAPER_MARK = 0


def load_paper(db, pin):
    """Set of station numbers marked as 'using paper'."""
    rows = _fetch_all(lambda: db.table("marshal_ticks").select("session,station").eq("room_pin", str(pin)).eq("session", PAPER_MARK).order("id"))
    return {int(r["station"]) for r in rows}


def set_paper(db, pin, station, on):
    if on:
        db.table("marshal_ticks").upsert({"room_pin": str(pin), "session": PAPER_MARK, "event_no": 0, "heat": 0, "station": int(station)},
                                         on_conflict="room_pin,session,event_no,heat,station").execute()
    else:
        db.table("marshal_ticks").delete().eq("room_pin", str(pin)).eq("session", PAPER_MARK).eq("station", int(station)).execute()


def load_flags(db, pin):
    """{(session, event_no, heat, lane): swimmer name} for swimmers flagged missing"""
    rows = _fetch_all(lambda: db.table("marshal_flags").select("session,event_no,heat,lane,swimmer").eq("room_pin", str(pin)).order("id"))
    return {(int(r["session"]), int(r["event_no"]), int(r["heat"]), int(r["lane"])): r["swimmer"] for r in rows}


def set_tick(db, pin, heat_key, station, on):
    s, e, h = heat_key
    if on:
        db.table("marshal_ticks").upsert({"room_pin": str(pin), "session": s, "event_no": e, "heat": h, "station": int(station)},
                                         on_conflict="room_pin,session,event_no,heat,station").execute()
    else:
        db.table("marshal_ticks").delete().eq("room_pin", str(pin)).eq("session", s).eq("event_no", e).eq("heat", h).eq("station", int(station)).execute()


def set_flag(db, pin, heat_key, lane, swimmer, on):
    s, e, h = heat_key
    if on:
        db.table("marshal_flags").upsert({"room_pin": str(pin), "session": s, "event_no": e, "heat": h, "lane": int(lane), "swimmer": swimmer},
                                         on_conflict="room_pin,session,event_no,heat,lane").execute()
    else:
        db.table("marshal_flags").delete().eq("room_pin", str(pin)).eq("session", s).eq("event_no", e).eq("heat", h).eq("lane", int(lane)).execute()


def reset_ticks(db, pin):
    paper = load_paper(db, pin)
    db.table("marshal_ticks").delete().eq("room_pin", str(pin)).execute()
    for n in paper:   # which stations are on paper is a set-up choice, so it survives a clear
        set_paper(db, pin, n, True)
    db.table("marshal_flags").delete().eq("room_pin", str(pin)).execute()


def delete_room(db, pin):
    for t in ("marshal_ticks", "marshal_flags", "marshal_swims", "marshal_rooms"):
        db.table(t).delete().eq("room_pin", str(pin)).execute()


# ---------------------------------------------------------------------------------------------
# WORKING OUT WHAT EACH STATION SEES
# ---------------------------------------------------------------------------------------------
def heat_keys(swims):
    """Heats in running order."""
    if swims.empty:
        return []
    g = swims.groupby(["session", "event_no", "heat"]).size().reset_index()
    return [(int(r.session), int(r.event_no), int(r.heat)) for r in g.itertuples()]


def station_lists(keys, ticks, station, stations, paper=frozenset()):
    """For one station: (ready, on_the_way, done), each a list of heat keys in running order.
    Stations on paper are skipped: ready = ticked at the nearest app station before this one (none before it: any heat not yet done here).
    on_the_way = not ticked here and not ready yet. done = ticked here."""
    before = [n for n in range(1, station) if n not in paper]
    prev = before[-1] if before else None
    ready, way, done = [], [], []
    for k in keys:
        t = ticks.get(k, set())
        if station in t:
            done.append(k)
        elif prev is None or prev in t:
            ready.append(k)
        else:
            way.append(k)
    return ready, way, done


def overview_rows(swims, keys, ticks, flags, stations, paper=frozenset()):
    ev = swims.drop_duplicates("event_no").set_index("event_no")["event"].to_dict() if not swims.empty else {}
    rows = []
    for (s, e, h) in keys:
        t = ticks.get((s, e, h), set())
        miss = sum(1 for (fs, fe, fh, _l) in flags if (fs, fe, fh) == (s, e, h))
        row = {"Session": s, "Event": event_title(ev.get(e, f"Event {e}")), "Heat": h}
        for n in range(1, stations + 1):
            row[f"S{n}"] = "📄" if n in paper else ("✅" if n in t else "")
        row["Missing"] = miss if miss else ""
        row["_n"] = len([n for n in t if n not in paper])
        rows.append(row)
    return rows
