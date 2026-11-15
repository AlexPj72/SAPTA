import gzip, os
from datetime import datetime, timezone

import archivia_barre_15m as AR

U = timezone.utc


class _R:
    def __init__(self, data=None, count=None):
        self.data, self.count = data, count


class FakeArchiveClient:
    """Tabella prezzi in memoria con i soli filtri usati dallo script; registra qualsiasi tentativo di scrittura."""
    def __init__(self, rows):
        self.rows, self.writes = rows, 0
    def table(self, name):
        return _Q(self)


class _Q:
    def __init__(self, c):
        self.c, self.f, self.cnt, self.rng, self.lim = c, [], False, None, None
    def select(self, *a, **k):
        self.cnt = k.get('count') == 'exact'; return self
    def eq(self, col, v): self.f.append(lambda r: r[col] == v); return self
    def gte(self, col, v): self.f.append(lambda r: r[col] >= v); return self
    def lt(self, col, v): self.f.append(lambda r: r[col] < v); return self
    def order(self, *a, **k): return self
    def limit(self, n): self.lim = n; return self
    def range(self, a, b): self.rng = (a, b); return self
    def upsert(self, *a, **k): self.c.writes += 1; return self
    def insert(self, *a, **k): self.c.writes += 1; return self
    def delete(self, *a, **k): self.c.writes += 1; return self
    def update(self, *a, **k): self.c.writes += 1; return self
    def execute(self):
        rows = sorted((r for r in self.c.rows if all(f(r) for f in self.f)), key=lambda r: r['timestamp'])
        total = len(rows)
        if self.rng: rows = rows[self.rng[0]:self.rng[1] + 1]
        if self.lim: rows = rows[:self.lim]
        return _R(rows, total if self.cnt else None)


def _rows():
    out = []
    for mon in (1, 2, 3):
        for i in range(2500):                      # > PAGE: prova la paginazione
            out.append({'ticker': 'ENI.MI', 'timestamp': datetime(2025, mon, 1 + i // 100, i % 24, 0, tzinfo=U).isoformat(),
                        'interval': '15m', 'open': 1, 'high': 2, 'low': 1, 'close': 1.5, 'volume': i, 'source': 'yfinance',
                        'data_quality_flag': 'ok'})
    out.append(dict(out[0], timestamp='2026-11-10T09:00:00+00:00'))
    return out


def test_archivio_e_verifica_senza_scritture(tmp_path):
    c = FakeArchiveClient(_rows())
    cutoff = AR.cutoff_from(datetime(2026, 11, 14, tzinfo=U), 12)       # 2025-11-01: archivia solo i mesi 2025-01..03
    assert cutoff == datetime(2025, 11, 1, tzinfo=U)
    mf = AR.archive(c, cutoff, str(tmp_path))
    assert [m['mese'] for m in mf] == ['2025-01', '2025-02', '2025-03'] and all(m['righe'] == 2500 for m in mf)
    assert AR.verify(c, str(tmp_path)) is True
    assert c.writes == 0                                                # sola lettura: nessuna scrittura/cancellazione


def test_verifica_fallisce_se_il_file_e_alterato(tmp_path):
    c = FakeArchiveClient(_rows())
    AR.archive(c, datetime(2025, 11, 1, tzinfo=U), str(tmp_path))
    p = os.path.join(tmp_path, 'prezzi_15m_2025-02.csv.gz')
    with gzip.open(p, 'wt') as fh:
        fh.write('ticker\nENI.MI\n')
    assert AR.verify(c, str(tmp_path)) is False


def test_db_vuoto():
    assert AR.archive(FakeArchiveClient([]), datetime(2025, 11, 1, tzinfo=U), '/tmp/_vuoto_arch') == []
