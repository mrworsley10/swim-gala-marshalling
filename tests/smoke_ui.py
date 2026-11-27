"""Runs app.py against a stand-in for Streamlit and an in-memory database, to catch crashes. Not a substitute for opening the real app.
   python3 tests/smoke_ui.py"""
import sys, os, types
from unittest.mock import MagicMock
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, R); sys.path.insert(0, os.path.join(R, "tests"))
import marshal_core as mc
from fakedb import FakeDB

class SS(dict):
    __getattr__ = dict.get
    def __setattr__(s, k, v): s[k] = v

def run(db, query, press=(), fragments=True, text=None):
    st = MagicMock(); st.session_state = SS(); st.query_params = dict(query); st.secrets = {"SUPABASE_URL": "u", "SUPABASE_KEY": "k"}
    st.context.headers = {"Host": "x.streamlit.app"}
    st.cache_resource = lambda f: f
    st.cache_data = lambda **k: (lambda f: f)
    st.query_params = type("QP", (dict,), {"clear": lambda s: dict.clear(s)})(query)
    st.columns.side_effect = lambda n: [MagicMock() for _ in range(n if isinstance(n, int) else len(n))]
    st.tabs.side_effect = lambda labels: [MagicMock() for _ in labels]
    st.selectbox.side_effect = lambda label, opts, index=0, **k: opts[index]
    st.radio.side_effect = lambda label, opts, **k: opts[0]
    st.text_input.side_effect = lambda label, **k: (text or {}).get(k.get("key"), k.get("value", ""))
    st.checkbox.return_value = False
    clicked = []
    def button(label, key=None, on_click=None, args=(), **k):
        if key in press and not k.get('disabled'):
            clicked.append(key)
            if on_click: on_click(*args)
            return True
        return False
    st.button.side_effect = button
    if not fragments: del st.fragment
    else:
        st.fragment = lambda **k: (lambda f: f)
    class RerunSignal(Exception): pass
    st.rerun.side_effect = RerunSignal
    sb = MagicMock(); sb.create_client = lambda u, k: db
    sys.modules.update({"streamlit": st, "supabase": sb})
    sys.modules.pop("app", None)
    try:
        import app  # noqa
    except RerunSignal: pass
    return st, clicked

def ent(club, s, name, ev, heat, lane): return {"club": club, "session": s, "swimmer": name, "age": "12", "event": ev, "heat": heat, "lane": lane, "entry": "30.00"}
E1, E2 = "Event 101 Mixed 11 Yrs/Over 50m Freestyle", "Event 102 Mixed 11 Yrs/Over 100m Freestyle"
df = mc.tidy([ent("Warrington W", 1, "Ann A", E1, 1, 1), ent("Chester D", 1, "Bob B", E1, 1, 2), ent("Wigan W", 1, "Cy C", E1, 2, 1), ent("Warrington W", 1, "Di D", E2, 1, 3)])
db = FakeDB(); pin = mc.create_room(db, df, "Smoke Gala", 3)

st, _ = run(db, {}); print("home ok; errors:", [c.args for c in st.error.call_args_list])
st, _ = run(db, {"room": pin, "station": "1"}); print("station 1 ok; titles:", [c.args[0] for c in st.title.call_args_list])
for sec in ("1", "2", "3", "overview"):
    st, _ = run(db, {"room": pin, "station": sec}); assert not st.error.call_args_list, (sec, st.error.call_args_list)
# tick the first heat at station 1 via the real button callback
st, clicked = run(db, {"room": pin, "station": "1"}, press={"t_1_101_1_1"}); assert clicked == ["t_1_101_1_1"], clicked
assert mc.load_ticks(db, pin) == {(1, 101, 1): {1}}, mc.load_ticks(db, pin)
st, clicked = run(db, {"room": pin, "station": "2"}); 
r, w, d = mc.station_lists(mc.heat_keys(mc.load_swims(db, pin)), mc.load_ticks(db, pin), 2, 3); assert len(r) == 1
st, clicked = run(db, {"room": pin, "station": "2"}, press={"t_1_101_1_2"}); assert mc.load_ticks(db, pin)[(1, 101, 1)] == {1, 2}
st, clicked = run(db, {"room": pin, "station": "2"}, press={"u_1_101_1_2"}); assert mc.load_ticks(db, pin)[(1, 101, 1)] == {1}
# without fragment support the page still renders
st, _ = run(db, {"room": pin, "station": "1"}, fragments=False); assert not st.error.call_args_list
# unknown room
st, _ = run(db, {"room": "00000"}); print("bad room errors:", [c.args[0] for c in st.error.call_args_list])
# organiser tools: only on the Overview, and locked until the PIN is typed
st, _ = run(db, {"room": pin, "station": "1"}); assert "Organiser tools (careful)" not in [c.args[0] for c in st.expander.call_args_list if c.args]
st, _ = run(db, {"room": pin, "station": "overview"}); assert "Organiser tools (careful)" in [c.args[0] for c in st.expander.call_args_list if c.args]
st, c = run(db, {"room": pin, "station": "overview"}, press={"del_btn"}); assert c == [] and mc.load_room(db, pin)   # locked: nothing happens
st, c = run(db, {"room": pin, "station": "overview"}, press={"rst_btn"}, text={"org_pin": "99999"}); assert c == [] and mc.load_ticks(db, pin)
st, c = run(db, {"room": pin, "station": "overview"}, press={"rst_btn"}, text={"org_pin": pin}); assert c == ["rst_btn"] and mc.load_ticks(db, pin) == {}
st, c = run(db, {"room": pin, "station": "overview"}, press={"del_btn"}, text={"org_pin": pin}); assert mc.load_room(db, pin) is None
print("ui smoke passed")

# --- instant taps: the tap shows at once from this phone's own copy, and still reaches the database ---
db = FakeDB(); pin = mc.create_room(db, df, "Instant Gala", 3)
st, c = run(db, {"room": pin, "station": "1"}, press={"t_1_101_1_1"})
assert st.session_state["mk_ot"] == {((1, 101, 1), 1): True}, st.session_state.get("mk_ot")
for f in st.session_state["mk_futs"]: f.result(timeout=5)
assert mc.load_ticks(db, pin) == {(1, 101, 1): {1}}
assert not st.session_state["mk_failed"]
print("instant taps ok")
