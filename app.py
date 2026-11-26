import streamlit as st
import pandas as pd
from html import escape
from supabase import create_client

import marshal_core as mc

st.set_page_config(page_title="Gala Marshalling", page_icon="🏁", layout="centered")

st.markdown("""
<style>
.mk-lane {width:100%; border-collapse:collapse; font-size:0.95rem; margin:0.25rem 0 0.5rem 0;}
.mk-lane td {padding:3px 6px; border-bottom:1px solid rgba(128,128,128,0.25);}
.mk-lane td.l {width:2rem; font-weight:700; text-align:center;}
.mk-lane td.c {opacity:0.7; font-size:0.8rem;}
.mk-lane tr.miss td {background:rgba(255,160,0,0.22);}
.mk-title {font-weight:700; font-size:1.05rem;}
.mk-sub {opacity:0.7; font-size:0.8rem;}
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
def heat_card(pin, hk, swims, ticks, flags, station, mode):
    """mode: 'ready' (tick button), 'way' (tick button, collapsed look) or 'done' (undo button)"""
    s, e, h = hk
    g = swims[(swims["session"] == s) & (swims["event_no"] == e) & (swims["heat"] == h)]
    if g.empty:
        return
    with st.container(border=True):
        st.markdown(f"<div class='mk-title'>{escape(mc.event_title(g['event'].iloc[0]))} · Heat {h}</div><div class='mk-sub'>Session {s}</div>", unsafe_allow_html=True)
        missing = [flags[(s, e, h, int(r.lane))] for r in g.itertuples() if (s, e, h, int(r.lane)) in flags]
        if missing:
            st.warning("Missing: " + ", ".join(missing))
        rows = ""
        for r in g.itertuples():
            cls = " class='miss'" if (s, e, h, int(r.lane)) in flags else ""
            rows += f"<tr{cls}><td class='l'>{int(r.lane)}</td><td>{escape(str(r.swimmer))}</td><td class='c'>{escape(str(r.club))}</td></tr>"
        st.markdown(f"<table class='mk-lane'>{rows}</table>", unsafe_allow_html=True)
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
    ticks, flags = mc.load_ticks(db, pin), mc.load_flags(db, pin)
    keys = mc.heat_keys(swims)
    ready, way, done = mc.station_lists(keys, ticks, station, stations)
    c1, c2, c3 = st.columns(3)
    c1.metric("Ready for you", len(ready))
    c2.metric("On the way", len(way))
    c3.metric("Done", len(done))
    st.button("🔄 Refresh", key="refresh_st", use_container_width=True)
    more = st.session_state.get("mk_more", 5)
    if not ready:
        st.info("Nothing waiting at your station right now." if keys else "No heats in this room.")
    for hk in ready[:more]:
        heat_card(pin, hk, swims, ticks, flags, station, "ready")
    if len(ready) > more:
        if st.button(f"Show {min(5, len(ready) - more)} more", key="mk_more_btn", use_container_width=True):
            st.session_state["mk_more"] = more + 5
    with st.expander("On the way to you"):
        st.caption("Heats that haven't been ticked at the station before yours. Tick one here if it arrived anyway.")
        for hk in way[:8]:
            heat_card(pin, hk, swims, ticks, flags, station, "way")
        if len(way) > 8:
            st.caption(f"…and {len(way) - 8} more later in the gala.")
    with st.expander("Done at your station"):
        for hk in list(reversed(done))[:8]:
            heat_card(pin, hk, swims, ticks, flags, station, "done")


def live_overview(pin, stations, swims):
    db = get_db()
    ticks, flags = mc.load_ticks(db, pin), mc.load_flags(db, pin)
    keys = mc.heat_keys(swims)
    rows = mc.overview_rows(swims, keys, ticks, flags, stations)
    finished = sum(1 for r in rows if r["_n"] >= stations)
    started = sum(1 for r in rows if 0 < r["_n"] < stations)
    c1, c2, c3 = st.columns(3)
    c1.metric("Heats", len(rows))
    c2.metric("In progress", started)
    c3.metric("Finished", finished)
    st.button("🔄 Refresh", key="refresh_ov", use_container_width=True)
    show = st.radio("Show", ["In progress", "Not started", "Finished", "All"], horizontal=True, key="ov_filter")
    if show == "In progress":
        rows = [r for r in rows if 0 < r["_n"] < stations]
    elif show == "Not started":
        rows = [r for r in rows if r["_n"] == 0]
    elif show == "Finished":
        rows = [r for r in rows if r["_n"] >= stations]
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
    st.title("🏁 " + (room.get("meet_name") or "Gala Marshalling"))
    st.caption(f"Room {pin} · {stations} stations")
    swims = cached_swims(pin, db)
    opts = [f"Station {i}" for i in range(1, stations + 1)] + ["Overview (everyone)"]
    qp = str(st.query_params.get("station", ""))
    idx = opts.index(f"Station {qp}") if qp.isdigit() and f"Station {qp}" in opts else (len(opts) - 1 if qp == "overview" else 0)
    choice = st.selectbox("Your station", opts, index=idx, key="mk_station")
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
