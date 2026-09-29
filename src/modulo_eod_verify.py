"""
Modulo EOD Verify (NUOVO 19/09): verifica automatica degli esiti reali

Risponde alla richiesta dell'utente dopo l'analisi manuale fatta con
ChatGPT sulle mail del 18/09 (confronto alert vs chiusura reale, fatto a
mano confrontando prezzi da stockanalysis.com): SAPTA deve fare da sola,
ogni giorno, quello che ChatGPT ha fatto una volta a mano - controllare se
la direzione indicata da ogni ipotesi AI Watch ha tenuto fino a chiusura.

Agganciato al workflow sapta_us_close (21:30 UTC, dopo la chiusura sia di
Milano - già chiusa da ore a quell'ora - sia di Wall Street) cosi' le
chiusure di entrambi i mercati sono gia' finalizzate, senza bisogno di un
workflow o uno schedule dedicato.

Per ogni ipotesi AI Watch di oggi (qualsiasi stato: in_osservazione,
confermato, invalidato, scaduto):
- legge entry_price (prezzo al momento dell'alert, salvato da
  modulo_ai_watch.py) e il close di oggi da 'prezzi' (interval=1d)
- calcola la variazione reale fino a chiusura ed 'eod_direction_held'
  (la direzione del movimento originale ha tenuto fino a fine giornata?)
- aggrega un riepilogo giornaliero per tipo di anomalia (prezzo/volume/
  debole) su ai_watch_daily_stats - la base dati con cui in futuro si
  potranno calibrare sul serio le soglie di conferma (oggi placeholder
  60%/30%, dichiarati come tali fin dall'inizio in modulo_ai_watch.py)

Fail-open: un ticker senza dati sufficienti viene saltato, non blocca gli
altri.
"""
from datetime import datetime, timezone
from config import supabase


def get_closes_for_date(target_date):
    """Chiusure per una data specifica (non necessariamente 'oggi' - vedi
    fix 29/09) per tutto l'universo, una sola query invece di una per
    ticker (stesso pattern già usato in modulo_briefing.py)."""
    try:
        response = (supabase.table('prezzi')
                    .select('ticker,timestamp,close')
                    .eq('interval', '1d')
                    .gte('timestamp', target_date + 'T00:00:00')
                    .lt('timestamp', target_date + 'T23:59:59')
                    .execute())
    except Exception as e:
        print(f"⚠️ Errore lettura chiusure del {target_date}: {e}")
        return {}
    closes = {}
    for row in response.data or []:
        t = row.get('ticker')
        if t and row.get('close') is not None:
            closes[t] = float(row['close'])  # un solo bar giornaliero per ticker per data, non serve dedup
    return closes


def get_pending_dates():
    """[FIX 29/09] Prima si usava datetime.now(timezone.utc).date() come
    'oggi' sia per filtrare le ipotesi da verificare sia per cercare la
    chiusura in prezzi. Bug: il workflow sapta_us_close è schedulato alle
    21:30 UTC ma GitHub a volte lo ritarda oltre mezzanotte UTC (osservato:
    run delle ipotesi del 28/09 partito alle 01:05 UTC del 29/09) - a quel
    punto 'oggi' per lo script diventava 29/09, mentre le ipotesi da
    verificare erano del 28/09: zero righe trovate, zero statistiche
    scritte, per settimane (dal 19/09). Fix: non usare mai l'orologio di
    sistema per decidere quale giornata verificare - si cercano invece le
    date con ipotesi ancora non verificate (eod_direction_held is null),
    qualunque esse siano. Gestisce anche un eventuale arretrato (più
    giornate mai verificate) in un solo run, invece di una sola volta."""
    try:
        rows = (supabase.table('ai_hypotheses')
                .select('hypothesis_date')
                .is_('eod_direction_held', 'null')
                .not_.is_('entry_price', 'null')
                .execute())
    except Exception as e:
        print(f"⚠️ Errore lettura date in sospeso: {e}")
        return []
    return sorted({row['hypothesis_date'] for row in (rows.data or []) if row.get('hypothesis_date')})


def run_eod_verify_for_date(target_date):
    print(f"📊 Modulo EOD Verify: verifica ipotesi del {target_date}...")

    try:
        rows = (supabase.table('ai_hypotheses')
                .select('id,ticker,price_change_pct,entry_price,tipo_anomalia')
                .eq('hypothesis_date', target_date)
                .is_('eod_direction_held', 'null')
                .execute())
        hypotheses = rows.data or []
    except Exception as e:
        print(f"⚠️ Errore lettura ipotesi del {target_date}: {e}")
        return

    if not hypotheses:
        print("   Nessuna ipotesi da verificare per questa data.")
        return

    closes = get_closes_for_date(target_date)
    if not closes:
        print(f"   Nessuna chiusura disponibile per il {target_date}, riprovo al prossimo giro utile.")
        return

    stats = {'totale': 0, 'confermata': 0}
    per_tipo = {'prezzo': [0, 0], 'volume': [0, 0], 'debole': [0, 0]}  # [totale, confermata]

    for h in hypotheses:
        ticker = h['ticker']
        entry_price = h.get('entry_price')
        close_price = closes.get(ticker)
        if entry_price is None or close_price is None:
            continue  # ipotesi precedenti al fix entry_price, o ticker senza chiusura oggi - salta

        eod_change_pct = round((close_price / entry_price - 1) * 100, 2)
        original_pct = h.get('price_change_pct') or 0
        direction_held = (original_pct >= 0) == (eod_change_pct >= 0)

        try:
            supabase.table('ai_hypotheses').update({
                'eod_close_price': close_price,
                'eod_change_pct': eod_change_pct,
                'eod_direction_held': direction_held,
                'eod_checked_at': datetime.now(timezone.utc).isoformat(),
            }).eq('id', h['id']).execute()
        except Exception as e:
            print(f"⚠️ Errore aggiornamento EOD per {ticker}: {e}")
            continue

        stats['totale'] += 1
        stats['confermata'] += 1 if direction_held else 0
        tipo = h.get('tipo_anomalia')
        if tipo in per_tipo:
            per_tipo[tipo][0] += 1
            per_tipo[tipo][1] += 1 if direction_held else 0

    if stats['totale'] == 0:
        print("   Nessuna ipotesi con entry_price e chiusura disponibili insieme, nessuna statistica da salvare.")
        return

    pct = round(stats['confermata'] / stats['totale'] * 100)
    print(f"   Verificate {stats['totale']} ipotesi: {stats['confermata']} hanno tenuto la direzione ({pct}%)")
    for tipo, (tot, conf) in per_tipo.items():
        if tot:
            print(f"      {tipo}: {conf}/{tot} ({round(conf/tot*100)}%)")

    try:
        supabase.table('ai_watch_daily_stats').insert({
            'stat_date': target_date,
            'n_totale': stats['totale'],
            'n_direzione_confermata': stats['confermata'],
            'n_prezzo': per_tipo['prezzo'][0], 'n_prezzo_confermata': per_tipo['prezzo'][1],
            'n_volume': per_tipo['volume'][0], 'n_volume_confermata': per_tipo['volume'][1],
            'n_debole': per_tipo['debole'][0], 'n_debole_confermata': per_tipo['debole'][1],
        }).execute()
    except Exception as e:
        # probabile giá presente (unique su stat_date) se il job viene rilanciato manualmente
        print(f"⚠️ Statistiche giornaliere non salvate (probabile duplicato): {e}")

    print(f"✅ EOD Verify completato per il {target_date}")


if __name__ == "__main__":
    pending = get_pending_dates()
    if not pending:
        print("📊 Modulo EOD Verify: nessuna data in sospeso da verificare.")
    for d in pending:
        run_eod_verify_for_date(d)
