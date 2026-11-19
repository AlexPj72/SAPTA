"""
Cambio EUR/USD unico per giornata (tassi di riferimento BCE) - SAPTA, 19/11/2026.

Regole (decise dall'utente):
- fonte UNICA: tassi di riferimento BCE salvati in 'fx_rates' (gratuiti); nessun ripiego su Yahoo o altre fonti;
- un solo cambio per giornata: E e T leggono ESATTAMENTE lo stesso tasso, identificato dalla data di riferimento;
- se il cambio necessario manca, errore esplicito (FxRateUnavailable): chi lo richiede si ferma.

Tasso in vigore per il giorno D = ultimo tasso BCE con rate_date STRETTAMENTE precedente a D.
Perche' "strettamente precedente": la BCE pubblica verso le 16:00 CET; se il tasso di D contasse per D, E (mattina) e T (sera) dello stesso
giorno leggerebbero righe diverse. Cosi' lunedi' si usa il tasso di venerdi', dopo un festivo l'ultimo giorno lavorativo, e la stessa data
produce sempre la stessa riga. Se l'ultimo tasso e' piu' vecchio di FX_MAX_AGE_DAYS giorni: errore, non si usa un valore stantio.
La data di riferimento di un segnale e' la data UTC del suo timestamp (E la scrive in signals_filtered; T la ritrova in lifecycle.created_at).
"""
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timezone

ECB_DAILY_URL = 'https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml'
ECB_HIST_90D_URL = 'https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml'
FX_MAX_AGE_DAYS = 7
PLAUSIBLE = {'USD': (0.5, 2.0)}       # unita' per 1 EUR: oltre questi limiti il dato e' considerato errato


class FxRateUnavailable(RuntimeError):
    """Il cambio necessario non e' disponibile: chi lo richiede si ferma (nessun valore alternativo)."""


@dataclass(frozen=True)
class FxRate:
    rate_date: date
    quote_currency: str
    rate: float            # unita' di valuta estera per 1 EUR
    source: str = 'ECB'

    @property
    def eur_per_unit(self):
        return 1.0 / self.rate


def _check_plausible(quote, rate):
    lo, hi = PLAUSIBLE.get(quote, (0.0, float('inf')))
    if not (lo < rate < hi):
        raise ValueError(f"tasso {quote} non plausibile: {rate}")


def parse_ecb_xml(text, quote='USD'):
    """XML BCE (giornaliero o storico) -> {data: unita' di 'quote' per 1 EUR}. Solleva ValueError se il contenuto non e' valido."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        raise ValueError(f"XML BCE non valido: {e}")
    out = {}
    for day in root.iter():
        if not day.tag.endswith('Cube') or 'time' not in day.attrib:
            continue
        try:
            d = date.fromisoformat(day.attrib['time'])
        except ValueError:
            raise ValueError(f"data BCE non valida: {day.attrib['time']}")
        for c in day:
            if c.tag.endswith('Cube') and c.attrib.get('currency') == quote:
                rate = float(c.attrib['rate'])
                _check_plausible(quote, rate)
                out[d] = rate
    return out


def reference_date(ts):
    """Data di riferimento (UTC) di un segnale: la data del suo timestamp."""
    if isinstance(ts, datetime):
        return (ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).date()
    if isinstance(ts, date):
        return ts
    from bar_freshness import parse_ts
    return parse_ts(ts).date()


def rate_for_date(client, ref_date, quote='USD', max_age_days=FX_MAX_AGE_DAYS):
    """Tasso BCE in vigore per ref_date (ultimo con rate_date < ref_date). FxRateUnavailable se manca, e' troppo vecchio o non e' valido."""
    ref_date = reference_date(ref_date)
    try:
        rows = (client.table('fx_rates').select('rate_date,rate,source').eq('base_currency', 'EUR').eq('quote_currency', quote)
                .lt('rate_date', ref_date.isoformat()).order('rate_date', desc=True).limit(1).execute().data or [])
    except Exception as e:
        raise FxRateUnavailable(f"lettura fx_rates fallita per {quote} al {ref_date}: {e}")
    if not rows:
        raise FxRateUnavailable(f"nessun tasso BCE {quote} precedente al {ref_date} in fx_rates")
    row = rows[0]
    try:
        rate_date, rate = date.fromisoformat(str(row['rate_date'])[:10]), float(row['rate'])
        _check_plausible(quote, rate)
    except (ValueError, TypeError) as e:
        raise FxRateUnavailable(f"tasso BCE {quote} non valido in fx_rates ({row}): {e}")
    age = (ref_date - rate_date).days
    if age > max_age_days:
        raise FxRateUnavailable(f"ultimo tasso BCE {quote} ({rate_date}) piu' vecchio di {max_age_days} giorni rispetto al {ref_date}")
    return FxRate(rate_date=rate_date, quote_currency=quote, rate=rate, source=row.get('source') or 'ECB')
