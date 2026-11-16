"""Passo 3 - P1-5/P1-6/P1-7: costi andata e ritorno, controlli fail-closed in E, dimensionamento unico E/T."""
import random
from datetime import datetime, timedelta, timezone

import pytest

import modulo_e_cost_filter as E
import modulo_t_state_machine as T
import sizing
from fakes import FakeSupabase

U = timezone.utc

COSTS_EU = {'commissione_fissa': 1.25, 'commissione_percentuale': 0.0005, 'spread_medio_percentuale': 0.001,
            'bollo_percentuale': 0.0, 'tassazione_plusvalenza_percentuale': 0.26}
COSTS_USA = {'commissione_fissa': 0.0, 'commissione_percentuale': 0.0, 'spread_medio_percentuale': 0.0005,
             'bollo_percentuale': 0.0, 'tassazione_plusvalenza_percentuale': 0.26}


# ------------------------------------------------------------------ dimensionamento unico
def test_una_sola_funzione_di_dimensionamento():
    assert E.size_position is T.size_position is sizing.size_position
    assert E.RISK_PER_TRADE_PERCENT == T.RISK_PER_TRADE_PERCENT == sizing.RISK_PER_TRADE_PERCENT == 0.01
    assert T.ZONE_ATR_FRACTION == sizing.ZONE_ATR_FRACTION == 0.5


def test_size_position_valori_noti():
    sz = sizing.size_position(100, 2, 97, 1000, 1.0, COSTS_EU, 'LIQ_HIGH')
    assert sz['quantity'] == 1 and sz['entry_price'] == pytest.approx(101.0505)           # R + 0,5 ATR con slippage
    assert sz['countervalue_eur'] == pytest.approx(101.05)
    sz = sizing.size_position(10, 0.2, 9.7, 1000, 1.0, COSTS_EU, 'LIQ_HIGH')              # stop vicino: piu' azioni
    assert isinstance(sz['quantity'], int) and sz['quantity'] > 1


def test_rischio_mai_oltre_l_uno_per_cento_costi_inclusi():
    rnd = random.Random(11)
    for _ in range(2000):
        ref = rnd.uniform(5, 800); atr = ref * rnd.uniform(0.005, 0.05)
        inv = ref - 1.5 * atr
        fx = rnd.choice([1.0, 0.86]); costs = rnd.choice([COSTS_EU, COSTS_USA]); bucket = rnd.choice(['LIQ_HIGH', 'LIQ_MEDIUM', 'LIQ_LOW', None])
        cap = 1000.0
        sz = sizing.size_position(ref, atr, inv, cap, fx, costs, bucket)
        q = sz['quantity']
        assert q >= 0 and sz['countervalue_eur'] <= cap + 0.01
        if q:
            slip = sizing.slippage_for(bucket)
            entry = sz['entry_price']
            loss_local = q * (entry - inv * (1 - slip)) + sizing.round_trip_cost(entry, q, costs, bucket)[0] - q * entry * 0 \
                - (q * entry * slip * 2)                                   # lo slippage e' gia' nella perdita allo stop (ingresso e uscita)
            loss_local = q * (entry - inv * (1 - slip)) + 2 * costs['commissione_fissa'] / fx + q * entry * 2 * (
                costs['commissione_percentuale'] + costs['spread_medio_percentuale'] + costs['bollo_percentuale'])
            assert loss_local * fx <= cap * 0.01 + 1e-6, (ref, atr, q, loss_local * fx)


def test_i_costi_riducono_la_quantita_rispetto_al_caso_senza_costi():
    free = dict(COSTS_EU, commissione_fissa=0.0, commissione_percentuale=0.0, spread_medio_percentuale=0.0)
    a = sizing.size_position(20, 0.4, 19.4, 1000, 1.0, free, 'LIQ_HIGH')['quantity']
    b = sizing.size_position(20, 0.4, 19.4, 1000, 1.0, COSTS_EU, 'LIQ_HIGH')['quantity']
    assert b < a


def test_non_dimensionabile():
    assert sizing.size_position(100, 2, None, 1000, 1.0, COSTS_EU, 'LIQ_HIGH') is None
    assert sizing.size_position(100, 2, 150, 1000, 1.0, COSTS_EU, 'LIQ_HIGH') is None        # stop sopra l'ingresso
    assert sizing.size_position(100, 2, 97, 1000, 1.0, None, 'LIQ_HIGH') is None
    assert sizing.size_position(100, 2, 97, 1000, 0, COSTS_EU, 'LIQ_HIGH') is None


def test_capitale_di_riferimento_1000_e_non_aumentato():
    assert sizing.REFERENCE_CAPITAL_EUR == 1000 and E.FALLBACK_CAPITAL_EUR == 1000
    sz = sizing.size_position(10, 5, 5, 1000, 1.0, COSTS_USA, 'LIQ_HIGH')                    # stop lontanissimo: tetto del capitale
    assert sz['countervalue_eur'] <= 1000


# ------------------------------------------------------------------ costi e rendimento atteso
def test_costi_andata_e_ritorno_sono_il_doppio_di_un_lato():
    one, _ = sizing.calculate_operation_cost(100, 5, COSTS_EU, 'LIQ_MEDIUM')
    rt, _ = sizing.round_trip_cost(100, 5, COSTS_EU, 'LIQ_MEDIUM')
    assert rt == pytest.approx(2 * one) and one == pytest.approx(1.25 + 500 * (0.0005 + 0.001 + 0.0015))


def test_rendimento_atteso_coerente_con_target_e_costi_andata_ritorno():
    r = E.calculate_expected_return(100, 1.0, 2.0, COSTS_EU, 3, 'LIQ_HIGH', target_price=106.0)
    entry = sizing.entry_reference_price(100, 2, 'LIQ_HIGH')
    assert r['expected_gross_return'] == pytest.approx(((106.0 - entry) / entry) * 1.0)
    rt, _ = sizing.round_trip_cost(entry, 3, COSTS_EU, 'LIQ_HIGH')
    assert r['estimated_cost'] == pytest.approx(rt / (entry * 3))
    r2 = E.calculate_expected_return(100, 1.0, 2.0, COSTS_EU, 3, 'LIQ_HIGH', target_price=None)      # ripiego 2*ATR
    assert r2['expected_gross_return'] == pytest.approx((4.0 / entry) * 1.0)
    assert r['expected_net_return'] < r['expected_gross_return']


# ------------------------------------------------------------------ E: fail-closed
class _Boom:
    def table(self, name): raise RuntimeError('db giu')


class _Rows:
    def __init__(self, rows): self.rows = rows
    def table(self, name): return self
    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def order(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def execute(self):
        class R: pass
        r = R(); r.data = self.rows; return r


def test_settore_sconosciuto_blocca():
    ok, n, why = E.check_sector_concentration('BPSO.MI', None, 7, 2)
    assert ok is False and 'non riconosciuto' in why


def test_errore_controllo_settore_blocca(monkeypatch):
    monkeypatch.setattr(E, 'supabase', _Boom())
    ok, n, why = E.check_sector_concentration('ENI.MI', 'Energy', 7, 2)
    assert ok is False and 'NON eseguibile' in why


def test_settore_ok_e_al_limite(monkeypatch):
    monkeypatch.setattr(E, 'supabase', _Rows([{'ticker': 'ENI.MI'}, {'ticker': 'TEN.MI'}, {'ticker': 'SOL.MI'}]))
    monkeypatch.setattr(E, 'get_active_exposure_items', lambda: [{'ticker': 'TEN.MI', 'eur': 100}])
    assert E.check_sector_concentration('ENI.MI', 'Energy', 7, 2) == (True, 1, None)
    monkeypatch.setattr(E, 'get_active_exposure_items', lambda: [{'ticker': 'TEN.MI', 'eur': 1}, {'ticker': 'SOL.MI', 'eur': 1}])
    ok, n, why = E.check_sector_concentration('ENI.MI', 'Energy', 7, 2)
    assert (ok, n) == (False, 2) and 'Concentrazione settoriale' in why


def test_errore_controllo_esposizione_blocca(monkeypatch):
    def boom(): raise RuntimeError('db giu')
    monkeypatch.setattr(E, 'get_active_exposure_items', boom)
    ok, pct, why = E.check_portfolio_exposure(100, 1000, 7, 0.6)
    assert ok is False and 'NON eseguibile' in why


def test_esposizione_ok_e_oltre_soglia(monkeypatch):
    monkeypatch.setattr(E, 'get_active_exposure_items', lambda: [{'ticker': 'A', 'eur': 400}])
    assert E.check_portfolio_exposure(100, 1000, 7, 0.6) == (True, 0.5, None)
    ok, pct, why = E.check_portfolio_exposure(300, 1000, 7, 0.6)
    assert ok is False and pct == pytest.approx(0.7) and 'Esposizione' in why


def test_capitale_errore_di_lettura_non_usa_il_ripiego(monkeypatch):
    monkeypatch.setattr(E, 'supabase', _Boom())
    with pytest.raises(E.CapitalUnavailable):
        E.get_current_capital()
    monkeypatch.setattr(E, 'supabase', _Rows([]))
    assert E.get_current_capital() == 1000
    monkeypatch.setattr(E, 'supabase', _Rows([{'capital_eur': 1000}]))
    assert E.get_current_capital() == 1000


# ------------------------------------------------------------------ T: stessa quantita' di E
class _TStore:
    def __init__(self, capital=1000.0, costs=COSTS_EU, cash=900.0):
        self.capital, self.costs, self.cash, self.updates = capital, costs, cash, []
    def portfolio_cash(self): return self.cash
    def reserved_eur(self): return 0.0
    def reference_capital(self): return self.capital
    def costs_for(self, market): return self.costs
    def update(self, lc, fields): self.updates.append(fields); return dict(lc, **fields)
    def record_event(self, *a, **k): return True


def _lc(**kw):
    lc = {'id': 5, 'ticker': 'ENI.MI', 'market': 'EU', 'currency': 'EUR', 'state': 'WATCH', 'ref_price': 100.0, 'atr': 2.0,
          'invalidation_price': 97.0, 'target_price': 106.0, 'slippage_pct': 0.0005, 'liquidity_bucket': 'LIQ_HIGH',
          'zone_low': 100.0, 'zone_high': 101.0, 'last_note': None}
    return dict(lc, **kw)


def _bar():
    t = datetime(2026, 11, 13, 9, 0, tzinfo=U)
    return {'start': t, 'end': t + timedelta(minutes=15), 'o': 100.2, 'h': 100.6, 'l': 100.0, 'c': 100.4, 'v': 1000, 'flag': 'ok'}


def _engine(store, **kw):
    eng = T.Engine(FakeSupabase(), datetime(2026, 11, 13, 9, 20, tzinfo=U), dry_run=True, log=lambda *a, **k: None)
    eng.store = store
    eng.captured, eng.notes_made = {}, []
    eng._apply = lambda lc, key, etype, to_state, updates, **k: (eng.captured.update(updates) or dict(lc, state=to_state, **updates))
    eng._note = lambda lc, bar, text, retry=False: (eng.notes_made.append(text) or lc)
    return eng


def test_T_e_E_producono_la_stessa_quantita_e_lo_stesso_controvalore_di_riferimento():
    lc = _lc()
    expected = sizing.size_position(100.0, 2.0, 97.0, 1000.0, 1.0, COSTS_EU, 'LIQ_HIGH')       # chiamata identica a quella di E
    eng = _engine(_TStore())
    eng._trigger(lc, _bar())
    assert eng.captured['quantity'] == expected['quantity'] >= 1
    assert eng.captured['countervalue_eur'] <= expected['countervalue_eur'] + 1e-9           # fill reale <= prezzo di dimensionamento


def test_T_usa_il_capitale_di_riferimento_non_la_cassa():
    eng = _engine(_TStore(capital=1000.0, cash=5000.0))                                        # cassa molto maggiore: nessun effetto
    eng._trigger(_lc(), _bar())
    q_ref = eng.captured['quantity']
    eng2 = _engine(_TStore(capital=1000.0, cash=300.0))
    eng2._trigger(_lc(), _bar())
    assert eng2.captured['quantity'] == q_ref


def test_T_senza_capitale_o_costi_non_entra():
    eng = _engine(_TStore(capital=None))
    eng._trigger(_lc(), _bar())
    assert eng.captured == {} and any('capitale di riferimento' in n for n in eng.notes_made)
    eng = _engine(_TStore(costs=None))
    eng._trigger(_lc(), _bar())
    assert eng.captured == {} and any('costi' in n for n in eng.notes_made)


def test_T_cassa_insufficiente_non_esegue_ma_non_cambia_la_quantita():
    eng = _engine(_TStore(cash=10.0))
    eng._trigger(_lc(), _bar())
    assert eng.captured == {} and any('capitale virtuale libero' in n for n in eng.notes_made)
