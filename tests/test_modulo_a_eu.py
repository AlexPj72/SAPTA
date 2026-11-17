"""Barre EU: dato provvisorio (volume parziale) non congelato; modalita' repair limitata alle sole barre provvisorie."""
from datetime import datetime, timedelta, timezone

import pandas as pd

import modulo_a_ingestion as A
from fakes import FakeSupabase

U = timezone.utc


def dt(y, m, d, h, mi=0, s=0):
    return datetime(y, m, d, h, mi, s, tzinfo=U)


START = dt(2026, 11, 13, 9, 0)            # barra EU 09:00-09:15 UTC
FINAL_VOL = 5000


def feed(now):
    """Yahoo Italia: la barra appena chiusa e' provvisoria (volume parziale) fino a 15 minuti dopo la chiusura."""
    end = START + timedelta(minutes=15)
    vol = FINAL_VOL if now - end >= timedelta(minutes=15) else 400
    idx = pd.DatetimeIndex([START], tz='UTC')
    return pd.concat({'ENI.MI': pd.DataFrame({'Open': [10.0], 'High': [10.2], 'Low': [9.9], 'Close': [10.1], 'Volume': [vol]}, index=idx)}, axis=1)


def run(db, now, **kw):
    return A.run(client=db, downloader=lambda b, p: feed(now), now=now, period='2d', tickers=['ENI.MI'], sleep=0, **kw)


def test_eu_provvisoria_non_viene_scritta_e_la_definitiva_si():
    db = FakeSupabase()
    s1 = run(db, dt(2026, 11, 13, 9, 17))                 # 2 minuti dopo la chiusura: volume parziale -> trattenuta
    assert db.prezzi == {} and s1['trattenute_non_assestate'] == 1 and A.exit_code(s1) == 0
    s2 = run(db, dt(2026, 11, 13, 9, 31))                 # 16 minuti dopo: dato assestato -> scritto
    assert s2['inserite'] == 1
    (row,) = db.prezzi.values()
    assert row['volume'] == FINAL_VOL and row['data_quality_flag'] == 'ok'
    s3 = run(db, dt(2026, 11, 13, 9, 46))                 # nessuna alterazione ai run successivi
    assert s3['inserite'] == 0 and next(iter(db.prezzi.values()))['volume'] == FINAL_VOL


def seeded(volume, created):
    db = FakeSupabase()
    key = ('ENI.MI', START.isoformat(), '15m', 'yfinance')
    db.prezzi[('ENI.MI', '15m', START.isoformat(), 'yfinance')] = {
        'ticker': 'ENI.MI', 'timestamp': START.isoformat(), 'interval': '15m', 'open': 10.0, 'high': 10.0, 'low': 10.0, 'close': 10.0,
        'volume': volume, 'source': 'yfinance', 'data_quality_flag': 'zero_volume' if volume == 0 else 'ok'}
    return db


def test_repair_aggiorna_solo_le_barre_provvisorie():
    now = dt(2026, 11, 13, 12, 0)
    prov = {('ENI.MI', START.isoformat())}
    db = seeded(0, 'x')
    s = A.run(client=db, downloader=lambda b, p: feed(now), now=now, period='2d', mode='repair', tickers=['ENI.MI'], sleep=0, provisional=prov)
    (row,) = db.prezzi.values()
    assert s['riparate'] == 1 and row['volume'] == FINAL_VOL and row['data_quality_flag'] == 'ok' and row['high'] == 10.2
    # barra NON provvisoria: intatta
    db2 = seeded(777, 'x')
    s2 = A.run(client=db2, downloader=lambda b, p: feed(now), now=now, period='2d', mode='repair', tickers=['ENI.MI'], sleep=0, provisional=set())
    (row2,) = db2.prezzi.values()
    assert s2['riparate'] == 0 and row2['volume'] == 777


def test_repair_non_inserisce_barre_nuove():
    now = dt(2026, 11, 13, 12, 0)
    db = FakeSupabase()
    s = A.run(client=db, downloader=lambda b, p: feed(now), now=now, period='2d', mode='repair', tickers=['ENI.MI'], sleep=0, provisional=set())
    assert db.prezzi == {} and s['riparate'] == 0


class _Q:
    def __init__(self, rows): self.rows, self.off = rows, 0
    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def like(self, *a, **k): return self
    def gte(self, *a, **k): return self
    def order(self, *a, **k): return self
    def range(self, a, b): self.off = (a, b); return self
    def execute(self):
        class R: pass
        r = R(); r.data = self.rows[self.off[0]:self.off[1] + 1]; return r


class _C:
    def __init__(self, rows): self.rows = rows
    def table(self, n): return _Q(self.rows)


def test_individua_le_chiavi_provvisorie_dal_ritardo_di_acquisizione():
    end = START + timedelta(minutes=15)
    rows = [{'ticker': 'ENI.MI', 'timestamp': START.isoformat(), 'created_at': (end + timedelta(minutes=1.5)).isoformat()},        # provvisoria
            {'ticker': 'ISP.MI', 'timestamp': START.isoformat(), 'created_at': (end + timedelta(minutes=16)).isoformat()},         # assestata
            {'ticker': 'TEN.MI', 'timestamp': START.isoformat(), 'created_at': (end + timedelta(minutes=14.9)).isoformat()}]       # al limite: provvisoria
    keys = A.fetch_provisional_keys(_C(rows), START - timedelta(days=1), dt(2026, 11, 13, 12))
    assert keys == {('ENI.MI', START.isoformat()), ('TEN.MI', START.isoformat())}


def test_timestamp_supabase_con_frazioni_irregolari():
    end = START + timedelta(minutes=15)
    rows = [{'ticker': 'ENI.MI', 'timestamp': '2026-11-13T09:00:00+00:00', 'created_at': '2026-11-13T09:16:38.11709+00:00'},    # 5 cifre: provvisoria
            {'ticker': 'ISP.MI', 'timestamp': '2026-11-13T09:00:00+00:00', 'created_at': '2026-11-13T09:31:02.5+00:00'}]       # 1 cifra: assestata
    keys = A.fetch_provisional_keys(_C(rows), START - timedelta(days=1), dt(2026, 11, 13, 12))
    assert keys == {('ENI.MI', START.isoformat())}
