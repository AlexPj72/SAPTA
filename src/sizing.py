"""
Dimensionamento e costi condivisi da Modulo E e Modulo T (Passo 3, audit 14/11/2026; decisione del 07/11).

Un'UNICA funzione di dimensionamento: E e T chiamano size_position con gli stessi ingressi e ottengono la stessa quantita'
e lo stesso controvalore. Nessun accesso a database o rete: tutto testabile.

Regole:
- prezzo di dimensionamento = R + 0,5 ATR (limite alto della zona di ingresso) piu' lo slippage del bucket di liquidita': il
  rischio reale non puo' superare quello stimato, qualunque sia il punto della zona in cui scatta l'ingresso;
- il rischio massimo per operazione (1% del capitale di riferimento) comprende la perdita allo stop (con slippage in uscita) E i
  costi completi di andata e ritorno (commissione fissa, commissione %, spread, bollo, slippage);
- quantita': INTERA (floor) per i titoli italiani; FRAZIONARIA (4 decimali, per difetto) SOLO per i titoli USA (decisione dell'utente del 22/11);
  mai oltre il capitale di riferimento; il rischio resta all'1% in entrambi i casi;
- capitale di riferimento: 1.000 EUR (capital_state). Non si aumenta qui.
"""
import math

REFERENCE_CAPITAL_EUR = 1000          # capitale di riferimento (usato solo se capital_state e' vuota, mai in caso di errore)
RISK_PER_TRADE_PERCENT = 0.01         # 1% del capitale per operazione
ZONE_ATR_FRACTION = 0.5               # zona di ingresso: da R a R + 0,5*ATR

SLIPPAGE_BY_LIQUIDITY = {             # [Sezione 12] valori di default, non calibrati
    'LIQ_HIGH': 0.0005,
    'LIQ_MEDIUM': 0.0015,
    'LIQ_LOW': 0.0040,
}
DEFAULT_SLIPPAGE = 0.0040             # fail-safe: bucket mancante = caso peggiore
FRACTIONAL_DECIMALS = 4               # quantita' frazionarie (solo USA): troncate per difetto a 4 decimali, il rischio non supera mai l'1%
FRACTIONAL_MARKETS = ('USA',)         # decisione dell'utente (22/11): frazioni consentite ESCLUSIVAMENTE per i titoli USA


def allows_fractional(market):
    return market in FRACTIONAL_MARKETS


def _floor_qty(x, fractional):
    if fractional:
        f = 10 ** FRACTIONAL_DECIMALS
        return math.floor(x * f + 1e-9) / f
    return math.floor(x)


def slippage_for(liquidity_bucket):
    return SLIPPAGE_BY_LIQUIDITY.get(liquidity_bucket, DEFAULT_SLIPPAGE)


def entry_reference_price(ref_price, atr, liquidity_bucket):
    """Prezzo di dimensionamento: R + 0,5 ATR, con slippage di ingresso."""
    return (float(ref_price) + ZONE_ATR_FRACTION * float(atr)) * (1 + slippage_for(liquidity_bucket))


def calculate_operation_cost(price, quantity, costs, liquidity_bucket):
    """Costo di UN lato (ingresso o uscita), nella valuta di 'costs' (commissione fissa in EUR; il resto e' una quota del valore)."""
    value = price * quantity
    slippage_pct = slippage_for(liquidity_bucket)
    total = (costs['commissione_fissa'] + value * costs['commissione_percentuale'] + value * costs['spread_medio_percentuale']
             + value * costs['bollo_percentuale'] + value * slippage_pct)
    return total, slippage_pct


def round_trip_cost(price, quantity, costs, liquidity_bucket):
    """Costo COMPLETO di andata e ritorno: ingresso piu' uscita."""
    one_way, slippage_pct = calculate_operation_cost(price, quantity, costs, liquidity_bucket)
    return 2 * one_way, slippage_pct


def size_position(ref_price, atr, invalidation_price, capital_eur, fx_eur_per_local, costs, liquidity_bucket,
                  risk_percent=RISK_PER_TRADE_PERCENT, fractional=False):
    """Quantita' (intera) e controvalore. None se non dimensionabile (dati mancanti o stop non sotto il prezzo di ingresso).
    ref_price, atr, invalidation_price sono nella valuta del titolo; capital_eur in EUR; fx_eur_per_local = EUR per 1 unita' locale."""
    if None in (ref_price, atr, invalidation_price, capital_eur, fx_eur_per_local, costs) or not fx_eur_per_local:
        return None
    slip = slippage_for(liquidity_bucket)
    entry = entry_reference_price(ref_price, atr, liquidity_bucket)
    exit_at_stop = float(invalidation_price) * (1 - slip)
    if entry <= exit_at_stop:
        return None
    pct_costs = 2 * (costs['commissione_percentuale'] + costs['spread_medio_percentuale'] + costs['bollo_percentuale'])
    loss_per_share = (entry - exit_at_stop) + pct_costs * entry                       # perdita allo stop + costi proporzionali (andata e ritorno)
    fixed_local = 2 * costs['commissione_fissa'] / fx_eur_per_local                  # commissione fissa, andata e ritorno
    risk_local = capital_eur * risk_percent / fx_eur_per_local
    qty = _floor_qty((risk_local - fixed_local) / loss_per_share, fractional) if risk_local > fixed_local else 0
    qty = min(qty, _floor_qty(capital_eur / (entry * fx_eur_per_local), fractional))   # mai oltre il capitale
    qty = max(qty, 0)
    cost_rt, _ = round_trip_cost(entry, qty, costs, liquidity_bucket) if qty else (0.0, slip)
    return {'quantity': qty, 'fractional': fractional, 'entry_price': entry, 'countervalue_eur': round(qty * entry * fx_eur_per_local, 2),
            'risk_budget_eur': round(capital_eur * risk_percent, 2), 'round_trip_cost_local': cost_rt,
            'loss_per_share_local': loss_per_share}
