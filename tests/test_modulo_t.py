"""Passo 2 - Modulo T: barre non valide e buchi di dati. Nessun DB reale: lo Store e' sostituito da un doppione che registra."""
from datetime import datetime, timedelta, timezone

import modulo_t_state_machine as T
from fakes import FakeSupabase

U = timezone.utc


def dt(y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=U)


def row(start, o=10.2, h=10.4, l=10.1, c=10.3, v=1000, flag='ok'):
    return T.make_bar({'timestamp': start.isoformat(), 'open': o, 'high': h, 'low': l, 'close': c, 'volume': v,
                       'data_quality_flag': flag})


class StubStore:
    def __init__(self, bars):
        self._bars, self.events, self.updates = list(bars), {}, []

    def bars(self, ticker, from_start):
        return [b for b in self._bars if b['start'] >= from_start]

    def record_event(self, lc, key, etype, bar, reason, now, price=None):
        if (lc['id'], key) in self.events:
            return False
        self.events[(lc['id'], key)] = etype
        return True

    def update(self, lc, fields):
        self.updates.append(fields)
        return dict(lc, **fields)

    def approved_sells(self, ticker, since):
        return []


def engine(bars, now, dry_run=False):
    eng = T.Engine(FakeSupabase(), now, dry_run=dry_run, log=lambda *a, **k: None)
    eng.store = StubStore(bars)
    eng.applied, eng.exits = [], []
    eng._apply = lambda lc, key, etype, to_state, updates, **kw: (eng.applied.append((key, to_state)) or dict(lc, state=to_state, **updates))
    eng._start_exit = lambda lc, bar, reason, level, sessions, sell=None: (eng.exits.append((reason, level, bar['start'])) or lc)
    eng._trigger = lambda lc, bar: (eng.applied.append(('TRIGGER', 'x')) or lc)
    return eng


def watch_lc(**kw):
    lc = {'id': 1, 'ticker': 'ENI.MI', 'market': 'EU', 'state': 'WATCH', 'invalidation_price': 9.0, 'target_price': 13.0,
          'zone_low': 10.0, 'zone_high': 10.5, 'created_at': '2026-11-13T07:55:00+00:00',
          'valid_until': '2026-11-13T16:30:00+00:00', 'last_bar_start': None, 'last_note': None}
    return dict(lc, **kw)


def active_lc(**kw):
    lc = {'id': 2, 'ticker': 'ENI.MI', 'market': 'EU', 'state': 'ACTIVE', 'invalidation_price': 9.0, 'target_price': 13.0,
          'trigger_bar_end': '2026-11-13T08:15:00+00:00', 'planned_time_exit_date': '2026-11-19', 'entry_session_date': '2026-11-13',
          'last_bar_start': '2026-11-13T08:00:00+00:00', 'last_note': None, 'quantity': 10}
    return dict(lc, **kw)


NOW = dt(2026, 11, 13, 10, 0)
B = dt(2026, 11, 13, 8, 15)          # barra di prova (08:15-08:30 UTC), chiusa alle 10:00


def seq(start, n, **kw):
    return [row(start + timedelta(minutes=15 * i), **kw) for i in range(n)]


# ------------------------------------------------------------------ WATCH
def test_watch_invalidazione_su_barra_valida_scatta():
    eng = engine(seq(dt(2026, 11, 13, 8, 0), 2) + [row(B + timedelta(minutes=15), l=8.9)], NOW)
    eng.evaluate_watch(watch_lc())
    assert ('INVALIDATED:INV_TOCCATA', 'INVALIDATED') in eng.applied


def test_watch_barra_volume_zero_non_invalida_e_lascia_evento():
    bars = seq(dt(2026, 11, 13, 8, 0), 2) + [row(B + timedelta(minutes=15), o=8.9, h=8.9, l=8.9, c=8.9, v=0, flag='zero_volume')]
    eng = engine(bars, NOW)
    eng.evaluate_watch(watch_lc())
    assert not any(k.startswith('INVALIDATED') for k, _ in eng.applied)
    assert any(k.startswith('DATA_HOLD:WATCH_INV_TOCCATA') for _, k in eng.store.events) or \
        any(str(k).startswith('DATA_HOLD:WATCH_INV_TOCCATA') for k in (e[1] for e in eng.store.events))
    assert any(str(u.get('last_note', '')).startswith('DATI:') for u in eng.store.updates)
    assert eng.data_stats['trattenute'] == 1


def test_watch_barra_stale_non_invalida_anche_con_volume():
    eng = engine(seq(dt(2026, 11, 13, 8, 0), 2) + [row(B + timedelta(minutes=15), l=8.9, flag='stale')], NOW)
    eng.evaluate_watch(watch_lc())
    assert not any(k.startswith('INVALIDATED') for k, _ in eng.applied)


def test_watch_barra_non_valida_non_fa_scattare_il_trigger():
    bars = [row(dt(2026, 11, 13, 8, 0), o=10.2, h=10.3, l=10.1, c=10.2, v=0, flag='zero_volume')]     # in zona ma senza scambi
    eng = engine(bars, dt(2026, 11, 13, 8, 20))
    eng.evaluate_watch(watch_lc())
    assert ('TRIGGER', 'x') not in eng.applied


# ------------------------------------------------------------------ ACTIVE
def test_active_stop_su_barra_valida_esce():
    eng = engine([row(dt(2026, 11, 13, 8, 15), l=8.8)], NOW)
    eng.evaluate_active(active_lc())
    assert eng.exits and eng.exits[0][0] == 'STOP' and eng.exits[0][1] == 9.0


def test_active_stop_su_barra_volume_zero_non_esce():
    eng = engine([row(dt(2026, 11, 13, 8, 15), o=8.8, h=8.8, l=8.8, c=8.8, v=0, flag='zero_volume')], NOW)
    eng.evaluate_active(active_lc())
    assert eng.exits == []
    assert any(k[1].startswith('DATA_HOLD:EXIT_STOP') for k in eng.store.events)


def test_active_target_su_barra_non_ok_non_esce():
    eng = engine([row(dt(2026, 11, 13, 8, 15), h=13.5, flag='stale')], NOW)
    eng.evaluate_active(active_lc())
    assert eng.exits == [] and eng.data_stats['trattenute'] == 1


def test_active_dopo_la_barra_invalida_una_barra_valida_decide():
    bars = [row(dt(2026, 11, 13, 8, 15), o=8.8, h=8.8, l=8.8, c=8.8, v=0, flag='zero_volume'), row(dt(2026, 11, 13, 8, 30), l=8.7)]
    eng = engine(bars, NOW)
    eng.evaluate_active(active_lc())
    assert [e[0] for e in eng.exits] == ['STOP'] and eng.exits[0][2] == dt(2026, 11, 13, 8, 30)


def test_active_tempo_rinviato_se_l_ultima_barra_e_non_valida():
    last = dt(2026, 11, 13, 16, 15)
    bars = [row(last, v=0, flag='zero_volume'), row(dt(2026, 11, 16, 8, 0), o=10.6)]
    lc = active_lc(planned_time_exit_date='2026-11-13', entry_session_date='2026-11-12', last_bar_start='2026-11-13T16:00:00+00:00',
                   trigger_bar_end='2026-11-12T10:00:00+00:00')
    eng = engine(bars, dt(2026, 11, 16, 8, 20))
    eng.evaluate_active(lc)
    assert any(k[1].startswith('DATA_HOLD:EXIT_TEMPO') for k in eng.store.events)
    assert [(e[0], e[1]) for e in eng.exits] == [('TEMPO', 10.6)]          # alla prima barra valida successiva, prezzo di apertura


def test_active_tempo_su_barra_valida_resta_invariato():
    last = dt(2026, 11, 13, 16, 15)
    eng = engine([row(last, c=10.7)], dt(2026, 11, 13, 16, 40))
    lc = active_lc(planned_time_exit_date='2026-11-13', entry_session_date='2026-11-12', last_bar_start='2026-11-13T16:00:00+00:00',
                   trigger_bar_end='2026-11-12T10:00:00+00:00')
    eng.evaluate_active(lc)
    assert [(e[0], e[1]) for e in eng.exits] == [('TEMPO', 10.7)]


def test_nota_dati_si_cancella_alla_prima_barra_valida():
    eng = engine([row(dt(2026, 11, 13, 8, 15))], NOW)
    eng.evaluate_active(active_lc(last_note='DATI: EXIT_STOP su candela 08:00 UTC non valida'))
    assert any(u.get('last_note', 'x') is None for u in eng.store.updates)


# ------------------------------------------------------------------ BUCHI
def _gap_bars():
    return [row(dt(2026, 11, 13, 8, 0)), row(dt(2026, 11, 13, 8, 15)), row(dt(2026, 11, 13, 8, 45))]     # manca 08:30


def test_buco_recente_blocca_la_valutazione_prima_del_buco():
    eng = engine(_gap_bars(), dt(2026, 11, 13, 9, 10))        # il buco finisce alle 08:45: 25 minuti fa
    got = eng._bars_after(watch_lc(), dt(2026, 11, 13, 7, 55))
    assert [b['start'].strftime('%H:%M') for b in got] == ['08:00', '08:15']
    assert eng.data_stats['buchi_in_attesa'] == 1 and not eng.store.events


def test_buco_oltre_la_pazienza_e_assenza_alla_fonte_con_evento_una_volta():
    eng = engine(_gap_bars(), dt(2026, 11, 13, 10, 0))        # 75 minuti dopo
    got = eng._bars_after(watch_lc(), dt(2026, 11, 13, 7, 55))
    assert [b['start'].strftime('%H:%M') for b in got] == ['08:00', '08:15', '08:45']
    assert list(eng.store.events) == [(1, 'DATA_GAP:2026-11-13T08:30:00+00:00')]       # solo il buco INTERNO, non la coda
    eng._bars_after(watch_lc(), dt(2026, 11, 13, 7, 55))
    assert len(eng.store.events) == 1                         # idempotente


def test_buco_in_coda_si_attende_senza_registrare():
    eng = engine(seq(dt(2026, 11, 13, 8, 0), 2), dt(2026, 11, 13, 10, 0))              # A non ha scritto nulla dopo le 08:15
    got = eng._bars_after(watch_lc(), dt(2026, 11, 13, 7, 55))
    assert [b['start'].strftime('%H:%M') for b in got] == ['08:00', '08:15'] and eng.store.events == {}


def test_stop_dopo_un_buco_in_attesa_non_viene_valutato():
    bars = [row(dt(2026, 11, 13, 8, 15)), row(dt(2026, 11, 13, 8, 45), l=8.5)]       # manca 08:30
    eng = engine(bars, dt(2026, 11, 13, 9, 10))
    eng.evaluate_active(active_lc())
    assert eng.exits == []


def test_buco_colmato_da_A_viene_valutato_in_ordine():
    full = _gap_bars() + [row(dt(2026, 11, 13, 8, 30), l=8.6)]                       # A ha ricoperto la barra mancante
    eng = engine(full, dt(2026, 11, 13, 9, 10))
    eng.evaluate_active(active_lc())
    assert [(e[0], e[2]) for e in eng.exits] == [('STOP', dt(2026, 11, 13, 8, 30))]    # lo stop sta nella barra ricoperta


def test_barre_gia_valutate_non_si_rivalutano():
    eng = engine(seq(dt(2026, 11, 13, 8, 0), 4), dt(2026, 11, 13, 9, 30))
    got = eng._bars_after(watch_lc(last_bar_start='2026-11-13T08:30:00+00:00'), dt(2026, 11, 13, 7, 55))
    assert [b['start'].strftime('%H:%M') for b in got] == ['08:45']


def test_barra_non_chiusa_e_fuori_calendario_ignorate():
    bars = seq(dt(2026, 11, 13, 7, 45), 1) + seq(dt(2026, 11, 13, 8, 0), 2)           # 07:45 pre-apertura
    eng = engine(bars, dt(2026, 11, 13, 8, 20))                                       # 08:15 non ancora chiusa
    got = eng._bars_after(watch_lc(created_at='2026-11-13T07:30:00+00:00'), dt(2026, 11, 13, 7, 30))
    assert [b['start'].strftime('%H:%M') for b in got] == ['08:00']


def test_dry_run_non_scrive():
    bars = [row(dt(2026, 11, 13, 8, 15), o=8.8, h=8.8, l=8.8, c=8.8, v=0, flag='zero_volume')]
    eng = engine(bars, NOW, dry_run=True)
    eng.evaluate_active(active_lc())
    assert eng.store.events == {} and eng.store.updates == []


def test_pazienza_sui_buchi_massimo_30_minuti():
    assert T.GAP_GRACE_MINUTES <= 30
    bars = _gap_bars()                                        # manca 08:30 (fine 08:45)
    eng = engine(bars, dt(2026, 11, 13, 9, 14))               # 29 minuti dalla fine del buco: si attende
    assert [b['start'].strftime('%H:%M') for b in eng._bars_after(watch_lc(), dt(2026, 11, 13, 7, 55))] == ['08:00', '08:15']
    eng = engine(bars, dt(2026, 11, 13, 9, 16))               # 31 minuti: assenza alla fonte, si prosegue con evento
    assert [b['start'].strftime('%H:%M') for b in eng._bars_after(watch_lc(), dt(2026, 11, 13, 7, 55))] == ['08:00', '08:15', '08:45']
    assert any(k[1].startswith('DATA_GAP') for k in eng.store.events)


# ------------------------------------------------------------------ segnali scaduti
class _SigStore(StubStore):
    def __init__(self, sigs):
        super().__init__([]); self.sigs, self.created = sigs, []
    def new_approved_signals(self, since): return self.sigs
    def raw(self, rid): return {'close_price': 100.0, 'atr': 2.0}
    def open_ticker(self, ticker): return None
    def insert_lifecycle(self, row): self.created.append(row); return dict(row, id=len(self.created))
    def _t(self, name):
        class Q:
            def insert(s, *a, **k): return s
            def execute(s): return None
        return Q()


def _sig(rid, ts, action='BUY'):
    return {'id': rid, 'raw_signal_id': rid, 'ticker': 'ENI.MI', 'filtered_action': action, 'timestamp': ts, 'invalidation_price': 97.0,
            'target_price': 106.0, 'slippage_applied_percent': 0.0005, 'liquidity_bucket': 'LIQ_HIGH'}


def test_segnale_scaduto_non_rientra_nel_ciclo_ordinario():
    eng = engine([], dt(2026, 11, 16, 10, 0))
    eng.store = _SigStore([_sig(1, '2026-11-12T10:00:00+00:00'),            # giovedi' scorso: scaduto da giorni
                           _sig(2, '2026-11-16T09:30:00+00:00')])           # di oggi: valido
    eng.executor = type('E', (), {'name': 'NOT_LINKED'})()
    eng.create_lifecycles()
    assert [r['raw_signal_id'] for r in eng.store.created] == [2]
    assert eng.data_stats['scaduti_ignorati'] == 1
    assert eng.c['n_skipped'] == 0 and eng.c['n_signals_new'] == 1 and not eng.notes   # nessun rumore ne' log per lo scaduto


def test_segnale_sell_ignorato_senza_contarlo_come_nuovo():
    eng = engine([], dt(2026, 11, 16, 10, 0))
    eng.store = _SigStore([_sig(3, '2026-11-16T09:30:00+00:00', 'SELL')])
    eng.create_lifecycles()
    assert eng.store.created == [] and eng.data_stats['sell_ignorati'] == 1 and eng.c['n_signals_new'] == 0
