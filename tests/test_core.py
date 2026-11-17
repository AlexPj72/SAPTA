from datetime import datetime, timedelta, timezone

import bar_ingestion_core as core
from bar_ingestion_core import build_records, classify_bar, new_counters

U = timezone.utc


def dt(y, m, d, h, mi=0, s=0):
    return datetime(y, m, d, h, mi, s, tzinfo=U)


def rec(ticker, start, now, live=True, o=10, h=10.5, l=9.8, c=10.2, v=1000):
    cnt = new_counters()
    out = build_records(ticker, [(start, o, h, l, c, v)], now, live, cnt)
    return out, cnt


# --- barre chiuse / in formazione -------------------------------------------------
def test_barra_in_formazione_scartata_e_chiusa_scritta():
    start = dt(2026, 11, 13, 13, 45)            # 13:45-14:00 UTC
    out, cnt = rec('AAPL', dt(2026, 11, 13, 14, 30), dt(2026, 11, 13, 14, 45, 30))    # USA, 14:30-14:45, chiusa da 30 s
    assert out == [] and cnt['scartate_in_formazione'] == 1
    out, cnt = rec('AAPL', dt(2026, 11, 13, 14, 30), dt(2026, 11, 13, 14, 46, 0))     # USA: chiusa da 60 s -> si scrive subito
    assert len(out) == 1 and cnt['trattenute_non_assestate'] == 0


def test_barra_eu_trattenuta_finche_il_dato_non_e_assestato():
    start = dt(2026, 11, 13, 13, 45)
    out, cnt = rec('ENI.MI', start, dt(2026, 11, 13, 14, 2))                           # 2 minuti dopo la chiusura: provvisoria
    assert out == [] and cnt['trattenute_non_assestate'] == 1
    out, cnt = rec('ENI.MI', start, dt(2026, 11, 13, 14, 14, 59))                      # 14:59 minuti: ancora trattenuta
    assert out == [] and cnt['trattenute_non_assestate'] == 1
    out, cnt = rec('ENI.MI', start, dt(2026, 11, 13, 14, 15, 0))                       # 15 minuti: scritta
    assert len(out) == 1 and cnt['trattenute_non_assestate'] == 0
    out, cnt = rec('ENI.MI', start, dt(2026, 11, 13, 14, 2), live=False)               # backfill: nessuna attesa
    assert len(out) == 1


def test_assestamento_solo_in_modalita_live_e_per_mercato():
    import bar_ingestion_core as c
    assert c.SETTLE_MINUTES == {'EU': 15, 'USA': 0}
    assert c.SETTLE_MINUTES['EU'] <= 30 and c.SETTLE_MINUTES['USA'] <= 30


# --- calendario --------------------------------------------------------------------
def test_pre_apertura_e_dopo_chiusura_eu_scartate():
    now = dt(2026, 11, 13, 20)
    for start in (dt(2026, 11, 13, 7, 45), dt(2026, 11, 13, 16, 30)):   # prima delle 08:00 UTC, asta di chiusura
        out, cnt = rec('ENI.MI', start, now)
        assert out == [] and cnt['scartate_non_regolari'] == 1
    out, _ = rec('ENI.MI', dt(2026, 11, 13, 8, 0), now)                 # prima barra regolare
    assert len(out) == 1
    out, _ = rec('ENI.MI', dt(2026, 11, 13, 16, 15), now)               # ultima barra regolare
    assert len(out) == 1


def test_orari_usa_ora_solare():
    now = dt(2026, 11, 14, 12)
    assert rec('AAPL', dt(2026, 11, 13, 14, 15), now)[1]['scartate_non_regolari'] == 1   # 09:15 NY
    assert len(rec('AAPL', dt(2026, 11, 13, 14, 30), now)[0]) == 1                        # 09:30 NY
    assert len(rec('AAPL', dt(2026, 11, 13, 20, 45), now)[0]) == 1                        # 15:45 NY
    assert rec('AAPL', dt(2026, 11, 13, 21, 0), now)[1]['scartate_non_regolari'] == 1     # 16:00 NY


def test_festivita_usa_ed_europa_e_weekend():
    now = dt(2026, 12, 30, 12)
    assert rec('AAPL', dt(2026, 11, 26, 15), dt(2026, 11, 27, 12))[1]['scartate_non_regolari'] == 1   # Thanksgiving
    assert rec('ENI.MI', dt(2026, 12, 25, 10), now)[1]['scartate_non_regolari'] == 1                  # Natale (Borsa Italiana)
    assert rec('ENI.MI', dt(2026, 11, 14, 10), dt(2026, 11, 16, 12))[1]['scartate_non_regolari'] == 1  # sabato


def test_chiusura_anticipata_usa():
    now = dt(2026, 11, 28, 12)                                           # 27/11: chiusura 13:00 NY = 18:00 UTC
    assert len(rec('AAPL', dt(2026, 11, 27, 17, 45), now)[0]) == 1
    assert rec('AAPL', dt(2026, 11, 27, 18, 15), now)[1]['scartate_non_regolari'] == 1


def test_calendario_non_verificato_non_blocca_e_viene_contato():
    out, cnt = rec('ENI.MI', dt(2027, 1, 5, 10), dt(2027, 1, 5, 12))
    assert len(out) == 1 and cnt['calendario_non_verificato'] == 1


# --- flag ----------------------------------------------------------------------------
def test_volume_zero_conservato_e_marcato():
    out, cnt = rec('ENI.MI', dt(2026, 11, 13, 9), dt(2026, 11, 13, 12), v=0)
    assert len(out) == 1 and out[0]['data_quality_flag'] == 'zero_volume' and out[0]['volume'] == 0


def test_feed_error():
    now = dt(2026, 11, 13, 12)
    s = dt(2026, 11, 13, 9)
    assert rec('ENI.MI', s, now, h=9.0, l=9.8)[0][0]['data_quality_flag'] == 'feed_error'   # high < low
    assert rec('ENI.MI', s, now, o=0)[0][0]['data_quality_flag'] == 'feed_error'             # prezzo non positivo
    assert rec('ENI.MI', s, now, v=-5)[0][0]['data_quality_flag'] == 'feed_error'            # volume negativo
    assert rec('ENI.MI', s, now, v=float('nan'))[0][0]['data_quality_flag'] == 'feed_error'  # volume mancante


def test_nan_sui_prezzi_scartato():
    out, cnt = rec('ENI.MI', dt(2026, 11, 13, 9), dt(2026, 11, 13, 12), c=float('nan'))
    assert out == [] and cnt['scartate_nan'] == 1


def test_stale_solo_live_e_solo_in_finestra():
    start = dt(2026, 11, 13, 9)                       # fine barra 09:15
    now_100 = dt(2026, 11, 13, 10, 55)                # 100 min dopo la fine: oltre soglia (30), dentro finestra (180)
    assert rec('ENI.MI', start, now_100, live=True)[0][0]['data_quality_flag'] == 'stale'
    assert rec('ENI.MI', start, now_100, live=False)[0][0]['data_quality_flag'] == 'ok'     # backfill: mai stale
    assert rec('ENI.MI', start, dt(2026, 11, 13, 9, 35), live=True)[0][0]['data_quality_flag'] == 'ok'     # 20 min
    assert rec('ENI.MI', start, dt(2026, 11, 13, 9, 45), live=True)[0][0]['data_quality_flag'] == 'ok'     # 30 min esatti: ok
    assert rec('ENI.MI', start, dt(2026, 11, 13, 9, 46), live=True)[0][0]['data_quality_flag'] == 'stale'  # 31 min: alimentazione in ritardo
    assert rec('ENI.MI', start, dt(2026, 11, 13, 14), live=True)[0][0]['data_quality_flag'] == 'ok'      # 4h45: recupero
    # la qualita' intrinseca prevale sul ritardo
    assert rec('ENI.MI', start, now_100, v=0)[0][0]['data_quality_flag'] == 'zero_volume'


def test_formato_record():
    out, _ = rec('AAPL', dt(2026, 11, 13, 14, 30), dt(2026, 11, 13, 20))
    r = out[0]
    assert r['interval'] == '15m' and r['source'] == 'yfinance' and r['timestamp'] == '2026-11-13T14:30:00+00:00'
    assert 'reliability_score' not in r and 'created_at' not in r
    assert market_ok()


def market_ok():
    return core.market_for('^GSPC') == 'USA' and core.market_for('FTSEMIB.MI') == 'EU' and core.market_for('AAPL') == 'USA'
