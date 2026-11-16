"""Passo 3 - H1/H2: baseline su barre valide, is_anomaly vincolante, guasti tecnici separati dalle promozioni."""
from datetime import datetime, timedelta, timezone

import modulo_h_anomaly as H

U = timezone.utc
T0 = datetime(2026, 11, 13, 8, 0, tzinfo=U)


def bar(i, close=100.0, volume=1000, flag='ok'):
    return {'timestamp': (T0 + timedelta(minutes=15 * i)).isoformat(), 'close': close, 'volume': volume, 'data_quality_flag': flag}


def series(n_base=12, last_volume=6000, last_close=104.0, extra=()):
    bars = [bar(i) for i in range(n_base)] + list(extra)
    bars.append(bar(len(bars), close=last_close, volume=last_volume))
    return bars


# ---------------------------------------------------------------- baseline su barre valide
def test_baseline_esclude_barre_a_volume_zero_e_non_ok():
    base = series()
    sporche = [bar(20 + k, volume=0, flag='zero_volume') for k in range(6)] + [bar(30 + k, volume=50000, flag='stale') for k in range(3)]
    sporca = base[:-1] + sporche + [base[-1]]
    ok1, ratio1, ch1 = H.compute_intraday_anomaly(base, 5.0, 0.03)
    ok2, ratio2, ch2 = H.compute_intraday_anomaly(sporca, 5.0, 0.03)
    assert ok1 and ok2 and ratio1 == ratio2 == 6.0 and abs(ch1 - 0.04) < 1e-9 and ch1 == ch2   # le barre non valide non diluiscono ne' gonfiano


def test_barra_corrente_non_valida_non_e_anomalia():
    for kw in ({'last_volume': 0}, ):
        assert H.compute_intraday_anomaly(series(**kw), 3.0, 0.015)[0] is False
    b = series(); b[-1]['data_quality_flag'] = 'stale'
    assert H.compute_intraday_anomaly(b, 3.0, 0.015)[0] is False


def test_poche_barre_valide_nessuna_anomalia():
    b = series(n_base=5)                                        # 6 valide < 8
    assert H.compute_intraday_anomaly(b, 3.0, 0.015) == (False, 0.0, 0.0)
    b = [bar(i, volume=0, flag='zero_volume') for i in range(10)] + [bar(10, close=110, volume=9000)]
    assert H.compute_intraday_anomaly(b, 3.0, 0.015) == (False, 0.0, 0.0)   # una sola valida


def test_soglie_vincolanti_sul_confronto():
    assert H.compute_intraday_anomaly(series(last_volume=4000, last_close=104.0), 5.0, 0.03)[0] is False   # volume 4x
    assert H.compute_intraday_anomaly(series(last_volume=6000, last_close=102.0), 5.0, 0.03)[0] is False   # movimento 2%
    assert H.compute_intraday_anomaly(series(last_volume=5000, last_close=103.0), 5.0, 0.03)[0] is True    # esattamente sulle soglie


# ---------------------------------------------------------------- run_h2
class _Q:
    def __init__(self, sb): self.sb, self.mode, self.payload, self.id = sb, 'select', None, None
    def select(self, *a, **k): return self
    def eq(self, col, v):
        if col == 'id': self.id = v
        return self
    def gte(self, *a, **k): return self
    def update(self, d): self.mode, self.payload = 'update', d; return self
    def execute(self):
        if self.mode == 'update':
            self.sb.updates[self.id] = self.payload
            class R: data = [self.payload]
            return R()
        class R: pass
        r = R(); r.data = self.sb.rows; return r


class FakeSB:
    def __init__(self, tickers):
        self.rows = [{'id': i + 1, 'ticker': t} for i, t in enumerate(tickers)]
        self.updates = {}
    def table(self, name): return _Q(self)


def run_h2(monkeypatch, bars_by_ticker, ctx=None, fresh=True):
    sb = FakeSB(list(bars_by_ticker))
    monkeypatch.setattr(H, 'supabase', sb)
    monkeypatch.setattr(H, 'get_recent_bars', lambda t, n: bars_by_ticker[t])
    monkeypatch.setattr(H, 'compute_context_score', lambda t: (ctx or {}).get(t, 0.5))
    monkeypatch.setattr(H, 'fetch_news_light_count', lambda t: 2)
    monkeypatch.setattr(H, 'is_bar_fresh', lambda t, ts: fresh)
    code = H.run_h2()
    return sb, code


def test_h2_promuove_solo_chi_supera_le_soglie(monkeypatch):
    sb, code = run_h2(monkeypatch, {'AAA': series(last_volume=7000, last_close=105.0),     # sopra soglie
                                    'BBB': series(last_volume=3500, last_close=102.0)})    # sotto soglie (3,5x, 2%)
    assert code == 0
    assert sb.updates[1]['status'] == 'promosso_a_B' and sb.updates[2]['status'] == 'scartato_h2'


def test_h2_limite_top_n_tra_i_soli_anomali(monkeypatch):
    bars = {f'T{i:02d}': series(last_volume=6000 + 1000 * i, last_close=104.0) for i in range(H.H2_TOP_N + 4)}
    sb, code = run_h2(monkeypatch, bars)
    promoted = [i for i, u in sb.updates.items() if u['status'] == 'promosso_a_B']
    assert code == 0 and len(promoted) == H.H2_TOP_N
    assert set(promoted) == set(range(5, H.H2_TOP_N + 5))                     # i 4 meno forti restano fuori


def test_h2_contesto_non_calcolabile_non_promuove_e_segnala_errore(monkeypatch):
    sb, code = run_h2(monkeypatch, {'AAA': series(last_volume=7000, last_close=105.0), 'BBB': series(last_volume=7000, last_close=105.0)},
                      ctx={'BBB': None})
    assert code == 1                                                         # errore visibile
    assert sb.updates[1]['status'] == 'promosso_a_B' and 2 not in sb.updates  # BBB resta h1_candidate (riprovato dopo)


def test_h2_dati_insufficienti_o_non_freschi_non_promuovono(monkeypatch):
    sb, code = run_h2(monkeypatch, {'AAA': series(n_base=3, last_volume=7000, last_close=105.0)})
    assert code == 0 and sb.updates == {}
    sb, code = run_h2(monkeypatch, {'AAA': series(last_volume=7000, last_close=105.0)}, fresh=False)
    assert code == 0 and sb.updates == {}


def test_h2_ultima_barra_non_valida_non_promuove(monkeypatch):
    sb, code = run_h2(monkeypatch, {'AAA': series(last_volume=0, last_close=105.0)})
    assert sb.updates == {}
