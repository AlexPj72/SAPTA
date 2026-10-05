"""
Calendario di seduta per la state machine (Modulo T): chiusure, orari e festivita' di Borsa Italiana e NYSE/Nasdaq.

- Orari in fuso orario locale (zoneinfo): l'ora legale si gestisce da sola (Europa e USA cambiano ora in date diverse).
- Calendario VERIFICATO fino a CALENDAR_VERIFIED_UNTIL (fonti: nyse.com/trade/hours-calendars e calendario ufficiale
  Borsa Italiana 2026). Oltre quella data le funzioni sollevano CalendarNotVerified: T non crea nuovi cicli finche'
  il calendario non viene esteso (meglio fermarsi che sbagliare la scadenza).
"""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

BAR_MINUTES = 15
CALENDAR_VERIFIED_UNTIL = date(2026, 12, 31)

_TZ = {'USA': ZoneInfo('America/New_York'), 'EU': ZoneInfo('Europe/Rome')}
_OPEN = {'USA': time(9, 30), 'EU': time(9, 0)}
_CLOSE = {'USA': time(16, 0), 'EU': time(17, 30)}     # EU: fine negoziazione continua (asta di chiusura 17:30-17:35 esclusa)

HOLIDAYS = {
    'USA': {date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3), date(2026, 5, 25),
            date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7), date(2026, 11, 26), date(2026, 12, 25)},
    'EU': {date(2026, 1, 1), date(2026, 4, 3), date(2026, 4, 6), date(2026, 5, 1),
           date(2026, 12, 24), date(2026, 12, 25), date(2026, 12, 31)},
}
EARLY_CLOSE = {
    'USA': {date(2026, 7, 2): time(13, 0), date(2026, 11, 27): time(13, 0), date(2026, 12, 24): time(13, 0)},
    'EU': {},
}


class CalendarNotVerified(Exception):
    """La data richiesta e' oltre il calendario verificato."""


def market_of(ticker):
    """'USA' se il ticker e' nell'universo USA, altrimenti 'EU' (tutti gli altri sono titoli italiani .MI)."""
    from universe import UNIVERSE_USA
    return 'USA' if ticker in UNIVERSE_USA else 'EU'


def currency_of(market):
    return 'USD' if market == 'USA' else 'EUR'


def _check(d):
    if d > CALENDAR_VERIFIED_UNTIL:
        raise CalendarNotVerified(f"calendario di seduta verificato solo fino al {CALENDAR_VERIFIED_UNTIL}: richiesto {d}")


def is_session_day(market, d):
    _check(d)
    return d.weekday() < 5 and d not in HOLIDAYS[market]


def session_bounds(market, d):
    """(apertura, chiusura) in UTC del giorno d, oppure None se il mercato e' chiuso."""
    if not is_session_day(market, d):
        return None
    tz = _TZ[market]
    close_t = EARLY_CLOSE[market].get(d, _CLOSE[market])
    o = datetime.combine(d, _OPEN[market], tzinfo=tz).astimezone(timezone.utc)
    c = datetime.combine(d, close_t, tzinfo=tz).astimezone(timezone.utc)
    return o, c


def local_date(market, ts):
    return ts.astimezone(_TZ[market]).date()


def next_session_close(market, ts):
    """Chiusura della prima seduta che contiene o segue ts (spec §5): creato in seduta -> stessa seduta; fuori -> la prossima."""
    d = local_date(market, ts)
    for i in range(12):
        day = d + timedelta(days=i)
        b = session_bounds(market, day)
        if b and b[1] > ts:
            return b[1]
    raise CalendarNotVerified("nessuna seduta trovata nei prossimi 12 giorni")


def nth_session_date(market, start_date, n):
    """Data della n-esima seduta contando start_date come la 1a (spec §6). start_date deve essere un giorno di seduta."""
    d, count = start_date, 0
    for _ in range(60):
        if is_session_day(market, d):
            count += 1
            if count == n:
                return d
        d += timedelta(days=1)
    raise CalendarNotVerified("seduta n-esima non trovata")


def last_regular_bar_start(market, d):
    b = session_bounds(market, d)
    return None if b is None else b[1] - timedelta(minutes=BAR_MINUTES)


def is_regular_bar(market, bar_start):
    """True se la candela inizia dentro la negoziazione continua di una seduta (esclude pre-apertura e aste)."""
    b = session_bounds(market, local_date(market, bar_start))
    return bool(b) and b[0] <= bar_start < b[1]
