"""A tiny in-memory stand-in for the Supabase client, enough for the calls marshal_core makes."""
class _Q:
    def __init__(self, db, name): self.db, self.name, self.f, self.op, self.payload, self.rng, self.on = db, name, [], "select", None, None, None
    def select(self, cols="*"): self.op = "select"; return self
    def eq(self, k, v): self.f.append((k, v)); return self
    def order(self, *a, **k): return self
    def range(self, a, b): self.rng = (a, b); return self
    def insert(self, rows): self.op, self.payload = "insert", rows; return self
    def upsert(self, row, on_conflict=None): self.op, self.payload, self.on = "upsert", row, on_conflict; return self
    def delete(self): self.op = "delete"; return self
    def _match(self, r): return all(str(r.get(k)) == str(v) for k, v in self.f)
    def execute(self):
        t = self.db.tables.setdefault(self.name, [])
        class R: pass
        r = R(); r.data = []
        if self.op == "select":
            rows = [dict(x) for x in t if self._match(x)]
            if self.rng: rows = rows[self.rng[0]:self.rng[1] + 1]
            r.data = rows
        elif self.op == "insert":
            for row in (self.payload if isinstance(self.payload, list) else [self.payload]):
                self.db.n += 1; t.append({**row, "id": self.db.n})
        elif self.op == "upsert":
            keys = self.on.split(",")
            for x in t:
                if all(str(x.get(k)) == str(self.payload.get(k)) for k in keys): x.update(self.payload); break
            else:
                self.db.n += 1; t.append({**self.payload, "id": self.db.n})
        elif self.op == "delete":
            self.db.tables[self.name] = [x for x in t if not self._match(x)]
        return r
class FakeDB:
    def __init__(self): self.tables, self.n = {}, 0
    def table(self, name): return _Q(self, name)
