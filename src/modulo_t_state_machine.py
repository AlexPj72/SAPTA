"""
Modulo T - State machine operativa (PAPER). FASE 4.

Prende i segnali BUY approvati da E (signals_filtered.filter_passed) e ne governa il ciclo di vita:

    WATCH -> ENTRY_PENDING -> ACTIVE -> EXIT_PENDING -> EXIT        (ingresso e uscita)
    WATCH -> INVALIDATED | EXPIRED                                  (finito senza ingresso)

Regole: specifica v0.3 (D1-D10). Si valutano SOLO candele 15m chiuse; l'ingresso avviene alla chiusura della candela
(fill = C + slippage); l'evento avverso vince sempre nella stessa candela; nessuna volonta' di inseguire il prezzo.

NESSUNA operazione sui portafogli (FASE 4): le intenzioni di operazione (trade_intents) vengono registrate con chiave
di idempotenza deterministica ma eseguite dall'executor NOT_LINKED. In FASE 5 si sostituisce l'executor.

NOTIFICHE (FASE 6, solo COMPRA ORA e VENDI ORA): la macchina a stati NON invia nulla. Dopo ogni run, un livello separato
(sync_alerts/deliver_alerts) guarda gli eventi TRIGGER e EXIT_SIGNAL:* gia' registrati e, per ciascuno, crea UNA riga
per canale in trade_alerts (UNIQUE) e la consegna. Un errore di invio non tocca mai lo stato dei cicli: l'alert resta
FAILED e si ritenta (max 5 volte) finche' e' ancora utile (COMPRA ORA 30 min, VENDI ORA 4 ore), poi EXPIRED.

Idempotenza: ogni transizione ha una event_key deterministica (UNIQUE per ciclo); un ciclo per segnale grezzo;
un solo ciclo aperto per titolo. Rilanciare T, o ripetere un run interrotto a meta', non duplica mai nulla.
"""
import re
import argparse
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import notifications
from market_calendar import (BAR_MINUTES, CalendarNotVerified, currency_of, is_regular_bar, last_regular_bar_start,

                             local_date, market_of, next_session_close, nth_session_date)


def _fromiso(s):
    """fromisoformat tollerante: Python <3.11 accetta solo 3 o 6 cifre di frazione."""
    s = str(s).replace('Z', '+00:00')
    s = re.sub(r'\.(\d{1,6})\d*', lambda m: '.' + m.group(1).ljust(6, '0'), s, count=1)
    return datetime.fromisoformat(s)


# ---------------------------------------------------------------- parametri (specifica v0.3)
ZONE_ATR_FRACTION = 0.5            # zona di ingresso: da R a R + 0,5*ATR
STOP_ATR_MULT, TARGET_ATR_MULT = 1.5, 3.0   # invariati (Modulo B)
MAX_HOLD_SESSIONS = 5              # REGOLA PROVVISORIA di paper trading, NON calibrata dal backtest (D5): costante configurabile
FRESHNESS_MINUTES = 30             # regola F: un ingresso e' azionabile solo se la candela e' fresca
EXPIRY_GRACE_MINUTES = 20          # scadenza per tempo: aspetta che arrivino le ultime candele (Borsa Italiana in ritardo)
BAR_CLOSED_GRACE_SECONDS = 60      # una candela e' chiusa se la sua fine + 60 s e' passata
COHERENCE_TOLERANCE = 0.005        # R-INV = 1,5A e TGT-R = 3A, tolleranza 0,5% del prezzo
RISK_PER_TRADE_PERCENT = 0.01      # stessa formula di Modulo E (1% del capitale / distanza dallo stop)
PORTFOLIO_CODE = 'PORTAFOGLIO_AI'   # FASE 5: il portafoglio virtuale gestito in automatico dall'IA (solo paper)
EXECUTOR_MODE = 'PORTFOLIO'         # FASE 5: le intenzioni diventano operazioni virtuali sul portafoglio (nessun ordine reale)
SIGNAL_LOOKBACK_DAYS = 3
ALERT_MAX_ATTEMPTS = 5
ALERT_MAX_AGE_MINUTES = {'COMPRA ORA': 30, 'VENDI ORA': 240}   # oltre, l'alert non e' piu' utile: EXPIRED
ALERT_EVENT_KINDS = {'TRIGGER': 'COMPRA ORA', 'EXIT_SIGNAL:STOP': 'VENDI ORA', 'EXIT_SIGNAL:TARGET': 'VENDI ORA',
                     'EXIT_SIGNAL:TEMPO': 'VENDI ORA', 'EXIT_SIGNAL:SEGNALE': 'VENDI ORA'}
CHANNELS = ('TELEGRAM', 'EMAIL')

OPEN_STATES = ('WATCH', 'ENTRY_PENDING', 'ACTIVE', 'EXIT_PENDING')
ACTION_LABEL = {'WATCH': 'ATTENDI', 'ENTRY_PENDING': 'COMPRA ORA', 'ACTIVE': 'TIENI', 'EXIT_PENDING': 'VENDI ORA',
                'EXIT': 'VENDI ORA', 'INVALIDATED': 'NON COMPRARE', 'EXPIRED': 'NON COMPRARE'}


def _iso(dt):
    return dt.astimezone(timezone.utc).isoformat() if dt else None


def parse_ts(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return _fromiso(value).astimezone(timezone.utc)


# ---------------------------------------------------------------- funzioni pure
def build_levels(ref, atr):
    return {'zone_low': ref, 'zone_high': ref + ZONE_ATR_FRACTION * atr,
            'invalidation_price': ref - STOP_ATR_MULT * atr, 'target_price': ref + TARGET_ATR_MULT * atr}


def levels_are_coherent(ref, atr, inv, tgt):
    """Controllo di coerenza alla creazione (spec §1): se i livelli di B/E non tornano, il ciclo non si crea."""
    tol = COHERENCE_TOLERANCE * ref
    return abs((ref - inv) - STOP_ATR_MULT * atr) <= tol and abs((tgt - ref) - TARGET_ATR_MULT * atr) <= tol


def position_size(fill_local, invalidation_price, capital_local, risk_percent=RISK_PER_TRADE_PERCENT):
    """Stessa formula di Modulo E (calculate_position_size): rischio massimo / distanza dallo stop."""
    stop_distance = abs(fill_local - invalidation_price)
    if stop_distance <= 0:
        return None
    return capital_local * risk_percent / stop_distance


def make_bar(row):
    """Riga di prezzi (dict) -> candela normalizzata."""
    start = parse_ts(row['timestamp'])
    return {'start': start, 'end': start + timedelta(minutes=BAR_MINUTES), 'o': float(row['open']), 'h': float(row['high']),
            'l': float(row['low']), 'c': float(row['close']), 'v': int(row.get('volume') or 0),
            'flag': row.get('data_quality_flag')}


def bar_payload(bar):
    return {'o': bar['o'], 'h': bar['h'], 'l': bar['l'], 'c': bar['c'], 'v': bar['v'], 'flag': bar['flag'],
            'start': _iso(bar['start']), 'end': _iso(bar['end'])}


def entry_eligible(bar, now):
    """Un ingresso richiede: candela con scambi (volume > 0), dato 'ok' e candela fresca (regola F)."""
    if bar['v'] <= 0:
        return False, 'candela senza scambi (volume 0): ingresso non consentito'
    if bar['flag'] != 'ok':
        return False, f"dato non affidabile ({bar['flag']}): ingresso non consentito"
    if bar['end'] < now - timedelta(minutes=FRESHNESS_MINUTES):
        return False, 'candela non piu fresca (> 30 min): un ingresso non puo essere retroattivo'
    return True, None


def watch_rule(lc, bar):
    """Regole W2-W6 (spec §4.1) su UNA candela chiusa. W1 (scadenza) e' gestita fuori. L'evento avverso vince sempre."""
    if bar['l'] <= lc['invalidation_price']:
        return 'INVALIDATED', 'INV_TOCCATA'
    if bar['h'] >= lc['target_price']:
        return 'INVALIDATED', 'TARGET_MANCATO'
    if lc['zone_low'] <= bar['c'] <= lc['zone_high']:
        return 'IN_ZONE', None
    if bar['c'] > lc['zone_high']:
        return 'EXTENDED', None
    return 'WAIT', None


def active_rule(lc, bar):
    """Regole A1-A4 (spec §4.2) su UNA candela dopo l'ingresso. Ritorna (reason, prezzo_livello) o None."""
    inv, tgt = lc['invalidation_price'], lc['target_price']
    if bar['o'] <= inv:
        return 'STOP', bar['o']                 # A1: gap sotto lo stop -> prezzo di apertura (peggiore)
    if bar['l'] <= inv:
        return 'STOP', inv                      # A2/A3: stop e target nella stessa candela -> vince lo stop
    if bar['h'] >= tgt:
        return 'TARGET', tgt                    # A4: mai migliore del target, anche se la candela apre sopra
    return None


def sell_fill(price, slippage):
    return price * (1 - slippage)


def pnl(lc, exit_fill, exit_fx):
    qty, entry = float(lc['quantity']), float(lc['entry_fill_price'])
    pnl_eur = qty * (exit_fill * exit_fx - entry * float(lc['fx_eur_per_local']))
    return round(pnl_eur, 2), round((exit_fill - entry) / entry * 100, 4)


# ---------------------------------------------------------------- executor (FASE 5 sostituisce questo)
class ExecResult:
    def __init__(self, ok, status, tx_id=None, error=None):
        self.ok, self.status, self.tx_id, self.error = ok, status, tx_id, error


class NotLinkedExecutor:
    """FASE 4: nessuna operazione di portafoglio. L'intenzione resta registrata come NOT_LINKED."""
    name = 'NOT_LINKED'

    def execute(self, lc, intent):
        return ExecResult(True, 'NOT_LINKED')


class PortfolioExecutor:
    """FASE 5: esegue l'intenzione sul portafoglio PAPER con la funzione SQL atomica e idempotente
    portfolio_execute_trade (mai ordini reali). I cicli NOT_LINKED (nati prima della FASE 5) restano non collegati."""
    name = 'PORTFOLIO'

    def __init__(self, sb, fx_usd_per_eur=None):
        self.sb, self.fx_usd_per_eur, self._costs = sb, fx_usd_per_eur, None

    def _fees(self, market, value_eur):
        if self._costs is None:
            rows = self.sb.table('costi_operazione').select('*').eq('attivo', True).execute().data or []
            by = {('Alpaca', 'USA'): 'USA', ('Interactive Brokers', 'EU'): 'EU'}
            self._costs = {by[(r['broker'], r['mercato'])]: r for r in rows if (r['broker'], r['mercato']) in by}
        c = self._costs.get(market)
        if not c:
            raise RuntimeError(f'costi di operazione mancanti per il mercato {market}')
        return round(float(c['commissione_fissa']) + value_eur * (float(c['commissione_percentuale']) + float(c['bollo_percentuale'])), 2)

    def _ai_decision_id(self, lc):
        try:
            sig = self.sb.table('signals_filtered').select('timestamp').eq('id', lc['signal_filtered_id']).execute().data
            if not sig:
                return None
            r = self.sb.table('ai_agent_decisions').select('id').eq('ticker', lc['ticker']).lte('timestamp', sig[0]['timestamp']) \
                .order('timestamp', desc=True).limit(1).execute().data
            return r[0]['id'] if r else None
        except Exception:
            return None

    def execute(self, lc, intent):
        if lc.get('sync_status') == 'NOT_LINKED':
            return ExecResult(True, 'NOT_LINKED')
        try:
            buy = intent['intent_type'] == 'BUY'
            qty = float(intent['quantity'])
            slip = float(lc.get('slippage_pct') or 0)
            if buy:
                price, fx = float(lc['entry_fill_price']), float(lc['fx_eur_per_local'])
                ref = price / (1 + slip)
                at, bar_start, delay = lc['trigger_bar_end'], lc['trigger_bar_start'], lc.get('trigger_delay_minutes')
            else:
                price, fx = float(lc['exit_price']), float(lc['fx_eur_per_local'])
                if lc['currency'] == 'USD' and self.fx_usd_per_eur:
                    u = self.fx_usd_per_eur()
                    fx = (1.0 / u) if u else fx
                ref = price / (1 - slip) if slip < 1 else price
                at, bar_start, delay = lc['exit_bar_end'], lc['exit_bar_start'], lc.get('exit_delay_minutes')
            fees = self._fees(lc['market'], qty * price * fx)
            params = {'p_code': PORTFOLIO_CODE, 'p_ticker': lc['ticker'], 'p_side': intent['intent_type'], 'p_quantity': qty,
                      'p_price_local': price, 'p_executed_at': at, 'p_idempotency_key': intent['idempotency_key'],
                      'p_market': lc['market'], 'p_currency': lc['currency'], 'p_fx_eur_per_local': fx, 'p_fees_eur': fees,
                      'p_price_reference': ref, 'p_slippage_pct': slip, 'p_source_type': 'AI_AGENT', 'p_lifecycle_id': lc['id'],
                      'p_signal_raw_id': lc['raw_signal_id'], 'p_signal_filtered_id': lc['signal_filtered_id'],
                      'p_ai_decision_id': self._ai_decision_id(lc), 'p_bar_start': bar_start, 'p_data_delay_minutes': delay}
            out = self.sb.rpc('portfolio_execute_trade', params).execute().data
            if isinstance(out, list):
                out = out[0] if out else {}
            return ExecResult(True, 'DONE', tx_id=(out or {}).get('tx_id'))
        except Exception as e:
            return ExecResult(False, 'FAILED', error=str(e)[:400])


def intent_key(lc_id, intent_type):
    # identico a portfolio_idempotency_key(code, lifecycle_id, evento) in SQL: deterministico, mai casuale
    return f"{PORTFOLIO_CODE}:LC{lc_id}:{intent_type}"


# ---------------------------------------------------------------- accesso ai dati
def _is_unique_violation(exc):
    m = str(exc).lower()
    return '23505' in m or 'duplicate key' in m or 'unique constraint' in m


class Store:
    def __init__(self, sb):
        self.sb = sb

    def _t(self, name):
        return self.sb.table(name)

    def new_approved_signals(self, since):
        """Segnali approvati da E, canonici (con raw_signal_id), non ancora trasformati in ciclo."""
        rows = self._t('signals_filtered').select('*').eq('filter_passed', True).in_('filtered_action', ['BUY', 'SELL']) \
            .gte('timestamp', _iso(since)).order('timestamp').execute().data or []
        rows = [r for r in rows if r.get('raw_signal_id') is not None]
        have = {r['raw_signal_id'] for r in (self._t('trade_lifecycle').select('raw_signal_id').execute().data or [])}
        return [r for r in rows if r['raw_signal_id'] not in have]

    def raw(self, raw_id):
        r = self._t('signals_raw').select('*').eq('id', raw_id).execute().data or []
        return r[0] if r else None

    def open_lifecycles(self):
        return self._t('trade_lifecycle').select('*').in_('state', list(OPEN_STATES)).order('id').execute().data or []

    def open_ticker(self, ticker):
        r = self._t('trade_lifecycle').select('id,state').eq('ticker', ticker).in_('state', list(OPEN_STATES)).execute().data or []
        return r[0] if r else None

    def insert_lifecycle(self, row):
        return self._t('trade_lifecycle').insert(row).execute().data[0]

    def bars(self, ticker, from_start):
        rows = self._t('prezzi').select('*').eq('ticker', ticker).eq('interval', '15m') \
            .gte('timestamp', _iso(from_start)).order('timestamp').execute().data or []
        return [make_bar(r) for r in rows]

    def approved_sells(self, ticker, since):
        rows = self._t('signals_filtered').select('*').eq('ticker', ticker).eq('filter_passed', True) \
            .eq('filtered_action', 'SELL').gte('timestamp', _iso(since)).order('timestamp').execute().data or []
        return [r for r in rows if r.get('raw_signal_id') is not None]

    def portfolio_cash(self):
        r = self._t('portfolios').select('cash_eur').eq('code', PORTFOLIO_CODE).execute().data or []
        return float(r[0]['cash_eur']) if r else None

    def reserved_eur(self):
        """Capitale 'prenotato' da cicli con ingresso deciso ma non ancora nel portafoglio (FASE 4: tutti i cicli ACTIVE)."""
        rows = self._t('trade_lifecycle').select('countervalue_eur,state,sync_status').in_('state', ['ENTRY_PENDING', 'ACTIVE', 'EXIT_PENDING']).execute().data or []
        if EXECUTOR_MODE == 'PORTFOLIO':     # con il portafoglio reale la cassa e' gia' scalata: si riservano solo gli ingressi non ancora registrati
            return sum(float(r['countervalue_eur'] or 0) for r in rows if r['state'] == 'ENTRY_PENDING' and r['sync_status'] in ('PENDING', 'FAILED'))
        return sum(float(r['countervalue_eur'] or 0) for r in rows if r['sync_status'] != 'DONE')

    def invested_eur(self):
        """Costo delle posizioni aperte del portafoglio (per dimensionare sul capitale totale, non solo sulla cassa libera)."""
        pf = self._t('portfolios').select('id').eq('code', PORTFOLIO_CODE).execute().data or []
        if not pf:
            return 0.0
        rows = self._t('portfolio_positions').select('cost_basis_eur').eq('portfolio_id', pf[0]['id']).eq('status', 'OPEN').execute().data or []
        return sum(float(r['cost_basis_eur'] or 0) for r in rows)

    def intent(self, lc_id, intent_type):
        r = self._t('trade_intents').select('*').eq('lifecycle_id', lc_id).eq('intent_type', intent_type).execute().data or []
        return r[0] if r else None

    def ensure_intent(self, lc, intent_type, qty, ref_price, status):
        cur = self.intent(lc['id'], intent_type)
        if cur:
            return cur
        row = {'lifecycle_id': lc['id'], 'intent_type': intent_type, 'portfolio_code': PORTFOLIO_CODE, 'ticker': lc['ticker'],
               'quantity': qty, 'ref_price': ref_price, 'idempotency_key': intent_key(lc['id'], intent_type), 'status': status}
        try:
            return self._t('trade_intents').insert(row).execute().data[0]
        except Exception as e:
            if _is_unique_violation(e):
                return self.intent(lc['id'], intent_type)
            raise

    def update_intent(self, intent_id, fields):
        fields = dict(fields, updated_at=_iso(datetime.now(timezone.utc)))
        self._t('trade_intents').update(fields).eq('id', intent_id).execute()

    def pending_lifecycles(self):
        return self._t('trade_lifecycle').select('*').in_('state', ['ENTRY_PENDING', 'EXIT_PENDING']).order('id').execute().data or []

    def transition(self, lc, event_key, event_type, to_state, updates, bar=None, reason=None, price=None, delay=None, now=None):
        """Transizione idempotente: prima l'evento (UNIQUE per ciclo+chiave), poi l'aggiornamento condizionato allo
        stato di partenza. Se l'evento esiste gia' (run interrotto), si riusano i valori salvati nel suo payload."""
        updates = dict(updates, state=to_state, action_label=ACTION_LABEL[to_state], updated_at=_iso(now or datetime.now(timezone.utc)))
        ev = {'lifecycle_id': lc['id'], 'event_key': event_key, 'event_type': event_type, 'from_state': lc['state'], 'to_state': to_state,
              'reason': reason, 'bar_start': _iso(bar['start']) if bar else None, 'bar_end': _iso(bar['end']) if bar else None,
              'price': price, 'detected_at': _iso(now or datetime.now(timezone.utc)), 'data_delay_minutes': delay,
              'payload': {'updates': json.loads(json.dumps(updates, default=str)), 'bar': bar_payload(bar) if bar else None}}
        try:
            self._t('trade_events').insert(ev).execute()
        except Exception as e:
            if not _is_unique_violation(e):
                raise
            old = self._t('trade_events').select('*').eq('lifecycle_id', lc['id']).eq('event_key', event_key).execute().data[0]
            updates = old['payload']['updates']          # stessi valori del primo tentativo
        res = self._t('trade_lifecycle').update(updates).eq('id', lc['id']).eq('state', lc['state']).execute().data or []
        if res:
            return res[0]
        cur = self._t('trade_lifecycle').select('*').eq('id', lc['id']).execute().data[0]
        return cur                                         # gia' transitato (altro run): niente da fare

    def update(self, lc, fields):
        self._t('trade_lifecycle').update(dict(fields, updated_at=_iso(datetime.now(timezone.utc)))).eq('id', lc['id']).execute()
        return dict(lc, **fields)

    def recent_alert_events(self, since):
        return self._t('trade_events').select('*').in_('event_key', list(ALERT_EVENT_KINDS)).gte('detected_at', _iso(since)).order('id').execute().data or []

    def lifecycle(self, lc_id):
        r = self._t('trade_lifecycle').select('*').eq('id', lc_id).execute().data or []
        return r[0] if r else None

    def alerts_of(self, lifecycle_ids):
        if not lifecycle_ids:
            return []
        return self._t('trade_alerts').select('lifecycle_id,event_key,channel').in_('lifecycle_id', list(lifecycle_ids)).execute().data or []

    def insert_alert(self, row):
        try:
            return self._t('trade_alerts').insert(row).execute().data[0]
        except Exception as e:
            if _is_unique_violation(e):
                return None                        # gia' presente: nessun doppione
            raise

    def open_alerts(self):
        return self._t('trade_alerts').select('*').in_('status', ['PENDING', 'FAILED']).order('id').execute().data or []

    def update_alert(self, alert_id, fields):
        self._t('trade_alerts').update(dict(fields, updated_at=_iso(datetime.now(timezone.utc)))).eq('id', alert_id).execute()

    def run_start(self, mode, dry_run, now):
        if dry_run:
            return None
        return self._t('trade_runs').insert({'started_at': _iso(datetime.now(timezone.utc)), 'status': 'RUNNING', 'mode': mode,
                                             'dry_run': dry_run, 'now_ts': _iso(now)}).execute().data[0]['id']

    def run_finish(self, run_id, status, counters, error=None, notes=None):
        if run_id is None:
            return
        self._t('trade_runs').update(dict(counters, status=status, finished_at=_iso(datetime.now(timezone.utc)),
                                          error=error, notes=notes)).eq('id', run_id).execute()


def get_usd_per_eur():
    """Dollari per 1 EUR (Yahoo EURUSD=X): cambio indicativo, non real-time. None se non disponibile."""
    try:
        import yfinance as yf
        hist = yf.Ticker('EURUSD=X').history(period='5d')['Close'].dropna()
        fx = float(hist.iloc[-1])
        return fx if 0.5 < fx < 2.0 else None
    except Exception as e:
        print(f"⚠️ cambio EURUSD non disponibile: {e}")
        return None


# ---------------------------------------------------------------- logica del ciclo
class Engine:
    def __init__(self, sb, now, executor=None, dry_run=False, fx_provider=get_usd_per_eur, log=print, senders=None):
        self.store, self.now, self.dry_run, self.log = Store(sb), now, dry_run, log
        # senders: {'TELEGRAM': fn(subject, text) -> (stato, errore), 'EMAIL': ...}: iniettabili nei test
        self.senders = senders or {'TELEGRAM': lambda subject, text: notifications.send_telegram(text),
                                   'EMAIL': lambda subject, text: notifications.send_email(subject, text)}
        self.alert_stats = {'enqueued': 0, 'sent': 0, 'failed': 0, 'expired': 0, 'given_up': 0, 'not_configured': 0}
        self.executor = executor or NotLinkedExecutor()
        self.fx_provider, self._fx = fx_provider, 'unset'
        self.c = {'n_signals_new': 0, 'n_created': 0, 'n_skipped': 0, 'n_evaluated': 0, 'n_transitions': 0, 'n_pending_retry': 0}
        self.notes = []
        self.failed_now = set()

    def usd_per_eur(self):
        if self._fx == 'unset':
            self._fx = self.fx_provider()
        return self._fx

    # -- creazione ------------------------------------------------------------------
    def create_lifecycles(self):
        since = self.now - timedelta(days=SIGNAL_LOOKBACK_DAYS)
        for sig in self.store.new_approved_signals(since):
            self.c['n_signals_new'] += 1
            ticker = sig['ticker']
            if sig['filtered_action'] == 'SELL':
                self.c['n_skipped'] += 1          # D1: SELL = uscita di un titolo in portafoglio, mai un nuovo ciclo (nessuno short)
                continue
            raw = self.store.raw(sig['raw_signal_id'])
            if not raw or raw.get('atr') in (None, 0) or raw.get('close_price') is None:
                self._skip(sig, 'segnale grezzo incompleto'); continue
            ref, atr = float(raw['close_price']), float(raw['atr'])
            inv, tgt = float(sig['invalidation_price']), float(sig['target_price'])
            if not levels_are_coherent(ref, atr, inv, tgt):
                self._skip(sig, 'livelli incoerenti (R-INV != 1,5A o TGT-R != 3A)'); continue
            market = market_of(ticker)
            try:
                created_at = parse_ts(sig['timestamp'])
                valid_until = next_session_close(market, created_at)
            except CalendarNotVerified as e:
                self._skip(sig, f'CALENDARIO NON VERIFICATO: {e}'); continue
            if valid_until + timedelta(minutes=EXPIRY_GRACE_MINUTES) <= self.now:
                self._skip(sig, 'scaduto prima di essere visto da T'); continue
            if self.store.open_ticker(ticker):
                self._skip(sig, 'esiste gia un ciclo aperto sul titolo'); continue
            lv = build_levels(ref, atr)
            row = {'raw_signal_id': sig['raw_signal_id'], 'signal_filtered_id': sig['id'], 'ticker': ticker, 'market': market,
                   'currency': currency_of(market), 'side': 'BUY', 'state': 'WATCH', 'action_label': ACTION_LABEL['WATCH'],
                   'ref_price': ref, 'atr': atr, 'zone_low': lv['zone_low'], 'zone_high': lv['zone_high'],
                   'invalidation_price': inv, 'target_price': tgt, 'slippage_pct': float(sig.get('slippage_applied_percent') or 0),
                   'liquidity_bucket': sig.get('liquidity_bucket'), 'created_at': _iso(created_at), 'valid_until': _iso(valid_until),
                   'sync_status': 'NOT_LINKED' if self.executor.name == 'NOT_LINKED' else 'PENDING'}
            if self.dry_run:
                self.log(f"[dry-run] creerei ciclo WATCH {ticker} raw={sig['raw_signal_id']}"); self.c['n_created'] += 1; continue
            try:
                lc = self.store.insert_lifecycle(row)
            except Exception as e:
                if _is_unique_violation(e):
                    self._skip(sig, 'ciclo gia presente (vincolo di unicita)'); continue
                raise
            self.store._t('trade_events').insert({'lifecycle_id': lc['id'], 'event_key': 'CREATED', 'event_type': 'CREATED', 'from_state': None,
                                                   'to_state': 'WATCH', 'reason': 'segnale approvato da E', 'price': ref,
                                                   'detected_at': _iso(self.now), 'payload': {'levels': lv}}).execute()
            self.c['n_created'] += 1
            self.log(f"🟡 {ticker}: ciclo creato (ATTENDI), zona {lv['zone_low']:.4f}-{lv['zone_high']:.4f}, valido fino a {valid_until:%d/%m %H:%M} UTC")

    def _skip(self, sig, why):
        self.c['n_skipped'] += 1
        self.notes.append(f"{sig['ticker']} raw={sig['raw_signal_id']}: {why}")
        self.log(f"⏭️ {sig['ticker']}: segnale non trasformato in ciclo - {why}")

    # -- valutazione ----------------------------------------------------------------
    def evaluate_all(self):
        for lc in self.store.open_lifecycles():
            if lc['state'] in ('ENTRY_PENDING', 'EXIT_PENDING'):
                continue                                   # li gestisce retry_pending
            self.c['n_evaluated'] += 1
            try:
                if lc['state'] == 'WATCH':
                    self.evaluate_watch(lc)
                elif lc['state'] == 'ACTIVE':
                    self.evaluate_active(lc)
            except CalendarNotVerified as e:
                self.notes.append(f"{lc['ticker']}: {e}")
                self.log(f"⚠️ {lc['ticker']}: {e}")

    def _bars_after(self, lc, floor_start):
        last = parse_ts(lc.get('last_bar_start'))
        market = lc['market']
        closed_by = self.now - timedelta(minutes=BAR_MINUTES, seconds=BAR_CLOSED_GRACE_SECONDS)
        out = []
        for b in self.store.bars(lc['ticker'], floor_start):
            if b['start'] < floor_start or (last and b['start'] <= last) or b['start'] > closed_by:
                continue
            if not is_regular_bar(market, b['start']):
                continue
            out.append(b)
        return out

    def _delay(self, bar):
        return max(0, int((self.now - bar['end']).total_seconds() // 60))

    def evaluate_watch(self, lc):
        valid_until = parse_ts(lc['valid_until'])
        # prima candela valutabile: la prima che INIZIA dopo la creazione del ciclo (inizio >= created_at)
        for bar in self._bars_after(lc, parse_ts(lc['created_at'])):
            if bar['start'] >= valid_until:                # W1
                break
            kind, reason = watch_rule(lc, bar)
            if kind == 'INVALIDATED':
                self._apply(lc, f'INVALIDATED:{reason}', 'INVALIDATED', 'INVALIDATED',
                            {'closed_reason': reason, 'closed_at': _iso(self.now), 'last_bar_start': _iso(bar['start']), 'last_note': None},
                            bar=bar, reason=reason, price=bar['l'] if reason == 'INV_TOCCATA' else bar['h'])
                return
            if kind == 'IN_ZONE':
                ok, why = entry_eligible(bar, self.now)
                if not ok:
                    lc = self._note(lc, bar, f"zona raggiunta alle {bar['end']:%H:%M} UTC ma {why}")
                    continue
                lc = self._trigger(lc, bar)
                if lc['state'] != 'WATCH':
                    return self.evaluate_active(lc) if lc['state'] == 'ACTIVE' else None
                continue
            flag = 'ESTESO' if kind == 'EXTENDED' else None
            fields = {'last_bar_start': _iso(bar['start']), 'watch_flag': flag,
                      'last_note': 'prezzo oltre la zona: non inseguire, si compra solo se rientra' if flag else None}
            if flag and lc.get('watch_flag') != 'ESTESO':
                lc = self._apply(lc, 'ESTESO', 'WATCH_EXTENDED', 'WATCH', fields, bar=bar, reason='prezzo oltre la zona', price=bar['c'])
            else:
                lc = self._persist(lc, fields)
        else:
            pass
        # W1 per tempo: oltre la chiusura + tolleranza per le ultime candele, senza ingresso
        if self.now >= valid_until + timedelta(minutes=EXPIRY_GRACE_MINUTES) or any(
                b['start'] >= valid_until for b in self.store.bars(lc['ticker'], valid_until)):
            self._apply(lc, 'EXPIRED', 'EXPIRED', 'EXPIRED',
                        {'closed_reason': 'SCADUTO', 'closed_at': _iso(valid_until), 'last_note': None},
                        reason='fine seduta senza ingresso')

    def _note(self, lc, bar, text, retry=False):
        # retry=True: ostacolo temporaneo (cambio, capitale, quantita'): la candela NON si considera elaborata,
        # al run successivo si riprova finche' e' fresca. Altrimenti (volume 0, dato non ok, non fresca) si va avanti.
        fields = {'last_note': text}
        if not retry:
            fields['last_bar_start'] = _iso(bar['start'])
        return self._persist(lc, fields)

    def _persist(self, lc, fields):
        if self.dry_run:
            return dict(lc, **fields)
        return self.store.update(lc, fields)

    def _apply(self, lc, key, etype, to_state, updates, bar=None, reason=None, price=None):
        self.c['n_transitions'] += 1
        self.log(f"➡️ {lc['ticker']}: {lc['state']} → {to_state} ({reason or key})")
        if self.dry_run:
            return dict(lc, state=to_state, **updates)
        return self.store.transition(lc, key, etype, to_state, updates, bar=bar, reason=reason, price=price,
                                     delay=self._delay(bar) if bar else None, now=self.now)

    # -- ingresso -------------------------------------------------------------------
    def _trigger(self, lc, bar):
        """Candela in zona, con scambi e fresca: calcola l'ingresso (fill, quantita', cassa) e fa scattare COMPRA ORA."""
        market, currency = lc['market'], lc['currency']
        fx_eur_per_local = 1.0
        if currency == 'USD':
            usd_per_eur = self.usd_per_eur()
            if not usd_per_eur:
                return self._note(lc, bar, 'ingresso rimandato: cambio USD/EUR non disponibile', retry=True)
            fx_eur_per_local = 1.0 / usd_per_eur
        fill = bar['c'] * (1 + float(lc['slippage_pct'] or 0))
        cash = self.store.portfolio_cash()
        if cash is None:
            return self._note(lc, bar, 'ingresso rimandato: portafoglio non trovato', retry=True)
        reserved = self.store.reserved_eur()
        sizing_capital_eur = (cash + reserved) if self.executor.name == 'NOT_LINKED' else (cash + self.store.invested_eur())
        qty_f = position_size(fill, float(lc['invalidation_price']), sizing_capital_eur / fx_eur_per_local)
        qty = math.floor(qty_f) if qty_f else 0
        if qty < 1:
            return self._note(lc, bar, 'SEGNALE VALIDO ma NON eseguito: quantita < 1 azione con il rischio per operazione', retry=True)
        countervalue = round(qty * fill * fx_eur_per_local, 2)
        available = cash - reserved
        if countervalue > available + 1e-9:
            return self._note(lc, bar, f'SEGNALE VALIDO ma NON eseguito: capitale virtuale libero {available:.2f} EUR < {countervalue:.2f} EUR', retry=True)
        entry_session = local_date(market, bar['start'])
        planned_exit = nth_session_date(market, entry_session, MAX_HOLD_SESSIONS)
        updates = {'trigger_bar_start': _iso(bar['start']), 'trigger_bar_end': _iso(bar['end']), 'trigger_detected_at': _iso(self.now),
                   'trigger_delay_minutes': self._delay(bar), 'entry_fill_price': fill, 'quantity': qty, 'countervalue_eur': countervalue,
                   'fx_eur_per_local': fx_eur_per_local, 'entry_session_date': entry_session.isoformat(),
                   'planned_time_exit_date': planned_exit.isoformat(), 'max_hold_sessions': MAX_HOLD_SESSIONS, 'sessions_elapsed': 1,
                   'last_bar_start': _iso(bar['start']), 'watch_flag': None, 'last_note': None}
        lc2 = self._apply(lc, 'TRIGGER', 'TRIGGER', 'ENTRY_PENDING', updates, bar=bar, reason='candela in zona di ingresso', price=bar['c'])
        if self.dry_run:
            return dict(lc2, state='ACTIVE')
        return self._finish_entry(lc2, bar)

    def _finish_entry(self, lc, bar=None):
        intent = self.store.ensure_intent(lc, 'BUY', lc['quantity'], lc['entry_fill_price'],
                                          'NOT_LINKED' if self.executor.name == 'NOT_LINKED' else 'PENDING')
        res = self.executor.execute(lc, intent)
        return self._after_exec(lc, intent, res, to_state='ACTIVE', key='ACTIVE', etype='ENTRY_CONFIRMED', bar=bar)

    def _after_exec(self, lc, intent, res, to_state, key, etype, bar=None, extra=None):
        attempts = int(intent.get('attempts') or 0) + 1
        if not res.ok:                                        # errore chiaramente identificabile: resta *_PENDING, si ritenta
            self.failed_now.add(lc['id'])
            self.store.update_intent(intent['id'], {'status': 'FAILED', 'attempts': attempts, 'last_error': (res.error or 'errore')[:500]})
            self.notes.append(f"{lc['ticker']}: operazione {intent['intent_type']} fallita ({res.error}); si ritenta")
            return self.store.update(lc, {'sync_status': 'FAILED', 'last_note': f"operazione di portafoglio non riuscita: {res.error}"})
        self.store.update_intent(intent['id'], {'status': res.status, 'attempts': attempts, 'last_error': None, 'portfolio_tx_id': res.tx_id})
        updates = dict(extra or {}, sync_status=res.status)
        return self._apply(lc, key, etype, to_state, updates, bar=bar, reason='operazione registrata' if res.status == 'DONE' else 'intenzione registrata (portafoglio non collegato)')

    # -- posizione aperta -------------------------------------------------------------
    def evaluate_active(self, lc):
        market = lc['market']
        entry_end = parse_ts(lc['trigger_bar_end'])
        planned_exit = datetime.fromisoformat(str(lc['planned_time_exit_date'])).date()
        sells = self.store.approved_sells(lc['ticker'], entry_end)
        for bar in self._bars_after(lc, entry_end):           # solo candele successive a quella di ingresso
            sess = local_date(market, bar['start'])
            sessions = self._sessions_elapsed(lc, sess)
            hit = active_rule(lc, bar)
            reason, level = (hit if hit else (None, None))
            if not reason and sess > planned_exit:             # A5 con dati mancanti: prima candela dopo la scadenza
                reason, level = 'TEMPO', bar['o']
            if not reason and sess == planned_exit and bar['start'] == last_regular_bar_start(market, sess):
                reason, level = 'TEMPO', bar['c']              # A5: chiusura dell'ultima candela dell'ultima seduta
            sell = next((s for s in sells if parse_ts(s['timestamp']) <= bar['start']), None) if not reason else None
            if sell:                                           # A6: SELL approvato da E su titolo in portafoglio
                reason, level = 'SEGNALE', bar['c']
            if reason:
                self.c['n_transitions'] += 0
                return self._start_exit(lc, bar, reason, level, sessions, sell)
            lc = self._persist(lc, {'last_bar_start': _iso(bar['start']), 'sessions_elapsed': sessions})
        return lc

    def _sessions_elapsed(self, lc, sess_date):
        entry = datetime.fromisoformat(str(lc['entry_session_date'])).date()
        n, d = 0, entry
        while d <= sess_date and n < 30:
            from market_calendar import is_session_day
            if is_session_day(lc['market'], d):
                n += 1
            d += timedelta(days=1)
        return n

    def _start_exit(self, lc, bar, reason, level, sessions, sell=None):
        fx = lc['fx_eur_per_local']
        if lc['currency'] == 'USD':
            u = self.usd_per_eur()
            fx = (1.0 / u) if u else lc['fx_eur_per_local']      # senza cambio aggiornato: quello dell'ingresso
        fill = sell_fill(level, float(lc['slippage_pct'] or 0))
        pnl_eur, pnl_pct = pnl(lc, fill, float(fx))
        updates = {'exit_bar_start': _iso(bar['start']), 'exit_bar_end': _iso(bar['end']), 'exit_detected_at': _iso(self.now),
                   'exit_delay_minutes': self._delay(bar), 'exit_price': fill, 'exit_reason': reason, 'pnl_eur': pnl_eur, 'pnl_pct': pnl_pct,
                   'holding_sessions': sessions, 'sessions_elapsed': sessions, 'last_bar_start': _iso(bar['start']),
                   'exit_signal_raw_id': sell['raw_signal_id'] if sell else None, 'closed_at': _iso(bar['end']), 'closed_reason': reason}
        lc2 = self._apply(lc, f'EXIT_SIGNAL:{reason}', 'EXIT_DECIDED', 'EXIT_PENDING', updates, bar=bar, reason=reason, price=level)
        if self.dry_run:
            return dict(lc2, state='EXIT')
        return self._finish_exit(lc2, bar)

    def _finish_exit(self, lc, bar=None):
        intent = self.store.ensure_intent(lc, 'SELL', lc['quantity'], lc['exit_price'],
                                          'NOT_LINKED' if self.executor.name == 'NOT_LINKED' else 'PENDING')
        res = self.executor.execute(lc, intent)
        return self._after_exec(lc, intent, res, to_state='EXIT', key='EXIT', etype='EXIT_CONFIRMED', bar=bar)

    # -- ritentativi (stato *_PENDING: l'operazione non e' ancora registrata) ---------------
    def retry_pending(self):
        for lc in self.store.pending_lifecycles():
            if lc['id'] in self.failed_now:
                continue                                      # appena fallita: riprova al prossimo run
            self.c['n_pending_retry'] += 1
            if lc['state'] == 'ENTRY_PENDING':
                self._finish_entry(lc)
            else:
                self._finish_exit(lc)

    # -- notifiche: livello SEPARATO dalla macchina a stati (non la modifica, non ne dipende) ----------
    def sync_alerts(self):
        """Per ogni evento COMPRA ORA / VENDI ORA recente crea UNA riga per canale in trade_alerts (idempotente)."""
        events = self.store.recent_alert_events(self.now - timedelta(hours=12))
        if not events:
            return
        have = {(a['lifecycle_id'], a['event_key'], a['channel']) for a in self.store.alerts_of({e['lifecycle_id'] for e in events})}
        for ev in events:
            if all((ev['lifecycle_id'], ev['event_key'], ch) in have for ch in CHANNELS):
                continue
            lc = self.store.lifecycle(ev['lifecycle_id'])
            kind = ALERT_EVENT_KINDS[ev['event_key']]
            ready = lc and (lc.get('entry_fill_price') is not None if kind == 'COMPRA ORA' else lc.get('exit_price') is not None)
            if not ready:
                continue                                  # transizione non ancora completata: al prossimo run
            subject, text = notifications.build_buy_alert(lc) if kind == 'COMPRA ORA' else notifications.build_sell_alert(lc)
            for ch in CHANNELS:
                if (ev['lifecycle_id'], ev['event_key'], ch) in have:
                    continue
                row = {'lifecycle_id': ev['lifecycle_id'], 'event_key': ev['event_key'], 'kind': kind, 'channel': ch, 'status': 'PENDING',
                       'attempts': 0, 'subject': subject, 'message': text, 'event_detected_at': ev['detected_at']}
                if self.store.insert_alert(row):
                    self.alert_stats['enqueued'] += 1

    def deliver_alerts(self):
        """Consegna gli alert PENDING/FAILED ancora utili. Un errore qui NON tocca mai lo stato dei cicli."""
        for al in self.store.open_alerts():
            age_min = (self.now - parse_ts(al['event_detected_at'])).total_seconds() / 60
            if al['kind'] != 'TEST' and age_min > ALERT_MAX_AGE_MINUTES[al['kind']]:
                self.store.update_alert(al['id'], {'status': 'EXPIRED', 'last_error': f"non piu utile ({int(age_min)} min dall'evento)"})
                self.alert_stats['expired'] += 1
                self.log(f"⌛ alert {al['kind']} {al['channel']} scaduto senza invio ({int(age_min)} min)")
                continue
            if int(al['attempts'] or 0) >= ALERT_MAX_ATTEMPTS:
                self.store.update_alert(al['id'], {'status': 'GIVEN_UP'})
                self.alert_stats['given_up'] += 1
                continue
            try:
                status, err = self.senders[al['channel']](al.get('subject'), al['message'])
            except Exception as exc:                      # nessun errore di invio deve fermare T
                status, err = 'FAILED', f"{type(exc).__name__}: {str(exc)[:200]}"
            fields = {'attempts': int(al['attempts'] or 0) + 1, 'last_error': err}
            if status == 'SENT':
                fields.update(status='SENT', sent_at=_iso(self.now))
                self.alert_stats['sent'] += 1
            elif status == 'NOT_CONFIGURED':
                fields.update(status='NOT_CONFIGURED')    # canale non configurato: niente ritentativi inutili
                self.alert_stats['not_configured'] += 1
            else:
                fields.update(status='FAILED')
                self.alert_stats['failed'] += 1
                self.notes.append(f"alert {al['kind']} {al['channel']} non consegnato: {err}")
            self.store.update_alert(al['id'], fields)
            self.log(f"📣 alert {al['kind']} {al['channel']}: {fields['status']}" + (f" ({err})" if err else ''))

    def run(self):
        self.create_lifecycles()
        self.evaluate_all()
        self.retry_pending()
        if not self.dry_run:
            try:
                self.sync_alerts()
                self.deliver_alerts()
            except Exception as exc:                      # le notifiche non fanno mai fallire T
                self.notes.append(f"errore nel livello notifiche: {type(exc).__name__}: {str(exc)[:200]}")
                self.log(f"⚠️ errore nel livello notifiche: {exc}")
        return self.c


def test_alert(sb, now):
    """Messaggio di PROVA (nessuna azione richiesta) su entrambi i canali; l'esito resta in trade_alerts (kind TEST)."""
    eng = Engine(sb, now, log=print)
    subject, text = notifications.build_test_alert(now)
    key = f"TEST:{now:%Y%m%dT%H%M%S}"
    for ch in CHANNELS:
        eng.store.insert_alert({'lifecycle_id': None, 'event_key': key, 'kind': 'TEST', 'channel': ch, 'status': 'PENDING', 'attempts': 0,
                                'subject': subject, 'message': text, 'event_detected_at': _iso(now)})
    eng.deliver_alerts()
    print(f"✅ prova notifiche completata: {eng.alert_stats}")


def snapshot_if_due(sb, now, every_minutes=55):
    """Fotografia del portafoglio (curva del capitale): al piu' una ogni ~ora, mai bloccante."""
    try:
        pf = sb.table('portfolios').select('id').eq('code', PORTFOLIO_CODE).execute().data
        if not pf:
            return
        last = sb.table('portfolio_snapshots').select('snapshot_at').eq('portfolio_id', pf[0]['id']).order('snapshot_at', desc=True).limit(1).execute().data
        if last and parse_ts(last[0]['snapshot_at']) > now - timedelta(minutes=every_minutes):
            return
        sb.rpc('portfolio_snapshot', {'p_code': PORTFOLIO_CODE, 'p_snapshot_at': _iso(now)}).execute()
        print('📸 snapshot portafoglio registrato')
    except Exception as e:
        print(f'⚠️ snapshot portafoglio non registrato: {e}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true', help='calcola e stampa, senza scrivere')
    ap.add_argument('--now', help='istante ISO UTC (solo per riprodurre il passato)')
    ap.add_argument('--test-alert', action='store_true', help='invia un messaggio di PROVA su Telegram ed email e ne registra l esito')
    args = ap.parse_args()
    from config import supabase
    now = parse_ts(args.now) if args.now else datetime.now(timezone.utc)
    if args.test_alert:
        return test_alert(supabase, now)
    executor = PortfolioExecutor(supabase) if EXECUTOR_MODE == 'PORTFOLIO' else NotLinkedExecutor()
    eng = Engine(supabase, now, executor=executor, dry_run=args.dry_run)
    if isinstance(executor, PortfolioExecutor):
        executor.fx_usd_per_eur = eng.usd_per_eur
    run_id = eng.store.run_start(EXECUTOR_MODE, args.dry_run, now)
    print(f"Modulo T - state machine (paper: operazioni virtuali sul portafoglio IA, nessun ordine reale) | now={now:%Y-%m-%d %H:%M} UTC")
    try:
        counters = eng.run()
        eng.store.run_finish(run_id, 'OK', counters, notes={'note': eng.notes[:20], 'alerts': eng.alert_stats})
        print(f"✅ T completato: {counters} | alert: {eng.alert_stats}")
        if EXECUTOR_MODE == 'PORTFOLIO' and not args.dry_run:
            snapshot_if_due(supabase, now)
    except Exception as e:
        eng.store.run_finish(run_id, 'ERROR', eng.c, error=str(e)[:900], notes={'note': eng.notes[:20]})
        print(f"❌ T errore: {e}")
        raise


if __name__ == '__main__':
    main()
