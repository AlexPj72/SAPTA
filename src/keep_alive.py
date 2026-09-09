"""
Keep-Alive: mantiene attivo Supabase free tier.
"""
from datetime import datetime, timezone
from config import supabase

if __name__ == "__main__":
    try:
        supabase.table('costi_operazione').select('id').limit(1).execute()
        print(f"Keep-alive OK: {datetime.now(timezone.utc).isoformat()}")
    except Exception as e:
        print(f"Keep-alive fallito: {e}")
