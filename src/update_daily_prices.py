"""
Aggiornamento incrementale prezzi giornalieri (NUOVO 22/09 - audit)

CAUSA RADICE trovata in audit il 22/09: 'prezzi' interval='1d' era fermo al
11/09/2026 su TUTTO l'universo, perché l'unico job che scrive dati
giornalieri (load_historical_data.py) è "one-off" - nessuno schedule
automatico, solo workflow_dispatch manuale. Ogni pagina/modulo che calcola
la direzione confrontando chiusure giornaliere (grafico.php, universo.php,
il briefing) confrontava quindi il prezzo di oggi con uno vecchio di giorni.

Questo script NON sostituisce load_historical_data.py (resta il
caricamento storico iniziale/di recupero) - aggiunge solo l'aggiornamento
INCREMENTALE quotidiano che mancava: riusa la stessa fetch_and_write() già
scritta e testata lì, con un periodo breve ("5d", non 2 anni) per
recuperare eventuali giorni persi tra un'esecuzione e l'altra senza
riscaricare tutto l'universo da zero ogni volta.

Agganciato a sapta_us_close.yml (21:30 UTC, dopo la chiusura sia di Milano
che di Wall Street) - stesso principio di riuso di schedule già usato per
gli altri moduli EOD di questo progetto.
"""
from datetime import datetime, timezone
from load_historical_data import fetch_and_write
from universe import UNIVERSE_FULL

if __name__ == "__main__":
    print(f"🚀 Aggiornamento incrementale prezzi giornalieri: {datetime.now(timezone.utc).isoformat()}")
    total, failed = fetch_and_write(UNIVERSE_FULL, period="5d", label="incrementale-5d")
    print(f"\n📊 Totale barre scritte/aggiornate: {total}")
    if failed:
        print(f"⚠️ Ticker falliti ({len(failed)}): {failed}")
        # Non sys.exit(1) qui, a differenza del caricamento storico completo:
        # un ticker fallito in un aggiornamento incrementale non è grave come
        # in un caricamento iniziale (ripartirà al giorno successivo), non
        # serve far fallire visibilmente l'intero workflow per questo.
    print("✅ Aggiornamento prezzi giornalieri completato")
