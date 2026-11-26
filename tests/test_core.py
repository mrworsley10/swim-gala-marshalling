"""Run from the repo root:  python3 tests/test_core.py [start-list.pdf]"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import marshal_core as mc
from fakedb import FakeDB

def ent(club, s, name, ev, heat, lane): return {"club": club, "session": s, "swimmer": name, "age": "12", "event": ev, "heat": heat, "lane": lane, "entry": "30.00"}
E1, E2 = "Event 101 Mixed 11 Yrs/Over 50m Freestyle", "Event 102 Mixed 11 Yrs/Over 100m Freestyle"
entries = [ent("Warrington W", 1, "Ann A", E1, 1, 1), ent("Chester D", 1, "Bob B", E1, 1, 2), ent("Wigan W", 1, "Cy C", E1, 2, 1),
           ent("Warrington W", 1, "Ann A", E1, 1, 1),  # read twice
           ent("Warrington W", 1, "Di D", E2, 1, 3), ent("Chester D", 1, "Ed E", E2, 1, 4), ent("X", 1, "No Heat", E2, "", 5)]
df = mc.tidy(entries)
assert len(df) == 5, len(df)
s = mc.summary(df); assert (s["swims"], s["clubs"], s["heats"], s["events"]) == (5, 3, 3, 2), s
assert mc.event_title(E1) == "101 · Mixed 11 Yrs/Over 50m Freestyle"

db = FakeDB()
pin = mc.create_room(db, df, "Test Gala", 4)
assert mc.load_room(db, pin)["stations"] == 4
sw = mc.load_swims(db, pin); assert len(sw) == 5
keys = mc.heat_keys(sw); assert keys == [(1, 101, 1), (1, 101, 2), (1, 102, 1)], keys

# station 1 sees everything; station 2 sees nothing until station 1 ticks
r, w, d = mc.station_lists(keys, mc.load_ticks(db, pin), 1, 4); assert (len(r), len(w), len(d)) == (3, 0, 0)
r, w, d = mc.station_lists(keys, mc.load_ticks(db, pin), 2, 4); assert (len(r), len(w), len(d)) == (0, 3, 0)
mc.set_tick(db, pin, keys[0], 1, True); mc.set_tick(db, pin, keys[0], 1, True)   # twice: still one tick
assert len(db.tables["marshal_ticks"]) == 1
t = mc.load_ticks(db, pin)
r, w, d = mc.station_lists(keys, t, 1, 4); assert (len(r), len(d)) == (2, 1)
r, w, d = mc.station_lists(keys, t, 2, 4); assert r == [keys[0]] and len(w) == 2
mc.set_tick(db, pin, keys[0], 2, True)
r, w, d = mc.station_lists(keys, mc.load_ticks(db, pin), 2, 4); assert d == [keys[0]] and r == []
mc.set_tick(db, pin, keys[0], 2, False)
assert mc.load_ticks(db, pin)[keys[0]] == {1}

# flags
mc.set_flag(db, pin, keys[0], 2, "Bob B", True); mc.set_flag(db, pin, keys[0], 2, "Bob B", True)
fl = mc.load_flags(db, pin); assert fl == {(1, 101, 1, 2): "Bob B"}, fl
rows = mc.overview_rows(sw, keys, mc.load_ticks(db, pin), fl, 4)
assert rows[0]["S1"] == "✅" and rows[0]["S2"] == "" and rows[0]["Missing"] == 1 and rows[1]["Missing"] == ""
mc.set_flag(db, pin, keys[0], 2, "Bob B", False); assert mc.load_flags(db, pin) == {}

# a second room does not mix with the first
pin2 = mc.create_room(db, df.iloc[:2], "Other", 3)
assert len(mc.load_swims(db, pin2)) == 2 and len(mc.load_swims(db, pin)) == 5
mc.reset_ticks(db, pin); assert mc.load_ticks(db, pin) == {}
mc.delete_room(db, pin); assert mc.load_room(db, pin) is None and len(mc.load_swims(db, pin2)) == 2

# paging: more than 1000 swims
big = mc.tidy([ent(f"C{i%9}", 1, f"Sw {i}", E1, i // 6 + 1, i % 6 + 1) for i in range(2500)])
pin3 = mc.create_room(db, big, "Big", 5)
assert len(mc.load_swims(db, pin3)) == 2500
print("core tests passed")

if len(sys.argv) > 1:
    class F:
        def __init__(s, p): s.p = p
        def seek(s, n): pass
        def read(s): return open(s.p, "rb").read()
    d = mc.tidy(mc.read_pdf_files([F(sys.argv[1])]))
    print("PDF:", mc.summary(d)); print(d.club.value_counts().to_dict())
    pin4 = mc.create_room(db, d, "PDF", 6); assert len(mc.load_swims(db, pin4)) == len(d)
    print("PDF round trip ok")
