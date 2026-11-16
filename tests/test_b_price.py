"""Passo 3 - P1-3: il prezzo di B viene solo da una barra 15m valida e fresca."""
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

import modulo_b_analysis as B
from bar_freshness import is_bar_fresh

U = timezone.utc
NOW = datetime(2026, 11, 13, 12, 5, tzinfo=U)       # venerdi', Borsa Italiana aperta


class _Resp:
    def __init__(self, data): self.data = data


class _Q:
    def __init__(self, rows): self.rows = rows
    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def order(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def execute(self): return _Resp(self.rows)


class _SB:
    def __init__(self, rows): self.rows = rows
    def table(self, name): return _Q(self.rows)


def r(minutes_before_end, close=10.0, volume=1000, flag='ok'):
    """Barra la cui FINE e' minutes_before_end minuti prima di NOW."""
    start = NOW - timedelta(minutes=minutes_before_end + 15)
    return {'timestamp': start.isoformat(), 'close': close, 'volume': volume, 'data_quality_flag': flag}


def price(monkeypatch, rows):
    monkeypatch.setattr(B, 'supabase', _SB(rows))
    monkeypatch.setattr(B, 'is_bar_fresh', lambda t, ts: is_bar_fresh(t, ts, NOW))
    return B.get_latest_intraday_price('ENI.MI')


def test_usa_la_barra_valida_piu_recente(monkeypatch):
    assert price(monkeypatch, [r(5, close=10.5), r(20, close=10.0)]) == 10.5


def test_salta_barre_stale_zero_volume_e_feed_error_e_usa_la_valida_precedente_se_fresca(monkeypatch):
    rows = [r(2, close=99.0, flag='stale'), r(7, close=98.0, volume=0, flag='zero_volume'), r(12, close=97.0, flag='feed_error'),
            r(17, close=10.2)]
    assert price(monkeypatch, rows) == 10.2


def test_barra_valida_ma_non_fresca_non_da_prezzo(monkeypatch):
    assert price(monkeypatch, [r(40, close=10.0)]) is None                       # chiusa da 40 minuti
    assert price(monkeypatch, [r(2, close=99.0, flag='stale'), r(45, close=10.0)]) is None


def test_nessuna_barra_valida_nessun_prezzo(monkeypatch):
    assert price(monkeypatch, [r(2, volume=0, flag='zero_volume'), r(7, flag='stale')]) is None
    assert price(monkeypatch, []) is None


def test_limite_30_minuti_dalla_fine(monkeypatch):
    assert price(monkeypatch, [r(30, close=10.0)]) == 10.0
    assert price(monkeypatch, [r(31, close=10.0)]) is None


def _daily():
    idx = pd.bdate_range(end='2026-11-12', periods=320)
    rng = np.random.default_rng(3)
    close = 100 + np.cumsum(rng.normal(0, 1, len(idx)))
    return pd.DataFrame({'Open': close, 'High': close + 1, 'Low': close - 1, 'Close': close, 'Volume': 1_000_000}, index=idx)


def test_indicatori_senza_prezzo_valido_non_producono_segnale(monkeypatch):
    monkeypatch.setattr(B, 'get_latest_intraday_price', lambda t: None)
    assert B.calculate_technical_indicators('ENI.MI', _daily()) is None             # niente ripiego sulla chiusura giornaliera


def test_indicatori_con_prezzo_valido_usano_quel_prezzo(monkeypatch):
    monkeypatch.setattr(B, 'get_latest_intraday_price', lambda t: 123.45)
    ind = B.calculate_technical_indicators('ENI.MI', _daily())
    assert ind is not None and ind['close'] == 123.45 and ind['daily_close'] != 123.45
