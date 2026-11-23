"""Decisione del 22/11: rischio 1% invariato; quantita' frazionarie ESCLUSIVAMENTE per i titoli USA; azioni italiane intere."""
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
FX = 1 / 1.099


def loss_eur(sz, ref, atr, inv, costs, fx, bucket):
    """Perdita allo stop in EUR (slippage e costi di andata e ritorno inclusi) della posizione dimensionata."""
    q, slip = sz['quantity'], sizing.slippage_for(bucket)
    entry = sz['entry_price']
    local = q * (entry - inv * (1 - slip)) + 2 * costs['commissione_fissa'] / fx + q * entry * 2 * (
        costs['commissione_percentuale'] + costs['spread_medio_percentuale'] + costs['bollo_percentuale'])
    return local * fx


def test_frazioni_consentite_solo_per_gli_usa():
    assert sizing.allows_fractional('USA') is True and sizing.allows_fractional('EU') is False
    assert sizing.FRACTIONAL_MARKETS == ('USA',)
    assert E.market_for_ticker('AMZN') == 'USA' and E.market_for_ticker('ENI.MI') == 'EU'


def test_titolo_usa_caro_ora_e_dimensionabile_con_rischio_1_per_cento():
    # AMZN del 20/11: prezzo 255,84, ATR 9,59 -> stop R - 1,5 ATR
    ref, atr = 255.84, 9.59
    inv = ref - 1.5 * atr
    sz = sizing.size_position(ref, atr, inv, 1000.0, FX, COSTS_USA, 'LIQ_HIGH', fractional=True)
    assert 0 < sz['quantity'] < 1 and sz['fractional'] is True
    assert round(sz['quantity'], 4) == sz['quantity']                                 # al massimo 4 decimali
    assert loss_eur(sz, ref, atr, inv, COSTS_USA, FX, 'LIQ_HIGH') <= 10.0 + 1e-6       # 1% di 1.000 EUR, costi inclusi
    assert loss_eur(sz, ref, atr, inv, COSTS_USA, FX, 'LIQ_HIGH') > 9.9                 # e lo usa quasi tutto (troncamento per difetto)
    assert sz['countervalue_eur'] <= 1000
    # senza frazioni lo stesso titolo resta non dimensionabile (comportamento precedente)
    assert sizing.size_position(ref, atr, inv, 1000.0, FX, COSTS_USA, 'LIQ_HIGH', fractional=False)['quantity'] == 0


def test_titoli_italiani_restano_interi():
    ref, atr = 66.4, 1.85
    inv = ref - 1.5 * atr
    sz = sizing.size_position(ref, atr, inv, 1000.0, 1.0, COSTS_EU, 'LIQ_MEDIUM', fractional=sizing.allows_fractional('EU'))
    assert sz['quantity'] == int(sz['quantity']) and sz['quantity'] >= 1 and sz['fractional'] is False
    caro = sizing.size_position(487.0, 12.4, 487.0 - 18.6, 1000.0, 1.0, COSTS_EU, 'LIQ_HIGH', fractional=sizing.allows_fractional('EU'))
    assert caro['quantity'] == 0                                                         # niente frazioni in Italia


def test_rischio_mai_oltre_l_uno_per_cento_con_frazioni():
    rnd = random.Random(5)
    for _ in range(3000):
        ref = rnd.uniform(5, 900); atr = ref * rnd.uniform(0.005, 0.09)
        inv = ref - 1.5 * atr
        bucket = rnd.choice(['LIQ_HIGH', 'LIQ_MEDIUM', 'LIQ_LOW', None])
        fx = rnd.choice([FX, 1.0])
        sz = sizing.size_position(ref, atr, inv, 1000.0, fx, COSTS_USA, bucket, fractional=True)
        assert sz['countervalue_eur'] <= 1000.0 + 0.01
        if sz['quantity']:
            assert loss_eur(sz, ref, atr, inv, COSTS_USA, fx, bucket) <= 10.0 + 1e-6
        else:
            assert sz['quantity'] == 0


def test_capitale_e_limite_di_rischio_invariati():
    assert sizing.REFERENCE_CAPITAL_EUR == 1000 and sizing.RISK_PER_TRADE_PERCENT == 0.01


# ------------------------------------------------------------------ E e T: stessa quantita' frazionaria
class _TStore:
    def portfolio_cash(self): return 900.0
    def reserved_eur(self): return 0.0
    def reference_capital(self): return 1000.0
    def costs_for(self, market): return COSTS_USA if market == 'USA' else COSTS_EU
    def update(self, lc, fields): return dict(lc, **fields)
    def record_event(self, *a, **k): return True


def _trigger_qty(lc, bar_close=100.4):
    eng = T.Engine(FakeSupabase(), datetime(2026, 11, 23, 15, 30, tzinfo=U), dry_run=True, log=lambda *a, **k: None,
                   fx_provider=lambda d: 1.099)
    eng.store, eng.captured, eng.notes_made = _TStore(), {}, []
    eng._apply = lambda lc, key, etype, to_state, updates, **k: (eng.captured.update(updates) or dict(lc, state=to_state, **updates))
    eng._note = lambda lc, bar, text, retry=False: (eng.notes_made.append(text) or lc)
    t = datetime(2026, 11, 23, 15, 0, tzinfo=U)
    bar = {'start': t, 'end': t + timedelta(minutes=15), 'o': lc['ref_price'], 'h': lc['ref_price'] * 1.002, 'l': lc['ref_price'] * 0.999,
           'c': lc['ref_price'] * 1.001, 'v': 1000, 'flag': 'ok'}
    eng._trigger(lc, bar)
    return eng


def _lc(ticker, market, currency, ref, atr, bucket='LIQ_HIGH'):
    return {'id': 1, 'ticker': ticker, 'market': market, 'currency': currency, 'state': 'WATCH', 'ref_price': ref, 'atr': atr,
            'invalidation_price': ref - 1.5 * atr, 'target_price': ref + 3 * atr, 'slippage_pct': sizing.slippage_for(bucket),
            'liquidity_bucket': bucket, 'zone_low': ref, 'zone_high': ref + 0.5 * atr, 'last_note': None,
            'created_at': '2026-11-23T14:40:00+00:00'}


def test_T_ed_E_stessa_quantita_frazionaria_per_un_titolo_usa_caro():
    lc = _lc('AMZN', 'USA', 'USD', 255.84, 9.59)
    eng = _trigger_qty(lc)
    e_sz = sizing.size_position(255.84, 9.59, lc['invalidation_price'], 1000.0, 1 / 1.099, COSTS_USA, 'LIQ_HIGH',
                                fractional=sizing.allows_fractional(E.market_for_ticker('AMZN')))
    assert eng.captured['quantity'] == e_sz['quantity'] and 0 < e_sz['quantity'] < 1
    assert 'quantita nulla' not in ' '.join(eng.notes_made)


def test_T_titolo_italiano_caro_non_entra_perche_le_azioni_sono_intere():
    lc = _lc('MCO.MI', 'EU', 'EUR', 487.11, 12.4)
    eng = _trigger_qty(lc)
    assert eng.captured == {} and any('quantita nulla' in n for n in eng.notes_made)


# ------------------------------------------------------------------ E: percorso reale di filter_signals
def _e_db(ticker, price, atr, sector='Technology'):
    now = datetime.now(U)
    db = FakeSupabase()
    db.tables = {
        'signals_raw': [{'id': 1, 'ticker': ticker, 'timestamp': (now - timedelta(minutes=5)).isoformat(), 'action': 'BUY', 'close_price': price,
                         'atr': atr, 'invalidation_price': price - 1.5 * atr, 'target_price': price + 3 * atr, 'confidence_level': 'HIGH',
                         'opportunity_type': 'event_driven', 'score_total': 3, 'data_quality_score': 1.0}],
        'signals_filtered': [],
        'costi_operazione': [dict(COSTS_USA, broker='Alpaca', mercato='USA', attivo=True),
                             dict(COSTS_EU, broker='Interactive Brokers', mercato='EU', attivo=True)],
        'capital_state': [{'capital_eur': 1000, 'created_at': now.isoformat()}],
        'fx_rates': [{'rate_date': (now - timedelta(days=1)).date().isoformat(), 'rate': 1.099, 'source': 'ECB'}],
        'ticker_sectors': [{'ticker': ticker, 'sector': sector, 'liquidity_bucket': 'LIQ_HIGH'}],
        'trade_lifecycle': [], 'portfolio_positions': [], 'signals_raw_dummy': [],
    }
    return db


def _run_e(monkeypatch, db, capsys):
    monkeypatch.setattr(E, 'supabase', db)
    monkeypatch.setattr(E, 'get_active_exposure_items', lambda: [])
    code = E.filter_signals()
    return code, capsys.readouterr().out


def _written(db):
    rows = db.inserts.get('signals_filtered') or []
    return rows[0] if rows else None


def test_E_approva_un_titolo_usa_caro_con_quantita_frazionaria(monkeypatch, capsys):
    db = _e_db('AMZN', 255.84, 9.59)
    code, out = _run_e(monkeypatch, db, capsys)
    row = _written(db)
    assert row is not None, out
    assert row['filtered_action'] == 'BUY' and row['filter_passed'] is True, (row, out)
    expected = sizing.size_position(255.84, 9.59, 255.84 - 1.5 * 9.59, 1000.0, 1 / 1.099, COSTS_USA, 'LIQ_HIGH', fractional=True)
    assert row['position_size_suggested'] == pytest.approx(expected['countervalue_eur'], abs=0.01)
    assert 0 < expected['quantity'] < 1


def test_E_blocca_un_titolo_italiano_caro_perche_intero(monkeypatch, capsys):
    db = _e_db('MCO.MI', 487.11, 12.4)
    code, out = _run_e(monkeypatch, db, capsys)
    row = _written(db)
    assert row is not None and row['filtered_action'] == 'HOLD' and row['filter_passed'] is False, (row, out)
    assert 'Quantita' in row['filter_reason'] and 'nulla' in row['filter_reason']
