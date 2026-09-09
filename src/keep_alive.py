"""
Keep-Alive: mantiene attivo il progetto Supabase free tier.
Nessuna logica di business, solo una query minima per resettare il timer di inattività.
"""
from datetime import datetime, timezone
from config import supabase

if __name__ == "__main__":
    try:
            # Una SELECT leggera su una tabella qualsiasi basta a contare come "attività"
                    supabase.table('costi_operazione').select('id').limit(1).execute()
                            print(f"✅ Keep-alive OK: {datetime.now(timezone.utc).isoformat()}")
                                except Exception as e:
                                        print(f"❌ Keep-alive fallito: {e}")