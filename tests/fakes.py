"""Doppioni minimi di Supabase per i test (nessuna rete, nessun DB reale)."""


class _Resp:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, client, table):
        self.c, self.t, self.mode, self.payload, self.kw = client, table, 'select', None, {}

    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def order(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def gte(self, *a, **k): return self
    def in_(self, *a, **k): return self
    def lt(self, *a, **k): return self
    def lte(self, *a, **k): return self
    def like(self, *a, **k): return self
    def range(self, *a, **k): return self
    def neq(self, *a, **k): return self

    def upsert(self, rows, **kw):
        self.mode, self.payload, self.kw = 'upsert', rows, kw
        return self

    def insert(self, rows, **kw):
        self.mode, self.payload, self.kw = 'insert', rows, kw
        return self

    def execute(self):
        c = self.c
        if self.mode == 'upsert':
            if c.fail_writes:
                raise RuntimeError('scrittura simulata fallita')
            key_cols = self.kw['on_conflict'].split(',')
            inserted = []
            for r in self.payload:
                k = tuple(r[x] for x in key_cols)
                if k in c.prezzi:
                    if not self.kw.get('ignore_duplicates'):
                        c.prezzi[k] = dict(r)
                    continue
                c.prezzi[k] = dict(r)
                inserted.append(r)
            return _Resp(inserted)
        if self.mode == 'insert':
            c.inserts.setdefault(self.t, []).extend(self.payload if isinstance(self.payload, list) else [self.payload])
            return _Resp(self.payload)
        return _Resp(c.tables.get(self.t, []))


class FakeSupabase:
    def __init__(self):
        self.prezzi, self.inserts, self.tables, self.fail_writes = {}, {}, {}, False

    def table(self, name):
        return _Query(self, name)
