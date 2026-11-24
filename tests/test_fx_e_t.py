"""fx_rates integrato in E e T: stesso tasso BCE per la stessa data, nessun ripiego, errore esplicito, quantita' coerenti."""
from datetime import date, datetime, timedelta, timezone

import pytest

import modulo_e_cost_filter as E
import modulo_t_state_machine as T
import sizing
from fakes import FakeSupabase
from fx import FxRateUnavailable, rate_for_date

U = timezone.utc
COSTS_USA = {'commissione_fissa': 0.0, 'commissione_percentuale': 0.0, 'spread_medio_percentuale': 0.0005, 'bollo_percentuale': 0.0,
             'tassazione_plusvalenza_percentuale': 0.26}


class _Q:
    def __init__(self, db): self.db, self.ref = db, None
    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def lt(self, col, v): self.ref = v; return self
    def order(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def execute(self):
        self.db.queries += 1
        class R: pass
        r = R()
        r.data = sorted([x for x in self.db.rows if x['rate_date'] < self.ref], key=lambda x: x['rate_date'], reverse=True)[:1]
        return r


class DB:
    def __init__(self, rates): self.rows = [{'rate_date': d, 'rate': v, 'source': 'ECB'} for d, v in rates.items()]; self.queries = 0
    def table(self, name): return _Q(self)


RATES = {'2026-11-13': 1.15, '2026-11-17': 1.16, '2026-11-18': 1.165}
SIG_TS = '2026-11-18T14:00:00+00:00'


# ---------------------------------------------------------------- E
def test_E_cambio_dalla_data_del_segnale_con_cache(monkeypatch):
    db = DB(RATES)
    monkeypatch.setattr(E, 'supabase', db)
    cache = {}
    a = E.fx_to_eur_for_signal({'timestamp': SIG_TS}, cache)
    b = E.fx_to_eur_for_signal({'timestamp': '2026-11-18T20:59:00+00:00'}, cache)
    assert a == b == pytest.approx(1 / 1.16) and db.queries == 1                 # per il 18 conta il tasso del 17; una lettura per data


def test_E_senza_tasso_solleva_errore_esplicito(monkeypatch):
    monkeypatch.setattr(E, 'supabase', DB({}))
    with pytest.raises(FxRateUnavailable):
        E.fx_to_eur_for_signal({'timestamp': SIG_TS}, {})


def test_E_e_T_non_hanno_piu_alcun_accesso_a_yahoo_per_il_cambio():
    import inspect
    for mod in (E, T):
        src = inspect.getsource(mod)
        assert 'get_usd_per_eur' not in src and 'EURUSD' not in src
    assert 'yf.' not in inspect.getsource(T) and 'yfinance' not in inspect.getsource(T)


# ---------------------------------------------------------------- T: ingresso
class _TStore:
    def __init__(self):
        self.updates = []
    def portfolio_cash(self): return 900.0
    def reserved_eur(self): return 0.0
    def reference_capital(self): return 1000.0
    def costs_for(self, market): return COSTS_USA
    def update(self, lc, fields): self.updates.append(fields); return dict(lc, **fields)
    def record_event(self, *a, **k): return True


def _lc(**kw):
    lc = {'id': 7, 'ticker': 'AAPL', 'market': 'USA', 'currency': 'USD', 'state': 'WATCH', 'ref_price': 100.0, 'atr': 2.0,
          'invalidation_price': 97.0, 'target_price': 106.0, 'slippage_pct': 0.0005, 'liquidity_bucket': 'LIQ_HIGH',
          'zone_low': 100.0, 'zone_high': 101.0, 'last_note': None, 'created_at': SIG_TS}
    return dict(lc, **kw)


def _bar():
    t = datetime(2026, 11, 18, 15, 0, tzinfo=U)
    return {'start': t, 'end': t + timedelta(minutes=15), 'o': 100.2, 'h': 100.6, 'l': 100.0, 'c': 100.4, 'v': 1000, 'flag': 'ok'}


def _engine(provider, now=datetime(2026, 11, 19, 10, 0, tzinfo=U)):
    eng = T.Engine(FakeSupabase(), now, dry_run=True, log=lambda *a, **k: None, fx_provider=provider)
    eng.store = _TStore()
    eng.captured, eng.notes_made, eng.applied = {}, [], []
    eng._apply = lambda lc, key, etype, to_state, updates, **k: (eng.captured.update(updates) or eng.applied.append(key)
                                                                or dict(lc, state=to_state, **updates))
    eng._note = lambda lc, bar, text, retry=False: (eng.notes_made.append(text) or lc)
    return eng


def test_T_ingresso_usa_il_tasso_della_data_del_segnale_e_la_stessa_quantita_di_E(monkeypatch):
    db = DB(RATES)
    monkeypatch.setattr(E, 'supabase', db)
    fx_e = E.fx_to_eur_for_signal({'timestamp': SIG_TS}, {})                       # E: tasso del 17 (per il segnale del 18)
    expected = sizing.size_position(100.0, 2.0, 97.0, 1000.0, fx_e, COSTS_USA, 'LIQ_HIGH', fractional=sizing.allows_fractional('USA'))
    eng = _engine(lambda d: rate_for_date(db, d).rate, now=datetime(2026, 11, 19, 10, 0, tzinfo=U))   # T un altro giorno (19), segnale del 18
    eng._trigger(_lc(), _bar())
    assert eng.captured['fx_eur_per_local'] == pytest.approx(fx_e)                  # stesso tasso di E, anche se il tasso del 18 e' ormai pubblicato
    assert eng.captured['quantity'] == expected['quantity'] > 0
    assert eng.fx_errors == []


def test_T_ingresso_senza_cambio_si_ferma_con_errore_esplicito():
    def provider(d): raise FxRateUnavailable('nessun tasso BCE USD precedente')
    eng = _engine(provider)
    eng._trigger(_lc(), _bar())
    assert eng.captured == {} and len(eng.fx_errors) == 1 and 'AAPL' in eng.fx_errors[0]
    assert any('cambio BCE non disponibile' in n for n in eng.notes_made)


def test_T_titoli_europei_non_usano_il_cambio():
    calls = []
    eng = _engine(lambda d: calls.append(d) or 1.16)
    eng._trigger(_lc(ticker='ENI.MI', market='EU', currency='EUR'), _bar())
    assert calls == [] and eng.captured['fx_eur_per_local'] == 1.0


# ---------------------------------------------------------------- T: uscita
def _active(**kw):
    lc = _lc(state='ACTIVE', quantity=5, entry_fill_price=100.0, fx_eur_per_local=1 / 1.16)
    return dict(lc, **kw)


def test_T_uscita_usa_il_cambio_del_giorno_dell_uscita():
    seen = []
    eng = _engine(lambda d: seen.append(d) or 1.165, now=datetime(2026, 11, 19, 10, 0, tzinfo=U))
    eng._start_exit(_active(), _bar(), 'STOP', 97.0, 1)
    assert seen == [date(2026, 11, 19)]
    assert eng.captured['pnl_eur'] == pytest.approx(5 * (97.0 * (1 - 0.0005) / 1.165 - 100.0 / 1.16), abs=0.01)


def test_T_uscita_senza_cambio_resta_pendente_senza_ripiego_sul_cambio_d_ingresso():
    def provider(d): raise FxRateUnavailable('tasso mancante')
    eng = _engine(provider)
    eng._start_exit(_active(), _bar(), 'STOP', 97.0, 1)
    assert eng.applied == [] and eng.captured == {} and len(eng.fx_errors) == 1
    assert any('USCITA RIMANDATA' in n for n in eng.notes_made)


# ---------------------------------------------------------------- executor portafoglio
class _RPC:
    def __init__(self): self.params = None
    def table(self, name):
        class Q:
            def select(s, *a, **k): return s
            def eq(s, *a, **k): return s
            def lte(s, *a, **k): return s
            def order(s, *a, **k): return s
            def limit(s, *a, **k): return s
            def execute(s):
                class R: data = [{'broker': 'Alpaca', 'mercato': 'USA', **COSTS_USA}]
                return R()
        return Q()
    def rpc(self, name, params):
        self.params = params
        class X:
            def execute(s):
                class R: data = {'tx_id': 1}
                return R()
        return X()


def _exit_lc():
    return _active(exit_price=97.0, exit_bar_end='2026-11-19T10:00:00+00:00', exit_bar_start='2026-11-19T09:45:00+00:00',
                   exit_detected_at='2026-11-19T10:01:00+00:00', exit_delay_minutes=1, raw_signal_id=1, signal_filtered_id=2)


def test_executor_uscita_usa_il_cambio_della_data_dell_uscita():
    sb = _RPC()
    ex = T.PortfolioExecutor(sb, fx_usd_per_eur=lambda d: {date(2026, 11, 19): 1.165}[d])
    res = ex.execute(_exit_lc(), {'intent_type': 'SELL', 'quantity': 5, 'idempotency_key': 'k'})
    assert res.ok and sb.params['p_fx_eur_per_local'] == pytest.approx(1 / 1.165)


def test_executor_uscita_senza_cambio_fallisce_con_errore_esplicito():
    sb = _RPC()
    def provider(d): raise FxRateUnavailable('tasso mancante')
    res = T.PortfolioExecutor(sb, fx_usd_per_eur=provider).execute(_exit_lc(), {'intent_type': 'SELL', 'quantity': 5, 'idempotency_key': 'k'})
    assert not res.ok and 'tasso mancante' in res.error and sb.params is None          # nessuna operazione registrata
    res = T.PortfolioExecutor(sb, fx_usd_per_eur=None).execute(_exit_lc(), {'intent_type': 'SELL', 'quantity': 5, 'idempotency_key': 'k'})
    assert not res.ok and sb.params is None                                              # provider assente = nessun ripiego


# ---------------------------------------------------------------- E: arresto senza cambio
def test_E_si_ferma_con_exit_code_1_se_manca_il_cambio_USD(monkeypatch, capsys):
    now = datetime.now(U)
    ts = (now - timedelta(minutes=5)).isoformat()
    db = FakeSupabase()
    db.tables = {
        'signals_raw': [{'id': 1, 'ticker': 'AAPL', 'timestamp': ts, 'action': 'BUY', 'close_price': 100.0, 'atr': 2.0,
                         'invalidation_price': 97.0, 'target_price': 106.0, 'confidence_level': 'HIGH', 'opportunity_type': 'event_driven',
                         'score_total': 3}],
        'signals_filtered': [],
        'costi_operazione': [dict(COSTS_USA, broker='Alpaca', mercato='USA', attivo=True)],
        'capital_state': [{'capital_eur': 1000, 'created_at': now.isoformat()}],
        'fx_rates': [],                                                              # nessun tasso BCE
        'ticker_sectors': [{'ticker': 'AAPL', 'sector': 'Technology', 'liquidity_bucket': 'LIQ_HIGH'}],
    }
    monkeypatch.setattr(E, 'supabase', db)
    code = E.filter_signals()
    out = capsys.readouterr().out
    assert code == 1 and 'cambio BCE non disponibile' in out and 'E SI FERMA' in out        # fermato per il cambio, non per altro
    assert db.inserts.get('signals_filtered') is None and db.prezzi == {}               # nessuna scrittura


# ---------------------------------------------------------------- provider di DEFAULT (23/11: 'Engine' object has no attribute 'sb')
def _default_engine(rates_rows):
    db = FakeSupabase()
    db.tables = {'fx_rates': rates_rows}
    eng = T.Engine(db, datetime(2026, 11, 23, 15, 30, tzinfo=U), dry_run=True, log=lambda *a, **k: None)      # NESSUN fx_provider esplicito
    return eng


def test_T_provider_di_default_legge_fx_rates_dal_client_dello_store():
    eng = _default_engine([{'rate_date': '2026-11-20', 'rate': 1.099, 'source': 'ECB'}])
    assert eng.usd_per_eur(date(2026, 11, 23)) == pytest.approx(1.099)


def test_T_provider_di_default_senza_tassi_solleva_errore_esplicito_non_attributeerror():
    eng = _default_engine([])
    with pytest.raises(FxRateUnavailable):
        eng.usd_per_eur(date(2026, 11, 23))


def test_T_ingresso_usa_con_provider_di_default_il_tasso_BCE():
    eng = _default_engine([{'rate_date': '2026-11-20', 'rate': 1.099, 'source': 'ECB'}])
    stub = _TStore()
    stub.sb = eng.store.sb                      # lo Store reale ha il client; lo stub lo espone come fa lo Store
    eng.store, eng.captured = stub, {}
    eng._apply = lambda lc, key, etype, to_state, updates, **k: (eng.captured.update(updates) or dict(lc, state=to_state, **updates))
    eng._note = lambda lc, bar, text, retry=False: lc
    eng._trigger(_lc(created_at='2026-11-23T14:40:00+00:00'), _bar())
    assert eng.captured['fx_eur_per_local'] == pytest.approx(1 / 1.099) and eng.captured['quantity'] > 0
