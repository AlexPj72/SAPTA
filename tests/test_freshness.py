from datetime import datetime, timedelta, timezone

import modulo_ai_watch as W
import modulo_h_anomaly as H
from bar_freshness import is_bar_fresh, parse_ts
from fakes import FakeSupabase

U = timezone.utc


def dt(y, m, d, h, mi=0, s=0):
    return datetime(y, m, d, h, mi, s, tzinfo=U)


def test_barra_ok_ma_vecchia_non_e_fresca():
    now = dt(2026, 11, 13, 12, 20)
    assert is_bar_fresh('ENI.MI', '2026-11-13T12:00:00+00:00', now)            # chiusa da 5 minuti
    assert is_bar_fresh('ENI.MI', '2026-11-13T11:30:00+00:00', now)            # 35 minuti: dentro i 45
    assert not is_bar_fresh('ENI.MI', '2026-11-13T11:00:00+00:00', now)        # 65 minuti
    assert not is_bar_fresh('ENI.MI', '2026-11-12T16:15:00+00:00', now)        # chiusura di ieri
    assert not is_bar_fresh('AAPL', '2026-11-13T20:45:00+00:00', dt(2026, 11, 14, 14, 0))   # venerdi' sera, sabato


def test_mercato_chiuso_pre_post_festivita():
    assert not is_bar_fresh('ENI.MI', '2026-11-13T16:30:00+00:00', dt(2026, 11, 13, 16, 50))   # asta di chiusura
    assert not is_bar_fresh('ENI.MI', '2026-11-13T07:45:00+00:00', dt(2026, 11, 13, 8, 5))     # pre-apertura
    assert not is_bar_fresh('AAPL', '2026-11-26T15:00:00+00:00', dt(2026, 11, 26, 15, 20))     # Thanksgiving
    assert is_bar_fresh('AAPL', '2026-11-13T20:45:00+00:00', dt(2026, 11, 13, 21, 5))          # ultima barra regolare, appena chiusa


def test_timestamp_irregolari_e_invalidi():
    assert parse_ts('2026-11-13T08:30:00.12345+00:00').minute == 30
    assert parse_ts('2026-11-13T08:30:00Z').hour == 8
    assert not is_bar_fresh('ENI.MI', None, dt(2026, 11, 13, 12))
    assert not is_bar_fresh('ENI.MI', 'non-una-data', dt(2026, 11, 13, 12))


def _bars(last_start, n=20, last_vol=50000, last_close=103.0):
    out = []
    for i in range(n):
        s = last_start - timedelta(minutes=15 * (n - 1 - i))
        out.append({'timestamp': s.isoformat(), 'close': 100.0 if i < n - 1 else last_close,
                    'volume': 1000 if i < n - 1 else last_vol, 'data_quality_flag': 'ok'})
    return out


def _h1(monkeypatch, bars, now):
    db = FakeSupabase()
    monkeypatch.setattr(H, 'supabase', db)
    monkeypatch.setattr(H, 'get_universe', lambda: ['ENI.MI'])
    monkeypatch.setattr(H, 'get_ticker_meta_map', lambda: {})
    monkeypatch.setattr(H, 'get_tickers_already_candidate_today', lambda: set())
    monkeypatch.setattr(H, 'get_recent_bars', lambda t, n: bars)
    monkeypatch.setattr(H, 'is_bar_fresh', lambda t, ts: is_bar_fresh(t, ts, now))   # orologio fisso, stessa funzione
    H.run_h1()
    return db.inserts.get('screening_candidates', [])


def test_h1_elabora_barra_fresca(monkeypatch):
    now = dt(2026, 11, 13, 12, 5)
    assert len(_h1(monkeypatch, _bars(dt(2026, 11, 13, 11, 45)), now)) == 1


def test_h1_non_elabora_barra_ok_ma_vecchia(monkeypatch):
    now = dt(2026, 11, 13, 12, 5)
    assert _h1(monkeypatch, _bars(dt(2026, 11, 12, 16, 15)), now) == []          # ieri, flag 'ok', picco di volume
    assert _h1(monkeypatch, _bars(dt(2026, 11, 13, 10, 0)), now) == []           # 2 ore fa


def _watch(monkeypatch, bars, now):
    db = FakeSupabase()
    db.tables['prezzi'] = [dict(b, ticker='ENI.MI') for b in reversed(bars)]
    db.tables['ticker_sectors'] = [{'ticker': 'ENI.MI', 'sector': 'Energy'}]
    monkeypatch.setattr(W, 'supabase', db)
    monkeypatch.setattr(W, 'is_bar_fresh', lambda t, ts: is_bar_fresh(t, ts, now))
    return W.get_universe_metrics()


def test_ai_watch_barra_fresca_e_barra_vecchia(monkeypatch):
    now = dt(2026, 11, 13, 12, 5)
    assert len(_watch(monkeypatch, _bars(dt(2026, 11, 13, 11, 45)), now)) == 1
    assert _watch(monkeypatch, _bars(dt(2026, 11, 12, 16, 15)), now) == []
