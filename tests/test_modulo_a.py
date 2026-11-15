import random
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

import modulo_a_ingestion as A
from bar_ingestion_core import coverage, expected_bars, frame_rows, market_for
from fakes import FakeSupabase
from market_calendar import session_bounds

U = timezone.utc


def dt(y, m, d, h, mi=0, s=0):
    return datetime(y, m, d, h, mi, s, tzinfo=U)


def make_df(tickers, now, days=2, hole=0.0, zero=0.0, seed=1):
    """DataFrame tipo yfinance (colonne MultiIndex, indice UTC) con tutte le barre regolari fino a 'now' (inclusa quella in formazione)."""
    rnd = random.Random(seed)
    idx = sorted({dt(2026, 1, 1) + timedelta(minutes=15 * k) for k in range(0)})
    cols, data = {}, {}
    starts = set()
    d = (now - timedelta(days=days)).date()
    per = {}
    while d <= now.date():
        for t in tickers:
            b = session_bounds(market_for(t), d)
            if not b:
                continue
            s = b[0]
            while s < b[1] and s <= now:
                if rnd.random() >= hole:
                    price = 100 + rnd.random()
                    per.setdefault(t, {})[s] = (price, price + 0.3, price - 0.3, price + 0.1,
                                                0 if rnd.random() < zero else rnd.randint(1000, 5000))
                starts.add(s)
                s += timedelta(minutes=15)
        d += timedelta(days=1)
    index = pd.DatetimeIndex(sorted(starts), tz='UTC')
    frames = {}
    for t in tickers:
        rows = [per.get(t, {}).get(s, (None,) * 5) for s in index]
        frames[t] = pd.DataFrame(rows, index=index, columns=['Open', 'High', 'Low', 'Close', 'Volume'])
    return pd.concat(frames, axis=1)


def runner(db, now, tickers, **kw):
    return A.run(client=db, downloader=lambda batch, period: make_df(batch, now, **kw.get('df', {})), now=now,
                 period=kw.get('period', '2d'), tickers=tickers, sleep=0)


# --- lettura del DataFrame -------------------------------------------------------------
def test_frame_rows_multiindex_piatto_e_ticker_mancante():
    now = dt(2026, 11, 13, 12)
    df = make_df(['ENI.MI', 'AAPL'], now, days=1)
    assert len(frame_rows(df, 'ENI.MI')) > 0 and frame_rows(df, 'XXX') == []
    flat = df['ENI.MI']
    assert len(frame_rows(flat, 'ENI.MI')) == len(frame_rows(df, 'ENI.MI'))
    assert frame_rows(pd.DataFrame(), 'ENI.MI') == [] and frame_rows(None, 'ENI.MI') == []


# --- idempotenza e flag non sovrascritti -------------------------------------------------
def test_seconda_esecuzione_senza_duplicati_ne_alterazioni():
    db, now = FakeSupabase(), dt(2026, 11, 13, 17)
    s1 = runner(db, now, ['ENI.MI', 'AAPL'], df={'zero': 0.1})
    snapshot = {k: dict(v) for k, v in db.prezzi.items()}
    assert s1['inserite'] > 0 and s1['duplicate'] == 0 and A.exit_code(s1) == 0
    s2 = runner(db, now, ['ENI.MI', 'AAPL'], df={'zero': 0.1})
    assert s2['inserite'] == 0 and s2['duplicate'] == s1['inserite']
    assert db.prezzi == snapshot                                    # nessuna riga alterata, flag compresi
    # una terza esecuzione molto piu' tardi (le stesse barre sarebbero 'stale') non cambia nulla
    s3 = runner(db, now + timedelta(hours=2), ['ENI.MI', 'AAPL'], df={'zero': 0.1})
    assert all(db.prezzi[k] == snapshot[k] for k in snapshot)
    assert len(db.prezzi) == len(snapshot) + s3['inserite']


def test_flag_calcolati_e_barre_a_volume_zero_conservate():
    db, now = FakeSupabase(), dt(2026, 11, 13, 17)
    s = runner(db, now, ['ENI.MI'], df={'zero': 0.2, 'seed': 4})
    flags = [r['data_quality_flag'] for r in db.prezzi.values()]
    assert 'zero_volume' in flags and all(f in ('ok', 'zero_volume', 'stale') for f in flags)
    assert all(r['volume'] == 0 for r in db.prezzi.values() if r['data_quality_flag'] == 'zero_volume')
    assert s['scartate_in_formazione'] >= 0


# --- esito di processo --------------------------------------------------------------------
def test_errore_di_scrittura_exit_code_1():
    db, now = FakeSupabase(), dt(2026, 11, 13, 17)
    db.fail_writes = True
    s = runner(db, now, ['ENI.MI'])
    assert s['errori_scrittura'] > 0 and A.exit_code(s) == 1 and s['inserite'] == 0


def test_errore_di_download_exit_code_1():
    def boom(batch, period):
        raise RuntimeError('yahoo giu')
    s = A.run(client=FakeSupabase(), downloader=boom, now=dt(2026, 11, 13, 17), tickers=['ENI.MI'], sleep=0)
    assert s['errori_download'] == 1 and A.exit_code(s) == 1


def test_mercato_chiuso_nessuna_barra_nuova_e_exit_0():
    db = FakeSupabase()
    s = A.run(client=db, downloader=lambda b, p: pd.DataFrame(), now=dt(2026, 11, 14, 12), tickers=['ENI.MI'], sleep=0)
    assert A.exit_code(s) == 0 and s['ticker_senza_dati'] == 1 and not db.prezzi


def test_modalita_live_e_backfill():
    assert A.is_live_mode('2d', '') and A.is_live_mode('5d', '') and not A.is_live_mode('59d', '')
    assert not A.is_live_mode('2d', 'backfill') and A.is_live_mode('59d', 'live')


# --- replay isolato di tre sedute ---------------------------------------------------------
def test_replay_tre_sedute_copertura_almeno_98_per_cento():
    """Run ogni 15 minuti per 3 giorni di seduta, con il 20% dei run saltati e un'interruzione di 3 ore,
    1% di barre assenti alla fonte. Obiettivo: copertura >= 98% sulle sedute complete."""
    db = FakeSupabase()
    rnd = random.Random(7)
    tickers = ['ENI.MI', 'ISP.MI', 'AAPL', 'MSFT', '^GSPC']
    t, end = dt(2026, 11, 10, 6), dt(2026, 11, 13, 22)
    outage = (dt(2026, 11, 11, 10), dt(2026, 11, 11, 13))
    runs = errors = 0
    while t <= end:
        if rnd.random() >= 0.20 and not (outage[0] <= t < outage[1]) and t.weekday() < 5:
            s = A.run(client=db, downloader=lambda b, p, n=t: make_df(b, n, hole=0.01, seed=int(n.timestamp()) % 9973),
                      now=t, period='2d', tickers=tickers, sleep=0)
            errors += A.exit_code(s)
            runs += 1
        t += timedelta(minutes=15)
    assert runs > 150 and errors == 0
    by = {}
    for r in db.prezzi.values():
        by.setdefault(r['ticker'], []).append(r)
    assert len(db.prezzi) == len({(r['ticker'], r['timestamp']) for r in db.prezzi.values()})      # nessun duplicato
    cov = coverage(by, dt(2026, 11, 10, 0), dt(2026, 11, 13, 23))
    print('REPLAY', 'run', runs, 'barre_db', len(db.prezzi), 'copertura', cov)
    assert cov['attese'] > 500 and cov['copertura'] >= 0.98, cov
    # le barre scritte sono tutte regolari e chiuse
    assert all(r['interval'] == '15m' for r in db.prezzi.values())


def test_senza_ricopertura_ci_sarebbero_buchi():
    """Prova che il test di copertura e' significativo: scrivendo solo l'ultima barra per run (comportamento vecchio),
    con il 20% di run saltati la copertura scende molto sotto il 98%."""
    db = FakeSupabase()
    rnd = random.Random(7)
    t, end = dt(2026, 11, 10, 6), dt(2026, 11, 13, 22)
    while t <= end:
        if rnd.random() >= 0.20 and t.weekday() < 5:
            df = make_df(['ENI.MI'], t, hole=0.01)
            rows = frame_rows(df, 'ENI.MI')
            closed = [r for r in rows if r[0].to_pydatetime() + timedelta(minutes=16) <= t]
            if closed:
                s, o, h, l, c, v = closed[-1]
                db.prezzi[('ENI.MI', s.isoformat())] = {'ticker': 'ENI.MI', 'timestamp': s.to_pydatetime().isoformat()}
        t += timedelta(minutes=15)
    by = {'ENI.MI': list(db.prezzi.values())}
    assert coverage(by, dt(2026, 11, 10, 0), dt(2026, 11, 13, 23))['copertura'] < 0.9
