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
    assert is_bar_fresh('ENI.MI', '2026-11-13T11:45:00+00:00', now)            # chiusa da 20 minuti
    assert not is_bar_fresh('ENI.MI', '2026-11-13T11:30:00+00:00', now)        # chiusa da 35 minuti: oltre i 30
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


def test_soglia_di_freschezza_massimo_30_minuti_dalla_fine_della_barra():
    start = '2026-11-13T11:45:00+00:00'                # fine 12:00
    assert is_bar_fresh('ENI.MI', start, dt(2026, 11, 13, 12, 30))        # 30 minuti esatti
    assert not is_bar_fresh('ENI.MI', start, dt(2026, 11, 13, 12, 31))    # 31 minuti
    from bar_freshness import FRESHNESS_MAX_MINUTES
    assert FRESHNESS_MAX_MINUTES <= 30


# ---------------------------------------------------------------- AI Watch: stesso criterio di H1
def _row(minutes_ago_start, volume, flag='ok', close=100.0):
    return {'timestamp': (dt(2026, 11, 13, 12, 5) - timedelta(minutes=minutes_ago_start)).isoformat(), 'close': close, 'volume': volume,
            'data_quality_flag': flag}


def _watch_rows(monkeypatch, rows_newest_first):
    now = dt(2026, 11, 13, 12, 5)
    db = FakeSupabase()
    db.tables['prezzi'] = [dict(r, ticker='ENI.MI') for r in rows_newest_first]
    db.tables['ticker_sectors'] = [{'ticker': 'ENI.MI', 'sector': 'Energy'}]
    monkeypatch.setattr(W, 'supabase', db)
    monkeypatch.setattr(W, 'is_bar_fresh', lambda t, ts: is_bar_fresh(t, ts, now))
    return W.get_universe_metrics()


def _base(n_valid=12, last_volume=6000, last_close=104.0):
    rows = [_row(20, last_volume, close=last_close)]                       # barra corrente (fine 12:00)
    rows += [_row(35 + 15 * i, 1000) for i in range(n_valid)]               # baseline valida
    return rows


def test_ai_watch_baseline_ignora_barre_zero_volume_e_non_ok(monkeypatch):
    pulite = _watch_rows(monkeypatch, _base())
    sporche_rows = _base()
    sporche_rows[3:3] = [_row(40, 0, 'zero_volume'), _row(45, 0, 'zero_volume'), _row(50, 99999, 'stale')]
    sporche = _watch_rows(monkeypatch, sporche_rows)
    assert len(pulite) == len(sporche) == 1
    assert pulite[0]['volume_ratio'] == sporche[0]['volume_ratio'] == 6.0
    assert W.LAST_METRICS_STATS['barre_escluse'] == 3 and W.LAST_METRICS_STATS['ticker_valutati'] == 1


def test_ai_watch_conta_barre_usate_e_scartate(monkeypatch):
    _watch_rows(monkeypatch, _base())
    assert W.LAST_METRICS_STATS['barre_usate'] == 13 and W.LAST_METRICS_STATS['barre_escluse'] == 0


def test_ai_watch_barra_corrente_non_valida_o_poche_valide_escludono_il_ticker(monkeypatch):
    rows = _base(); rows[0]['volume'] = 0
    assert _watch_rows(monkeypatch, rows) == [] and W.LAST_METRICS_STATS['ticker_senza_barra_valida_fresca'] == 1
    rows = [_row(20, 6000)] + [_row(35 + 15 * i, 1000) for i in range(3)] + [_row(80 + 15 * i, 0, 'zero_volume') for i in range(10)]
    assert _watch_rows(monkeypatch, rows) == [] and W.LAST_METRICS_STATS['ticker_dati_insufficienti'] == 1


def test_criterio_di_validita_unico_tra_h1_e_ai_watch():
    import bar_freshness
    assert H.is_valid_bar is bar_freshness.is_valid_bar and W.is_valid_bar is bar_freshness.is_valid_bar
