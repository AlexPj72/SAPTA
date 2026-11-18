"""
Freschezza di una barra 15m, calcolata IN LETTURA (Passo 1, audit 14/11/2026).

Il flag in 'prezzi' dice com'e' fatta la barra (qualita' intrinseca) e non cambia nel tempo. Se una barra e' ancora
"corrente" dipende da quando la si legge: una barra 'ok' della chiusura di ieri non e' un dato corrente.

Una barra e' fresca se:
  1. appartiene alla negoziazione continua di una seduta del suo mercato (calendario di market_calendar.py;
     se il calendario non e' verificato per quella data si usa solo l'eta');
  2. la sua fine non e' piu vecchia di max_minutes rispetto a 'now'.
A mercato chiuso l'eta' supera la soglia e la barra non e' fresca; il calendario esclude pre/post-mercato e aste.
"""
from datetime import datetime, timedelta, timezone
import re

from bar_ingestion_core import market_for, to_utc
from market_calendar import BAR_MINUTES, CalendarNotVerified, is_regular_bar

FRESHNESS_MAX_MINUTES = 30   # [15/11 -> 16/11] massimo 30 minuti dalla FINE della barra (le barre restano a 15 minuti); oltre = problema di alimentazione, non barra fresca


def is_valid_bar(bar):
    """Barra utilizzabile per baseline e confronti: flag 'ok' (o assente) e volume > 0. Criterio UNICO di H1/H2 e AI Watch."""
    try:
        volume = float(bar.get('volume') or 0)
    except (TypeError, ValueError):
        return False
    return bar.get('data_quality_flag') in (None, 'ok') and volume > 0


def parse_ts(value):
    """Timestamp ISO di Supabase (anche con frazioni di secondo irregolari, 'Z') -> datetime UTC."""
    if isinstance(value, datetime):
        return to_utc(value)
    s = str(value).strip().replace('Z', '+00:00').replace(' ', 'T')
    m = re.match(r'^(.*?\d{2}:\d{2}:\d{2})(\.\d+)?(.*)$', s)
    if m:
        frac = (m.group(2) or '')[1:7].ljust(6, '0') if m.group(2) else ''
        s = m.group(1) + ('.' + frac if frac else '') + m.group(3)
    return to_utc(datetime.fromisoformat(s))


def is_bar_fresh(ticker, bar_start, now=None, max_minutes=FRESHNESS_MAX_MINUTES):
    now = to_utc(now) if now is not None else datetime.now(timezone.utc)
    try:
        start = parse_ts(bar_start)
    except (ValueError, TypeError):
        return False
    try:
        if not is_regular_bar(market_for(ticker), start):
            return False
    except CalendarNotVerified:
        pass
    age = now - (start + timedelta(minutes=BAR_MINUTES))
    return age <= timedelta(minutes=max_minutes)
