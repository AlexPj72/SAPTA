"""
SAPTA v5.1 — STEP 2 (pre-migrazione)
Script di sola LETTURA: interroga lo schema reale della tabella `prezzi`
su Supabase e riporta cosa serve fare prima di applicare la migrazione
di `migration_step2_interval.sql`.

Non modifica nulla. Richiede le variabili d'ambiente:
    SUPABASE_URL
    SUPABASE_KEY   (service_role o una chiave con permesso su information_schema)

Uso:
    pip install supabase --break-system-packages
    export SUPABASE_URL=...
    export SUPABASE_KEY=...
    python check_prezzi_schema.py
"""

import os
import sys

try:
    from supabase import create_client
except ImportError:
    print("Manca il pacchetto 'supabase'. Installa con:")
    print("  pip install supabase --break-system-packages")
    sys.exit(1)


def main():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")

    if not url or not key:
        print("ERRORE: imposta SUPABASE_URL e SUPABASE_KEY come variabili d'ambiente.")
        sys.exit(1)

    client = create_client(url, key)

    # Interroga information_schema per ottenere le colonne reali di `prezzi`.
    # Usiamo una funzione RPC generica via query SQL raw, perché il client
    # supabase-py non espone information_schema direttamente.
    query = """
        select column_name, data_type, is_nullable, column_default
        from information_schema.columns
        where table_name = 'prezzi'
        order by ordinal_position;
    """

    try:
        result = client.rpc("execute_sql", {"query": query}).execute()
        columns = result.data
    except Exception:
        # Fallback se non esiste una RPC 'execute_sql' generica nel progetto:
        # prova a leggere una riga della tabella per dedurre le colonne presenti.
        print("Nessuna RPC 'execute_sql' disponibile: provo a dedurre lo schema")
        print("leggendo una riga di esempio dalla tabella `prezzi`.\n")
        sample = client.table("prezzi").select("*").limit(1).execute()
        if not sample.data:
            print("La tabella `prezzi` risulta vuota o non accessibile con questa chiave.")
            sys.exit(1)
        columns = [{"column_name": k, "data_type": "sconosciuto (dedotto)",
                    "is_nullable": "?", "column_default": None}
                   for k in sample.data[0].keys()]

    print("=== Schema attuale rilevato per `prezzi` ===")
    existing_names = set()
    for col in columns:
        existing_names.add(col["column_name"])
        print(f"  - {col['column_name']:<20} {col['data_type']:<20} "
              f"nullable={col.get('is_nullable')} default={col.get('column_default')}")

    print()
    print("=== Verifica requisiti STEP 2 (spec SAPTA v5.1, Sezione 4) ===")

    if "interval" in existing_names:
        print("  [OK] La colonna 'interval' esiste già.")
        print("       -> La migrazione ADD COLUMN va saltata, verificare solo")
        print("          che i valori esistenti siano coerenti con '15m'/'1d'.")
    else:
        print("  [DA FARE] La colonna 'interval' NON esiste.")
        print("            -> Applicare migration_step2_interval.sql così com'è.")

    if "ticker" not in existing_names:
        print("  [ATTENZIONE] Non trovo una colonna 'ticker': verificare il nome")
        print("               reale usato in produzione prima di creare l'indice.")

    if "timestamp" not in existing_names:
        print("  [ATTENZIONE] Non trovo una colonna 'timestamp': verificare il")
        print("               nome reale (es. potrebbe chiamarsi 'ts' o 'created_at').")

    print()
    print("Copia l'output sopra e incollalo nella conversazione prima di")
    print("applicare la migrazione, così i nomi vengono confermati.")


if __name__ == "__main__":
    main()
