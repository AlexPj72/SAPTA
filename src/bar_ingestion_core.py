"""
Nucleo del Modulo A (Passo 1, audit 14/11/2026): logica pura di selezione e classificazione delle barre 15m.
Nessun accesso a rete, database o variabili d'ambiente: tutto e' testabile con dati sintetici.

Principi:
- si scrivono TUTTE le barre del periodo scaricato, non solo l'ultima;
- solo barre CHIUSE da almeno CLOSE_GRACE_SECONDS e appartenenti alla negoziazione continua (calendario di market_calendar);
- il flag e' assegnato UNA volta, all'inserimento, e non viene piu' sovrascritto (l'upsert e' ignore_duplicates);
- qualita' intrinseca della barra (ok / zero_volume / feed_error) distinta dalla freschezza di acquisizione (stale);
- la freschezza "in lettura" (la barra e' ancora corrente?) NON e' un flag: si calcola in bar_freshness.py.
"""
import math
from datetime import datetime, timedelta, timezone

from market_calendar import BAR_MINUTES, CalendarNotVerified, is_regular_bar, session_bounds

CLOSE_GRACE_SECONDS = 60
STALE_INGESTION_MINUTES = 30      # ritardo (dalla FINE della barra) oltre il quale una barra "live" e' marcata stale: massimo 30 minuti
# Il feed Yahoo Italia consegna prima una barra PROVVISORIA (volume parziale o zero) e la completa dopo circa 15 minuti: misurato il
# 16-17/11/2026, barre EU acquisite entro 3 minuti dalla chiusura = volume mediano 0,11x della media storica (0,49x se acquisite dopo
# 10-20 minuti) e 32% a volume zero. Con l'upsert ignore_duplicates la barra provvisoria resterebbe congelata: in modalita' live una
# barra si scrive solo quando il suo mercato ha 'assestato' il dato. USA: dato definitivo alla chiusura (0 minuti).
SETTLE_MINUTES = {'EU': 15, 'USA': 0}
LIVE_WINDOW_MINUTES = 180         # una barra e' "live" se la sua fine e' piu' recente di questa finestra; piu' vecchia = recupero
PRICE_TOL = 1e-6

COUNTER_KEYS = ('scaricate', 'scartate_nan', 'scartate_non_regolari', 'scartate_in_formazione', 'trattenute_non_assestate', 'riparate',
                'calendario_non_verificato', 'da_scrivere', 'inserite', 'duplicate',
                'errori_download', 'errori_scrittura', 'ticker_senza_dati')


def new_counters():
    return {k: 0 for k in COUNTER_KEYS}


def market_for(ticker):
    """Mercato di un simbolo, anche per gli indici (^GSPC -> USA, FTSEMIB.MI -> EU)."""
    return 'EU' if ticker.endswith('.MI') else 'USA'


def to_utc(ts):
    """Timestamp (pandas/datetime, naive = UTC) -> datetime tz-aware UTC."""
    if hasattr(ts, 'to_pydatetime'):
        ts = ts.to_pydatetime()
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def _isnum(x):
    return x is not None and not (isinstance(x, float) and math.isnan(x))


def classify_bar(o, h, l, c, v, bar_end, now, live):
    """Flag di qualita' assegnato all'inserimento. Priorita': feed_error > zero_volume > stale > ok."""
    if (min(o, h, l, c) <= 0 or h < max(o, c, l) * (1 - PRICE_TOL) or l > min(o, c, h) * (1 + PRICE_TOL)
            or not _isnum(v) or v < 0):
        return 'feed_error'
    if v == 0:
        return 'zero_volume'
    if live:
        delay = now - bar_end
        if timedelta(minutes=STALE_INGESTION_MINUTES) < delay <= timedelta(minutes=LIVE_WINDOW_MINUTES):
            return 'stale'
    return 'ok'


def build_records(ticker, rows, now, live, counters):
    """rows: iterabile di (inizio_barra, open, high, low, close, volume).
    Ritorna la lista di record 'prezzi' da scrivere e aggiorna i contatori."""
    market = market_for(ticker)
    out = []
    for start, o, h, l, c, v in rows:
        counters['scaricate'] += 1
        if not all(_isnum(x) for x in (o, h, l, c)):
            counters['scartate_nan'] += 1
            continue
        start = to_utc(start)
        try:
            regular = is_regular_bar(market, start)
        except CalendarNotVerified:
            regular = True
            counters['calendario_non_verificato'] += 1
        if not regular:
            counters['scartate_non_regolari'] += 1
            continue
        bar_end = start + timedelta(minutes=BAR_MINUTES)
        if bar_end + timedelta(seconds=CLOSE_GRACE_SECONDS) > now:
            counters['scartate_in_formazione'] += 1
            continue
        if live and now - bar_end < timedelta(minutes=SETTLE_MINUTES.get(market, 0)):
            counters['trattenute_non_assestate'] += 1     # dato ancora provvisorio: si scrive al run successivo (A riscarica 2 giorni)
            continue
        v = float(v) if _isnum(v) else None
        flag = classify_bar(float(o), float(h), float(l), float(c), v, bar_end, now, live)
        out.append({
            'ticker': ticker,
            'timestamp': start.isoformat(),
            'interval': '15m',
            'open': float(o), 'high': float(h), 'low': float(l), 'close': float(c),
            'volume': int(v) if v is not None else 0,
            'source': 'yfinance',
            'data_quality_flag': flag,
        })
    counters['da_scrivere'] += len(out)
    return out


def frame_rows(df, ticker):
    """Righe (inizio, o, h, l, c, v) dal DataFrame di yfinance (colonne MultiIndex o piatte). [] se il ticker non c'e'."""
    if df is None or len(df) == 0:
        return []
    try:
        sub = df[ticker] if hasattr(df.columns, 'levels') else df
        sub = sub[['Open', 'High', 'Low', 'Close', 'Volume']]
    except KeyError:
        return []
    sub = sub.dropna(how='all')
    return [(idx, r['Open'], r['High'], r['Low'], r['Close'], r['Volume']) for idx, r in sub.iterrows()]


def expected_bars(market, d):
    """Numero di barre 15m regolari attese nella seduta d (0 se chiuso). Solleva CalendarNotVerified oltre il calendario."""
    b = session_bounds(market, d)
    return 0 if b is None else int((b[1] - b[0]).total_seconds() // (BAR_MINUTES * 60))


def coverage(records_by_ticker, window_start, now):
    """Copertura = barre scritte/attese per seduta completa chiusa nell'intervallo [window_start, now).
    Considera solo sedute COMPLETE (chiusura + 1 min < now) il cui inizio e' >= window_start."""
    exp = got = 0
    for ticker, recs in records_by_ticker.items():
        market = market_for(ticker)
        have = {datetime.fromisoformat(r['timestamp']) for r in recs}
        d = window_start.date()
        while d <= now.date():
            try:
                b = session_bounds(market, d)
            except CalendarNotVerified:
                break
            if b and b[0] >= window_start and b[1] + timedelta(minutes=1) < now:
                exp += expected_bars(market, d)
                got += sum(1 for t in have if b[0] <= t < b[1])
            d += timedelta(days=1)
    return {'attese': exp, 'presenti': got, 'copertura': (got / exp) if exp else None}
