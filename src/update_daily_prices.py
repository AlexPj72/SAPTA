"""
Aggiornamento incrementale prezzi giornalieri (NUOVO 22/09 - audit; esteso agli indici il 18/11 - Passo 3)

CAUSA RADICE trovata in audit il 22/09: 'prezzi' interval='1d' era fermo al 11/09/2026 su TUTTO l'universo, perche' l'unico job che
scrive dati giornalieri (load_historical_data.py) e' "one-off". Questo script aggiunge l'aggiornamento INCREMENTALE quotidiano:
riusa fetch_and_write() con un periodo breve ("5d") per recuperare i giorni persi tra un'esecuzione e l'altra.

[Passo 3 - P1-8] Gli indici di riferimento (^GSPC, FTSEMIB.MI) NON facevano parte di UNIVERSE_FULL e quindi NON venivano aggiornati:
restavano fermi al 25/09/2026 (verifiche EOD e Relative Strength bloccate). Ora sono inclusi esplicitamente. Un fallimento su un
indice fa terminare il processo con codice 1 (visibile nel workflow); un ticker azionario fallito resta non bloccante
(riparte il giorno dopo).

Agganciato a sapta_us_close.yml (21:30 UTC, dopo la chiusura sia di Milano che di Wall Street).
"""
import sys
from datetime import datetime, timezone

from load_historical_data import fetch_and_write
from universe import INDEX_TICKERS, UNIVERSE_FULL


def daily_tickers():
    """Universo operativo piu' indici di riferimento, senza duplicati e con gli indici sempre presenti."""
    return list(dict.fromkeys(list(UNIVERSE_FULL) + list(INDEX_TICKERS)))


def exit_code_for(failed):
    """1 se e' fallito almeno un indice di riferimento; 0 altrimenti (un titolo fallito non e' bloccante)."""
    return 1 if any(t in INDEX_TICKERS for t in failed) else 0


if __name__ == "__main__":
    print(f"🚀 Aggiornamento incrementale prezzi giornalieri: {datetime.now(timezone.utc).isoformat()}")
    total, failed = fetch_and_write(daily_tickers(), period="5d", label="incrementale-5d")
    print(f"\n📊 Totale barre scritte/aggiornate: {total}")
    if failed:
        print(f"⚠️ Ticker falliti ({len(failed)}): {failed}")
    code = exit_code_for(failed)
    if code:
        print(f"❌ Fallito l'aggiornamento di un indice di riferimento: {[t for t in failed if t in INDEX_TICKERS]}")
    else:
        print("✅ Aggiornamento prezzi giornalieri completato")
    sys.exit(code)
