"""Passo 3 - P1-8: gli indici di riferimento entrano nell'aggiornamento daily e un loro errore e' visibile."""
import pandas as pd

import load_historical_data as L
import modulo_a_ingestion as A
import universe as U
import update_daily_prices as D
from fakes import FakeSupabase


def test_indici_inclusi_una_sola_volta_e_fuori_dall_universo_operativo():
    t = D.daily_tickers()
    assert '^GSPC' in t and 'FTSEMIB.MI' in t and len(t) == len(set(t)) == len(U.UNIVERSE_FULL) + 2
    assert '^GSPC' not in U.UNIVERSE_FULL and 'FTSEMIB.MI' not in U.UNIVERSE_FULL
    assert A.INDEX_TICKERS is U.INDEX_TICKERS                                  # unica definizione, usata anche da A


def test_exit_code_solo_per_gli_indici():
    assert D.exit_code_for(['^GSPC']) == 1 and D.exit_code_for(['AAPL', 'FTSEMIB.MI']) == 1
    assert D.exit_code_for(['AAPL', 'ENI.MI']) == 0 and D.exit_code_for([]) == 0


def test_scrittura_daily_degli_indici(monkeypatch):
    idx = pd.date_range('2026-11-10', periods=4, freq='B')
    def frame(base):
        return pd.DataFrame({'Open': base, 'High': base + 1, 'Low': base - 1, 'Close': base + .5, 'Volume': [0, 0, 0, 0]}, index=idx)
    df = pd.concat({'^GSPC': frame(5000.0), 'FTSEMIB.MI': frame(40000.0)}, axis=1)
    db = FakeSupabase()
    monkeypatch.setattr(L, 'supabase', db)
    monkeypatch.setattr(L.yf, 'download', lambda batch, **k: df, raising=False)
    monkeypatch.setattr(L.time, 'sleep', lambda s: None)
    total, failed = L.fetch_and_write(['^GSPC', 'FTSEMIB.MI'], period='5d', label='t')
    assert failed == [] and total == 8
    assert {k[0] for k in db.prezzi} == {'^GSPC', 'FTSEMIB.MI'} and {k[1] for k in db.prezzi} == {'1d'}
