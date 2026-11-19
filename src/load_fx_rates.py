"""
Carica i tassi di riferimento BCE in fx_rates (incrementale, idempotente). Solo GET sul sito BCE (gratuito) e inserimenti.

  python src/load_fx_rates.py            # ultimo tasso giornaliero
  python src/load_fx_rates.py --hist90   # ultimi ~90 giorni (primo caricamento / recupero)

Un solo cambio per giornata: l'inserimento usa ignore_duplicates (una riga gia' presente non viene mai modificata).
Codice di uscita 1 se download, parsing o scrittura falliscono, o se la BCE non restituisce alcun tasso.
"""
import argparse
import sys
import urllib.request

from fx import ECB_DAILY_URL, ECB_HIST_90D_URL, parse_ecb_xml

ON_CONFLICT = 'base_currency,quote_currency,rate_date'


def download(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'SAPTA-fx-loader/1.0'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8')


def run(client, fetcher=download, hist90=False, quote='USD'):
    url = ECB_HIST_90D_URL if hist90 else ECB_DAILY_URL
    try:
        rates = parse_ecb_xml(fetcher(url), quote)
    except Exception as e:
        print(f"❌ BCE: download/parsing fallito: {e}")
        return 1
    if not rates:
        print("❌ BCE: nessun tasso nel file scaricato")
        return 1
    rows = [{'base_currency': 'EUR', 'quote_currency': quote, 'rate_date': d.isoformat(), 'rate': r, 'source': 'ECB'}
            for d, r in sorted(rates.items())]
    try:
        resp = client.table('fx_rates').upsert(rows, on_conflict=ON_CONFLICT, ignore_duplicates=True).execute()
    except Exception as e:
        print(f"❌ scrittura fx_rates fallita: {e}")
        return 1
    inserted = len(resp.data or [])
    print(f"✅ BCE {quote}: {len(rows)} tassi scaricati ({rows[0]['rate_date']} → {rows[-1]['rate_date']}), "
          f"{inserted} inseriti, {len(rows) - inserted} già presenti (non modificati)")
    return 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--hist90', action='store_true')
    a = ap.parse_args()
    from config import supabase
    sys.exit(run(supabase, hist90=a.hist90))
