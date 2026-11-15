"""
Archivio compresso delle barre 15m piu' vecchie di N mesi (Passo 1, audit 14/11/2026) - SOLA LETTURA sul database.

Esporta le barre in file mensili CSV compressi (gzip) con un manifest (righe, intervallo date, sha256) e poi VERIFICA l'archivio
rileggendo i file e confrontando il numero di righe con quello del database. Questo script NON CANCELLA nulla e non contiene
alcuna istruzione di cancellazione: la rimozione dal DB resta un passo separato, da autorizzare dopo la verifica.

Uso (non eseguito in produzione):
  python src/archivia_barre_15m.py --older-than-months 12 --out archivio_15m
  python src/archivia_barre_15m.py --verify-only --out archivio_15m
"""
import argparse
import csv
import gzip
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

COLS = ['ticker', 'timestamp', 'interval', 'open', 'high', 'low', 'close', 'volume', 'source', 'data_quality_flag']
PAGE = 1000


def month_start(dt):
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def add_months(dt, n):
    y, m = divmod(dt.month - 1 + n, 12)
    return dt.replace(year=dt.year + y, month=m + 1)


def cutoff_from(now, months):
    return add_months(month_start(now), -months)


def _query(client, start, end):
    return (client.table('prezzi').select(','.join(COLS)).eq('interval', '15m')
            .gte('timestamp', start.isoformat()).lt('timestamp', end.isoformat()).order('timestamp'))


def db_count(client, start, end):
    r = (client.table('prezzi').select('ticker', count='exact').eq('interval', '15m')
         .gte('timestamp', start.isoformat()).lt('timestamp', end.isoformat()).limit(1).execute())
    return r.count


def first_month(client):
    r = (client.table('prezzi').select('timestamp').eq('interval', '15m').order('timestamp').limit(1).execute())
    return datetime.fromisoformat(r.data[0]['timestamp']).astimezone(timezone.utc) if r.data else None


def archive(client, cutoff, outdir):
    """Scrive un file per mese fino a 'cutoff' (escluso). Ritorna il manifest. Nessuna scrittura/cancellazione sul DB."""
    os.makedirs(outdir, exist_ok=True)
    first = first_month(client)
    manifest = []
    if first is None:
        return manifest
    start = month_start(first)
    while start < cutoff:
        end = add_months(start, 1)
        rows, offset = [], 0
        while True:
            page = _query(client, start, end).range(offset, offset + PAGE - 1).execute().data or []
            rows += page
            if len(page) < PAGE:
                break
            offset += PAGE
        if rows:
            name = f"prezzi_15m_{start:%Y-%m}.csv.gz"
            path = os.path.join(outdir, name)
            with gzip.open(path, 'wt', newline='', encoding='utf-8') as fh:
                w = csv.DictWriter(fh, fieldnames=COLS)
                w.writeheader()
                w.writerows({c: r.get(c) for c in COLS} for r in rows)
            with open(path, 'rb') as fh:
                digest = hashlib.sha256(fh.read()).hexdigest()
            manifest.append({'file': name, 'mese': f"{start:%Y-%m}", 'righe': len(rows), 'sha256': digest,
                             'da': rows[0]['timestamp'], 'a': rows[-1]['timestamp']})
        start = end
    with open(os.path.join(outdir, 'manifest.json'), 'w', encoding='utf-8') as fh:
        json.dump(manifest, fh, indent=1)
    return manifest


def verify(client, outdir):
    """True solo se, per ogni file: sha256 corretto, righe lette = righe del manifest = righe presenti nel DB nel mese."""
    with open(os.path.join(outdir, 'manifest.json'), encoding='utf-8') as fh:
        manifest = json.load(fh)
    ok = True
    for m in manifest:
        path = os.path.join(outdir, m['file'])
        with open(path, 'rb') as fh:
            good_hash = hashlib.sha256(fh.read()).hexdigest() == m['sha256']
        with gzip.open(path, 'rt', encoding='utf-8') as fh:
            n = sum(1 for _ in csv.DictReader(fh))
        start = datetime.strptime(m['mese'], '%Y-%m').replace(tzinfo=timezone.utc)
        in_db = db_count(client, start, add_months(start, 1))
        good = good_hash and n == m['righe'] == in_db
        print(f"{'OK ' if good else 'KO '} {m['file']}: file={n} manifest={m['righe']} db={in_db} sha={'ok' if good_hash else 'ERRATO'}")
        ok &= good
    return ok


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--older-than-months', type=int, default=12)
    ap.add_argument('--out', default='archivio_15m')
    ap.add_argument('--verify-only', action='store_true')
    a = ap.parse_args()
    from config import supabase
    if not a.verify_only:
        mf = archive(supabase, cutoff_from(datetime.now(timezone.utc), a.older_than_months), a.out)
        print(f"Archiviati {sum(m['righe'] for m in mf)} righe in {len(mf)} file. NESSUNA CANCELLAZIONE ESEGUITA.")
    sys.exit(0 if verify(supabase, a.out) else 1)
