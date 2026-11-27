import streamlit as st
import pandas as pd
from html import escape
from supabase import create_client

import marshal_core as mc

st.set_page_config(page_title="Gala Marshalling", page_icon="🏁", layout="centered")

st.markdown("""
<style>
.block-container {padding-top: 2.5rem; padding-bottom: 4rem;}
.mk-h1 {font-size:1.2rem; font-weight:800; line-height:1.2; margin:0.2rem 0 0;}
.mk-room {opacity:0.65; font-size:0.8rem; margin-bottom:0.4rem;}
.mk-chips {display:flex; gap:0.4rem; flex-wrap:wrap; margin:0.2rem 0 0.6rem 0;}
.mk-chips span {background:rgba(128,128,128,0.18); border-radius:999px; padding:0.2rem 0.7rem; font-size:0.85rem;}
.mk-chips b {font-size:1rem;}
.mk-card {border-left:7px solid #6b7280; border-radius:10px; padding:0.35rem 0.6rem 0.4rem 0.7rem; margin-bottom:0.4rem; background:rgba(128,128,128,0.08);}
.mk-card.ready {border-left-color:#22c55e;}
.mk-card.next {border-left-color:#22c55e; background:rgba(34,197,94,0.12);}
.mk-card.done {border-left-color:#3b82f6; opacity:0.85;}
.mk-card.miss {border-left-color:#f59e0b; background:rgba(245,158,11,0.14);}
.mk-top {display:flex; justify-content:space-between; align-items:center;}
.mk-heat {font-size:1.35rem; font-weight:800;}
.mk-tag {font-size:0.7rem; font-weight:800; letter-spacing:0.05em; padding:0.1rem 0.5rem; border-radius:999px; background:#22c55e; color:#04210f;}
.mk-tag.warn {background:#f59e0b; color:#2b1a00;}
.mk-ev {opacity:0.8; font-size:0.85rem; margin-bottom:0.15rem;}
.mk-dots {font-size:0.8rem; margin:0.1rem 0 0.35rem 0; letter-spacing:0.12rem;}
.mk-dots .on {color:#22c55e;} .mk-dots .off {opacity:0.4;} .mk-dots .you {color:#facc15; font-weight:800;}
.mk-row {display:flex; align-items:center; gap:0.6rem; padding:0.28rem 0.2rem; border-top:1px solid rgba(128,128,128,0.22);}
.mk-row.miss {background:rgba(245,158,11,0.25); border-radius:6px;}
.mk-lane {flex:0 0 2rem; height:2rem; border-radius:50%; background:rgba(128,128,128,0.3); display:flex; align-items:center; justify-content:center; font-weight:800; font-size:1rem;}
.mk-name {font-size:1.05rem; font-weight:600; line-height:1.15;}
.mk-name small {display:block; font-weight:400; opacity:0.65; font-size:0.78rem;}
.mk-time {margin-left:auto; font-size:0.9rem; font-weight:600; opacity:0.8; font-variant-numeric:tabular-nums;}
.mk-gone {margin-left:0.6rem; font-size:0.7rem; font-weight:800; color:#f59e0b;}
div.stButton > button {min-height:3rem; font-size:1.05rem; font-weight:700;}
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def get_db():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


@st.cache_data(ttl=600, show_spinner=False)
def cached_swims(pin, _db):
    return mc.load_swims(_db, pin)


def _toast(msg):
    try:
        st.toast(msg, icon="⚠️")
    except Exception:
        pass


def do_tick(pin, hk, station, on):
    try:
        mc.set_tick(get_db(), pin, hk, station, on)
    except Exception as e:
        _toast(f"Couldn't save that tick: {e}")


def do_flag(pin, hk, lane, swimmer, key):
    try:
        mc.set_flag(get_db(), pin, hk, lane, swimmer, bool(st.session_state.get(key)))
    except Exception as e:
        _toast(f"Couldn't save that flag: {e}")


# ---------------------------------------------------------------------------------------------
# HOME: join a room, or set one up
# ---------------------------------------------------------------------------------------------
def page_home():
    st.title("🏁 Gala Marshalling")
    st.caption("A tick sheet for the marshals. Every club, every heat, every station, on your own phone.")
    t_join, t_setup = st.tabs(["Join a gala", "Set up a gala"])
    with t_join:
        pin = st.text_input("Room PIN", max_chars=5, key="join_pin")
        if st.button("Join", type="primary", use_container_width=True, key="join_btn"):
            if pin and pin.strip().isdigit() and mc.load_room(get_db(), pin.strip()):
                st.query_params["room"] = pin.strip()
                st.rerun()
            else:
                st.error("No room with that PIN.")
    with t_setup:
        setup_form()


def setup_form():
    st.write("One person does this, once. Load the **start list for the whole gala** (every club), then choose how many stations there are.")
    method = st.radio("Start list from", ["SportSystems link", "Meet Centre PDF"], horizontal=True, key="mk_method")
    if method == "SportSystems link":
        url = st.text_input("SportSystems start list link", key="mk_url")
        if url and st.button("Read the link", key="mk_read_url"):
            with st.spinner("Reading the link..."):
                try:
                    entries, name = mc.read_url(url.strip())
                    st.session_state["mk_df"] = mc.tidy(entries)
                    st.session_state["mk_meet"] = name
                except Exception as e:
                    st.session_state.pop("mk_df", None)
                    st.error(f"Couldn't read that link: {e}")
    else:
        files = st.file_uploader("Start list PDF(s)", type=["pdf"], accept_multiple_files=True, key="mk_pdf")
        if files and st.button("Read the PDF", key="mk_read_pdf"):
            with st.spinner("Reading the PDF..."):
                try:
                    st.session_state["mk_df"] = mc.tidy(mc.read_pdf_files(files))
                    st.session_state["mk_meet"] = ""
                except Exception as e:
                    st.session_state.pop("mk_df", None)
                    st.error(str(e))

    df = st.session_state.get("mk_df")
    if df is None:
        return
    if df.empty:
        st.warning("Nothing was read from that start list.")
        return
    s = mc.summary(df)
    st.success(f"Read {s['swims']} swims · {s['swimmers']} swimmers · {s['clubs']} clubs · {s['events']} events · {s['heats']} heats · session(s) {', '.join(str(x) for x in s['sessions'])}")
    if s["clubs"] < 2:
        st.warning("Only one club was found. Check this is the start list for the whole gala.")
    meet = st.text_input("Gala name", value=st.session_state.get("mk_meet", ""), key="mk_meet_in")
    stations = st.number_input("How many marshalling stations?", min_value=1, max_value=10, value=5, step=1, key="mk_stations")
    if st.button("Create marshalling room", type="primary", use_container_width=True, key="mk_create"):
        with st.spinner("Creating the room..."):
            try:
                pin = mc.create_room(get_db(), df, meet, int(stations))
                st.session_state["mk_new_pin"] = pin
                st.session_state.pop("mk_df", None)
                st.rerun()
            except Exception as e:
                st.error(f"Couldn't create the room: {e}")


def show_new_room():
    pin = st.session_state.get("mk_new_pin")
    if not pin:
        return False
    host = ""
    try:
        host = st.context.headers.get("Host", "")
    except Exception:
        pass
    link = f"https://{host}/?room={pin}" if host else f"?room={pin}"
    st.title("🏁 Room ready")
    st.success(f"Room PIN: {pin}")
    st.write("Send this link to every marshal. Each person opens it on their own phone and picks their station.")
    st.code(link)
    if st.button("Open the room", type="primary", use_container_width=True, key="open_new"):
        st.query_params["room"] = pin
        st.session_state.pop("mk_new_pin", None)
        st.rerun()
    return True


# ---------------------------------------------------------------------------------------------
# A ROOM: station view and overview
# ---------------------------------------------------------------------------------------------
def dots_html(ticked, stations, station, paper=frozenset()):
    out = []
    for n in range(1, stations + 1):
        if n in paper: out.append("<span class='off'>▫</span>")
        elif n in ticked: out.append("<span class='on'>●</span>")
        elif n == station: out.append("<span class='you'>◎</span>")
        else: out.append("<span class='off'>○</span>")
    return "".join(out)


def _entry_txt(v):
    v = str(v or "").strip()
    return "" if v.upper() in ("", "N/A", "NT", "NONE", "NAN") else v


def heat_card(pin, hk, swims, ticks, flags, station, mode, stations, is_next=False, paper=frozenset()):
    """mode: 'ready' (tick button), 'way' (tick button) or 'done' (undo button)"""
    s, e, h = hk
    g = swims[(swims["session"] == s) & (swims["event_no"] == e) & (swims["heat"] == h)]
    if g.empty:
        return
    missing = [flags[(s, e, h, int(r.lane))] for r in g.itertuples() if (s, e, h, int(r.lane)) in flags]
    cls = "miss" if missing else ("done" if mode == "done" else ("next" if is_next else ("ready" if mode == "ready" else "")))
    tag = "<span class='mk-tag warn'>MISSING</span>" if missing else ("<span class='mk-tag'>NEXT UP</span>" if is_next else "")
    rows = ""
    for r in g.itertuples():
        gone = (s, e, h, int(r.lane)) in flags
        rows += (f"<div class='mk-row{' miss' if gone else ''}'><div class='mk-lane'>{int(r.lane)}</div>"
                 f"<div class='mk-name'>{escape(str(r.swimmer))}<small>{escape(str(r.club))}</small></div>"
                 f"<div class='mk-time'>{escape(_entry_txt(r.entry))}</div>"
                 f"{'<div class=mk-gone>MISSING</div>' if gone else ''}</div>")
    head = (f"<div class='mk-card {cls}'><div class='mk-top'><span class='mk-heat'>Heat {h}</span>{tag}</div>"
            f"<div class='mk-ev'>{escape(mc.event_title(g['event'].iloc[0]))} · Session {s}</div>"
            f"<div class='mk-dots'>{dots_html(ticks.get(hk, set()), stations, station, paper)}</div>{rows}</div>")
    with st.container():
        st.markdown(head, unsafe_allow_html=True)
        if mode == "done":
            st.button("↩ Undo", key=f"u_{s}_{e}_{h}_{station}", on_click=do_tick, args=(pin, hk, station, False), use_container_width=True)
        else:
            st.button("✅ Lined up, all here", key=f"t_{s}_{e}_{h}_{station}", on_click=do_tick, args=(pin, hk, station, True),
                      use_container_width=True, type="primary" if mode == "ready" else "secondary")
        with st.expander("Flag a missing swimmer"):
            for r in g.itertuples():
                key = f"f_{s}_{e}_{h}_{int(r.lane)}"
                st.session_state[key] = (s, e, h, int(r.lane)) in flags   # follow what is saved, so a flag from another phone shows here
                st.checkbox(f"Lane {int(r.lane)} · {r.swimmer}", key=key, on_change=do_flag, args=(pin, hk, int(r.lane), str(r.swimmer), key))


def live_station(pin, station, stations, swims):
    db = get_db()
    ticks, flags, paper = mc.load_ticks(db, pin), mc.load_flags(db, pin), mc.load_paper(db, pin)
    keys = mc.heat_keys(swims)
    if station in paper:
        st.info("📄 This station is marked as using paper, so the app skips it. Tick heats here only if you want to use the app after all (the organiser can switch paper off on the Overview screen).")
    ready, way, done = mc.station_lists(keys, ticks, station, stations, paper)
    st.markdown(f"<div class='mk-chips'><span>Ready <b>{len(ready)}</b></span><span>On the way <b>{len(way)}</b></span><span>Done <b>{len(done)}</b></span></div>", unsafe_allow_html=True)
    more = st.session_state.get("mk_more", 5)
    if not ready:
        st.info("Nothing waiting at your station right now." if keys else "No heats in this room.")
    for i, hk in enumerate(ready[:more]):
        heat_card(pin, hk, swims, ticks, flags, station, "ready", stations, is_next=(i == 0), paper=paper)
    if len(ready) > more:
        if st.button(f"Show {min(5, len(ready) - more)} more", key="mk_more_btn", use_container_width=True):
            st.session_state["mk_more"] = more + 5
    with st.expander("On the way to you"):
        st.caption("Heats that haven't been ticked at the station before yours. Tick one here if it arrived anyway.")
        for hk in way[:8]:
            heat_card(pin, hk, swims, ticks, flags, station, "way", stations, paper=paper)
        if len(way) > 8:
            st.caption(f"…and {len(way) - 8} more later in the gala.")
    with st.expander("Done at your station"):
        for hk in list(reversed(done))[:8]:
            heat_card(pin, hk, swims, ticks, flags, station, "done", stations, paper=paper)
    st.button("🔄 Refresh now", key="refresh_st", use_container_width=True)


def live_overview(pin, stations, swims):
    db = get_db()
    ticks, flags, paper = mc.load_ticks(db, pin), mc.load_flags(db, pin), mc.load_paper(db, pin)
    keys = mc.heat_keys(swims)
    rows = mc.overview_rows(swims, keys, ticks, flags, stations, paper)
    need = max(1, stations - len(paper))   # stations that use the app
    finished = sum(1 for r in rows if r["_n"] >= need)
    started = sum(1 for r in rows if 0 < r["_n"] < need)
    st.markdown(f"<div class='mk-chips'><span>Heats <b>{len(rows)}</b></span><span>In progress <b>{started}</b></span><span>Finished <b>{finished}</b></span></div>", unsafe_allow_html=True)
    st.button("🔄 Refresh", key="refresh_ov", use_container_width=True)
    show = st.radio("Show", ["In progress", "Not started", "Finished", "All"], horizontal=True, key="ov_filter")
    if show == "In progress":
        rows = [r for r in rows if 0 < r["_n"] < need]
    elif show == "Not started":
        rows = [r for r in rows if r["_n"] == 0]
    elif show == "Finished":
        rows = [r for r in rows if r["_n"] >= need]
    if flags:
        st.warning(f"{len(flags)} swimmer(s) flagged missing: " + ", ".join(sorted(set(flags.values()))[:12]))
    if rows:
        df = pd.DataFrame(rows).drop(columns=["_n"])
        st.dataframe(df, hide_index=True, use_container_width=True)
    else:
        st.info("No heats to show.")


def _auto(fn):
    """Refresh the live part every few seconds where this Streamlit version can."""
    frag = getattr(st, "fragment", None)
    if frag:
        try:
            return frag(run_every=10)(fn)
        except Exception:
            return fn
    return fn


live_station = _auto(live_station)
live_overview = _auto(live_overview)


def page_room(pin):
    db = get_db()
    room = mc.load_room(db, pin)
    if not room:
        st.error("That room doesn't exist (any more).")
        if st.button("Back", key="back_home"):
            st.query_params.clear()
            st.rerun()
        return
    stations = int(room.get("stations") or 1)
    st.markdown(f"<div class='mk-h1'>🏁 {escape(room.get('meet_name') or 'Gala Marshalling')}</div><div class='mk-room'>Room {pin} · {stations} stations</div>", unsafe_allow_html=True)
    swims = cached_swims(pin, db)
    opts = [f"Station {i}" for i in range(1, stations + 1)] + ["Overview (everyone)"]
    qp = str(st.query_params.get("station", ""))
    idx = opts.index(f"Station {qp}") if qp.isdigit() and f"Station {qp}" in opts else (len(opts) - 1 if qp == "overview" else 0)
    choice = st.selectbox("Your station", opts, index=idx, key="mk_station", label_visibility="collapsed")
    st.query_params["station"] = "overview" if choice.startswith("Overview") else choice.split()[1]
    if choice.startswith("Overview"):
        live_overview(pin, stations, swims)
        organiser_tools(pin, db)
    else:
        live_station(pin, int(choice.split()[1]), stations, swims)


def organiser_tools(pin, db):
    """Only on the Overview screen, and each action needs the room PIN typed in, so a marshal at a station can't hit it by accident."""
    with st.expander("Organiser tools (careful)"):
        st.caption("To clear the ticks or delete the room, type the room PIN first.")
        typed = st.text_input("Type the room PIN to unlock", key="org_pin", max_chars=5)
        unlocked = typed.strip() == str(pin)
        room = mc.load_room(db, pin) or {}
        n_st = int(room.get("stations") or 1)
        paper = mc.load_paper(db, pin)
        st.markdown("**Stations using paper** (the app skips these)")
        for n in range(1, n_st + 1):
            want = st.checkbox(f"Station {n} is on paper", value=(n in paper), key=f"paper_{n}_{'1' if n in paper else '0'}", disabled=not unlocked)
            if unlocked and want != (n in paper):
                mc.set_paper(db, pin, n, want)
                st.rerun()
        if st.button("Clear every tick and flag", key="rst_btn", disabled=not unlocked):
            mc.reset_ticks(db, pin)
            st.success("Cleared.")
        if st.button("Delete this whole room", key="del_btn", disabled=not unlocked):
            mc.delete_room(db, pin)
            st.query_params.clear()
            st.rerun()


pin_q = str(st.query_params.get("room", "")).strip()
if pin_q:
    page_room(pin_q)
elif not show_new_room():
    page_home()
