"""
[NUOVO 28/09] cleanup_old_data.py — mai esistito nel repo nonostante fosse
già referenziato in sapta_fast.yml da settimane (step "Cleanup old intraday
data", condizione mai vera - vedi commit che ha corretto lo schedule).
Elimina le barre intraday (interval='15m') più vecchie di RETENTION_DAYS da
public.prezzi. Non tocca MAI l'interval='1d' (storico giornaliero, serve a
lungo termine per SMA200/backtest). H1 legge solo H1_BARS_LOOKBACK=20 barre
15m (meno di un giorno di borsa): RETENTION_DAYS=14 lascia ampio margine per
debug/analisi manuale mantenendo comunque la tabella limitata, dato che i
dati 15m crescono senza limite dal 18/09 (nessuna pulizia è mai avvenuta).
"""
import os
from datetime import datetime, timedelta, timezone
from supabase import create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

RETENTION_DAYS = 14


if __name__ == "__main__":
    cutoff = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).isoformat()
    print(f"🧹 Cleanup dati intraday (15m) più vecchi di {cutoff}")

    try:
        # Conteggio prima della cancellazione, solo per il log - non blocca
        # la cancellazione se fallisce (es. limiti di conteggio esatto).
        before = supabase.table('prezzi').select('id', count='exact') \
            .eq('interval', '15m').lt('timestamp', cutoff).execute()
        n_da_cancellare = before.count if before.count is not None else '?'
        print(f"📊 Righe da cancellare: {n_da_cancellare}")
    except Exception as e:
        print(f"⚠️ Conteggio preliminare fallito (non bloccante): {e}")

    try:
        supabase.table('prezzi').delete().eq('interval', '15m').lt('timestamp', cutoff).execute()
        print("✅ Cleanup completato")
    except Exception as e:
        print(f"❌ Errore durante il cleanup: {e}")
        raise
