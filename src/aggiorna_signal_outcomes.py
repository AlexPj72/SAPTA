"""Aggiorna lo storico esiti segnali (signal_outcomes) - NUOVO 20/10/2026.
Chiama la funzione SQL refresh_signal_outcomes(): per ogni riga di signals_raw calcola, sui prezzi giornalieri,
ingresso all'apertura della seduta successiva e rendimenti a 1/3/5 sedute (+ MFE/MAE a 5). Idempotente:
righe COMPLETE/INVALID non vengono toccate, nessun duplicato (chiave = raw_signal_id).
Solo osservazione: non modifica segnali, filtri, regole operative ne' portafogli. Non deve mai bloccare il workflow."""
import sys
from datetime import datetime, timezone

if __name__ == "__main__":
    print(f"Aggiornamento signal_outcomes: {datetime.now(timezone.utc).isoformat()}")
    try:
        from config import supabase
        n = supabase.rpc("refresh_signal_outcomes").execute().data
        print(f"  righe inserite/aggiornate: {n}")
        s = supabase.table("signal_outcomes").select("status").execute().data
        c = {}
        for r in s:
            c[r["status"]] = c.get(r["status"], 0) + 1
        print(f"  stato attuale: {c}")
    except Exception as e:
        print(f"ERRORE aggiornamento signal_outcomes (non bloccante): {e}")
    sys.exit(0)
