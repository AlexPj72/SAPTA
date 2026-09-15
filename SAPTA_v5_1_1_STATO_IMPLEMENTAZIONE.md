# SAPTA v5.1.1 — Stato Implementazione (tracking)

> Aggiornato: sessione del 13/09/2026 (segue sessione del 12/09/2026).
> Da questa sessione in poi Claude ha accesso diretto a Supabase (MCP) e al
> repo GitHub (via token temporaneo passato dall'utente, valido solo per la
> sessione), quindi la verifica non passa più solo dai log riportati in chat
> ma da query/comandi diretti. Il file resta comunque un tracking, non
> l'unica fonte di verità: in caso di dubbio, riverificare su Supabase/GitHub.

## Legenda
- ✅ Fatto e verificato
- 🟡 Fatto ma non ancora committato / non ancora verificato in produzione
- ⬜ Non iniziato
- ⚠️ Rischio noto, da sorvegliare

---

## 0. Novità sessione 13/09 (riepilogo)

Una verifica diretta del repo GitHub e di Supabase ha mostrato che **molti
elementi segnati 🟡/⬜ nella sessione del 12/09 erano in realtà già stati
completati** (commit già fatti, migrazioni già lanciate) — l'opposto del
problema di allucinazione incontrato in precedenza, ma stesso principio:
verificare prima di assumere, in entrambe le direzioni. Aggiornato di
conseguenza l'intero documento (sezioni 1, 4, 5).

Inoltre, in questa sessione:
- **Bug reale trovato e corretto**: `sapta_us_close.yml` non passava
  `--force-reprocess` a Modulo B, quindi il workflow post-chiusura USA
  avrebbe saltato tutti i candidati già processati durante il giorno,
  vanificando il suo scopo (rigenerare il segnale sulla barra definitiva).
  Fix committato e pushato.
- **Nuova tabella `capital_state`**: il capitale usato da Modulo E per il
  position sizing non è più una costante hardcoded (`CAPITAL_EUR = 10000`)
  ma un valore letto a runtime da Supabase, impostabile in qualsiasi momento
  dalla dashboard. Permette di testare capitali diversi, registrare
  depositi/prelievi, e in futuro (Fase 7, Modulo G) aggiornarsi
  automaticamente con i P&L realizzati.
- **Dashboard PHP online**: pubblicata su `https://lnx.pujia.it/SAPTA/`
  (nota: cartella con nome tutto maiuscolo sul server — case-sensitive su
  Linux, tenerne conto in eventuali link/documentazione futura). Verificata
  funzionante: legge segnali, capitale, candidati screening da Supabase.
- **Struttura hosting chiarita**: un solo account Aruba "Hosting Basic
  Windows & Linux", un solo account FTP, due motori paralleli. Sito
  personale su `win.pujia.it`/`www.pujia.it` (Windows), progetti (SAPTA e
  futuri: Fruttorto, trasparenza-territoriale) su `lnx.pujia.it/<nome>/`
  (Linux), ognuno in una propria sottocartella. `www.pujia.it` è stato
  ripuntato verso Linux durante la sessione — verificare che questo non
  abbia rotto il sito personale su Windows in una sessione futura, non
  controllato qui.

---

## 0bis. Novità sessione 14/09 (riepilogo)

- **Modulo I (agente IA Gemini)**: risultava già integrato in
  `modulo_b_analysis.py` come `run_ai_agent()`, ma rotto — autenticazione
  `?key=` incompatibile con le chiavi formato `AQ.` (nuovo standard Google
  da settembre 2026), e modello `gemini-2.5-flash` con RPD 20 troppo basso.
  **Corretto**: auth via header `x-goog-api-key`, modello
  `gemini-3.1-flash-lite` (RPD 500). ✅ Codice pronto, non ancora verificato
  con una decisione reale scritta in `ai_agent_decisions` (vedi sotto).
- **Bug `pandas_ta` risolto**: il pacchetto installato è
  `pandas-ta-classic`, si importa come `pandas_ta_classic`, non `pandas_ta`
  — causava `ModuleNotFoundError` e faceva fallire ogni run di Modulo B.
- **Target price**: verificato che `compute_target()` era già implementato
  e collegato (colonna `target_price` già su Supabase) — nessun intervento
  necessario, punto già chiuso.
- **GDELT e modello XGBoost**: non ancora verificati/iniziati in questa
  sessione.
- **Catena A→H1→H2→B ancora da confermare end-to-end**: dopo i fix, sia
  Fast che Slow Pipeline sono andati a buon fine, ma `screening_candidates`
  risultava ancora vuota (zero candidati promossi) — Modulo A scrive
  regolarmente in `prezzi`, quindi il problema (se reale) è in H1/H2, non in
  A. Potrebbe essere normale (mercato calmo) — da confermare con altri cicli
  nella giornata prima di considerarlo un bug.

- **GDELT (14/09)**: integrato in `compute_context_score()` (modulo_h_anomaly.py)
  via DOC 2.0 API (gratis, no chiave), tono medio per paese su 7gg, peso
  `gdelt_tone: 0.15` in `scoring_weights_v1.json` (v2). Committato, **non
  ancora testato con un run reale**.

- **screening_candidates ancora vuota (14/09, verifica completata)**: ipotesi
  iniziale ("H1 richiede min. 8 barre 15m, non ancora accumulate") **smentita**
  — ticker con più storia hanno già 9 barre, sopra soglia. Causa più probabile
  ora: nessun ticker ha superato contemporaneamente le due soglie H1
  (volume_ratio≥3.0 E |price_change|≥1.5%) — comportamento corretto se vero
  (mercato calmo), ma **non confermato** (impossibile leggere i log del
  workflow dalla sandbox). **Confermato con log reale (15/09, 01:02 UTC)**: "0 candidati
  grezzi trovati su 135 ticker" — comportamento corretto, non un bug. A
  mercati chiusi zero anomalie è normale; da riverificare a mercati aperti
  per vedere il comportamento con volatilità reale.
- **Audit esterno (ChatGPT, file `SAPTA_verifica_stato_2026-09-14.md` in
  root)**: confermate/risolte oggi le sue osservazioni su Modulo I e
  screening vuota (parzialmente, vedi sopra). Punti del suo audit **ancora
  del tutto NON iniziati**: backtest/walk-forward completo, paper trading,
  dashboard/frontend completo (nessun file PHP nel repo), modello XGBoost.
  Non affrontati in questa sessione.

## 1. Database (Supabase)

| Elemento | Stato | Note |
|---|---|---|
| `prezzi.interval` (NOT NULL, check '15m'/'1d') | ✅ | Verificato via `pg_constraint` (sessione 12/09) |
| `prezzi.data_quality_flag` | ✅ | Check allargato a `ok/stale/zero_volume/split/dividend/halt/feed_error` |
| `prezzi` unique `(ticker, interval, timestamp, source)` | ✅ | Coerente con l'upsert di Modulo A |
| `ticker_sectors` (tabella + popolata) | ✅ | 128 righe. 1 ticker (`BPSO.MI`) senza sector/industry (limite yfinance) |
| `screening_candidates` (tabella) | ✅ | Schema confermato |
| `screening_candidates` popolata | ⬜ | Ancora vuota al 12/09 (mercato chiuso, atteso). **Da riverificare lunedì 14/09 con mercato aperto** |
| Indici `screening_candidates(ticker,timestamp)` e `(status)` | ✅ | **Verificato via query diretta in questa sessione**: entrambi esistono (con una piccola ridondanza — due indici quasi identici su ticker+timestamp, innocuo, non prioritario da pulire) |
| `scoring_weights_v1.json` | ✅ | **Verificato nel repo**: `src/scoring_weights_v1.json` esiste |
| `signals_raw` — nuove colonne (`opportunity_type`, `confidence_level`, `confidence_multiplier`, `invalidation_price`, `invalidation_reason`, `has_upcoming_earnings`, `screening_candidate_id`) | ✅ | **Verificato via query diretta**: tutte le colonne esistono già |
| `screening_candidates.b_processed_at` | ✅ | **Verificato via query diretta**: colonna esiste |
| **[NUOVO 13/09]** `capital_state` (tabella) | ✅ | Creata in questa sessione. Append-only: ogni riga è un cambiamento di capitale (`change_type`: manual_set / deposit / withdrawal / realized_pnl-futuro). RLS: lettura pubblica, insert pubblico (stesso pattern di `human_decisions`, pensato per scrittura da dashboard PHP con anon key). Valore iniziale: €1.000 (placeholder) |

## 2. Modulo A (Ingestion)

| Elemento | Stato | Note |
|---|---|---|
| Legge `universe.py` (128 ticker) invece di `config.TICKERS` | ✅ | |
| Scrive `interval='15m'` esplicito | ✅ | |
| Calcola `data_quality_flag` (`stale`/`zero_volume`) | ✅ | Controllo leggero |
| Controllo split/dividendo/halt reale (Sezione 4.2 completa) | ⬜ | Non ancora implementato, dichiarato esplicitamente nel codice |

## 3. Modulo H (Anomaly Radar — H1/H2)

| Elemento | Stato | Note |
|---|---|---|
| Riscrittura H1+H2, workflow aggiornati | ✅ | Invariato dal 12/09 |
| Test reale H1 (workflow_dispatch, mercato chiuso) | ✅ | 0 righe attese, comportamento corretto |
| **Test reale H2 con mercato aperto** | ⬜ | **Prossimo banco di prova: lunedì 14/09**, primo run reale su ~150 ticker |
| Context score: `momentum` e `sector_relative` | ⬜ | Esclusi per ora, dichiarato nel codice |
| Misurazione durata reale job "slow" dopo H2 | ⬜ | Da fare nelle prime 2 settimane dopo il primo run reale |

## 4. Modulo B (Analysis)

| Elemento | Stato | Note |
|---|---|---|
| Legge da `screening_candidates` (status='promosso_a_B') | ✅ | **Corretto rispetto al 12/09**: verificato nel codice del repo, non più "da caricare" |
| Calendario eventi (earnings via yfinance) | ✅ | Presente nel codice, non ancora testato con mercato aperto |
| Verdetto con confidenza esplicita + mappatura a moltiplicatore | ✅ | Presente, legge da `scoring_weights_v1.json`. Euristica non calibrata (v5.1.1 §28 alert 4) |
| Condizione di invalidazione esplicita (`invalidation_price`) | ✅ | Presente nel codice |
| Classificazione tipologia opportunità (incl. 8.4 deterioramento) | ✅ | Presente nel codice |
| News livello 2 (HuggingFace/FinBERT) | ✅ | Invariato dalla v3.1 |
| **[FIX 13/09]** `sapta_us_close.yml` passa `--force-reprocess` | ✅ | **Bug reale trovato e corretto in questa sessione**: mancava, il workflow avrebbe saltato i candidati già processati durante il ciclo slow |
| Decisione: 6 ticker "core" bypassano H1/H2? | ✅ | Deciso: NO, nessuna azione richiesta |

## 5. Modulo E (Cost Filter)

| Elemento | Stato | Note |
|---|---|---|
| Legge settore da `ticker_sectors` invece di `SECTOR_MAP` hardcoded | ✅ | **Corretto rispetto al 12/09**: verificato nel codice, già implementato |
| Slippage per fascia di liquidità (valori default Sezione 12) | ✅ | Verificato nel codice |
| Nuova formula position sizing (basata su `invalidation_price`) | ✅ | Verificato nel codice, sostituisce integralmente la vecchia formula ATR-based |
| **[NUOVO 13/09]** Capitale letto da `capital_state` invece di costante hardcoded | ✅ | `CAPITAL_EUR = 10000` rimossa, sostituita da `get_current_capital()` con fallback fail-open a €1.000 se la tabella è vuota/irraggiungibile. Letto una volta per run, passato esplicitamente a `calculate_position_size()` |
| `CAPITAL_EUR` come valore — nota di decisione | ⚠️ | Il valore operativo ora si imposta dalla dashboard (`capital.php`), non nel codice. **Da decidere**: quale capitale usare per il paper trading di Fase 7 (spec parla di ~1.000€, il placeholder in `capital_state` è €1.000) |

## 6. Rischio di portafoglio (Sezione 15) — nuovo controllo

| Elemento | Stato | Note |
|---|---|---|
| Concentrazione settoriale tra candidati sopravvissuti a E | ⬜ | |
| Correlazione approssimata (settore/mercato) | ⬜ | |
| Esposizione totale stimata | ⬜ | |

## 7. Ranking finale (Sezione 16)

| Elemento | Stato | Note |
|---|---|---|
| Formula combinata | ⬜ | Non iniziato — dipende da punti 4-6 |

## 8. Storico e Backtest (Sezioni 21-22)

| Elemento | Stato | Note |
|---|---|---|
| Storico base 2 anni, tutto l'universo | ✅ | **Fatto in questa sessione**: 134/135 ticker, 67.278 righe, copertura 2024-09-11 → oggi. Manca solo `BPSO.MI` (stesso ticker già noto senza sector/industry via yfinance — limitazione nota, non bloccante) |
| Storico esteso 5-6 anni, 15-20 ticker per stress test | ✅ | **Fatto in questa sessione**: 18 ticker (mix LIQ_HIGH/MEDIUM/LOW, settori diversi, incluso l'unico LIQ_LOW disponibile `AVIO.MI`), storico dal 2019-06-03 — copre sia marzo 2020 sia il bear market 2022. Script: `src/load_historical_data.py`, workflow one-off `load_historical.yml` |
| Backtest walk-forward | ⬜ | Non iniziato — dipende da Rischio di Portafoglio (punto 6) e Ranking (punto 7), non ancora scritti |
| Stress test marzo 2020 / bear 2022 | ⬜ | Dati ora disponibili (vedi sopra), ma il backtest stesso non è ancora scritto |

## 9. Dashboard PHP (Aruba)

| Elemento | Stato | Note |
|---|---|---|
| Hosting chiarito e strutturato | ✅ | Un account Aruba "Windows & Linux", FTP unico, motore Linux dedicato ai progetti (`lnx.pujia.it/<progetto>/`), motore Windows al sito personale |
| `index.php`, `config.php`, `signals.php`, `anomalies.php`, `capital.php`, `assets/style.css` | ✅ | Creati e pubblicati su `https://lnx.pujia.it/SAPTA/` (nota maiuscole, vedi sezione 0). Verificati funzionanti: leggono segnali, capitale, candidati da Supabase |
| `anomalies.php` aggiornata per leggere `screening_candidates` invece della vecchia tabella `anomalies` | ✅ | Fatto contestualmente alla creazione (non serviva più un fix separato, la tabella legacy non viene nemmeno referenziata nel nuovo codice) |
| `capital.php` — gestione capitale con storico | ✅ | Form di aggiornamento + tabella storico, scrive su `capital_state` via anon key (stesso pattern di sicurezza già accettato per `human_decisions`: anon key resta lato server PHP) |
| Badge fuorviante "HOLD → APPROVATO" in `index.php` | ✅ | **Fix in questa sessione**: badge "APPROVATO/DECLASSATO" ora compare solo per BUY/SELL; HOLD genuino mostra "— nessuna azione" (badge grigio neutro) |
| File PHP NON sono nel repo GitHub | ⚠️ | Vivono solo su Aruba, gestiti manualmente via File Manager. Se si perde la copia locale/output di una sessione, non c'è backup automatico — valutare se aggiungerli al repo (es. cartella `dashboard/`) in una sessione futura, anche solo come backup, senza per questo servirli da lì |

## 11. Pezzi mancanti/persi da recuperare (decisione sessione 13/09)

L'utente ha richiesto di completare SAPTA secondo la filosofia originale delle
spec precedenti (v3/v4), recuperando pezzi persi nel passaggio a v5.1.1.
Ordine di lavoro concordato (**tutti e 4, in quest'ordine**):

| # | Attività | Stato | Note |
|---|---|---|---|
| 1 | **Target price (take-profit)** | ⬜ | Mai esistito in nessuna versione. Oggi esiste solo `invalidation_price` (stop). Serve un livello simmetrico esplicito (es. ATR-based o rapporto rischio/rendimento minimo 1:2) in Modulo B, accanto a `invalidation_price` in `signals_raw`. Priorità 1: veloce, sblocca segnali "operativi" completi (entry+stop+target) |
| 2 | **Modulo I (agente IA di ragionamento)** | ⬜ | Previsto in `SAPTA_v4.md` §3 come TERZO CANALE di confronto per la Fase 7 (Umano vs Macchina vs IA), non come sostituto di Modulo B. Riceve dati grezzi post-H2 (non filtrati da E) e produce BUY/SELL/HOLD + confidenza + motivazione testuale via LLM gratuito (Groq Llama 3.3 70B o Gemini 1.5 Flash). L'utente lo vuole ora, non in Fase 7 — spostato in avanti rispetto alla sequenza originale su richiesta esplicita. **Chiarito esplicitamente con l'utente**: non fa proiezioni di prezzo, fa lo stesso tipo di verdetto di Modulo B con ragionamento LLM invece di regole fisse |
| 3 | **Modello XGBoost** | ⬜ | Previsto fin da v2/v3 ("Fase 4: ML e Segnali"), mai realizzato — Modulo B usa tuttora una formula a punteggio manuale (RSI/MACD/Bollinger/sentiment con pesi fissi +1/+2/-1/-2). Ora possibile addestrarlo per davvero: lo storico necessario è stato caricato in questa sessione (punto 8, sopra). Va validato fuori campione, stesso principio del backtest walk-forward già previsto in Sezione 22 |
| 4 | **GDELT (rischio geopolitico)** | ⬜ | Presente esplicitamente in `SAPTA_v3.md`/`SAPTA_v4.md` §5.B ("GDELT per il risk score geopolitico di fondo, Goldstein Scale"), sparito senza spiegazione nel passaggio a v5.1.1 (v5.1.1 non lo menziona né lo rimuove esplicitamente — omissione silenziosa, non decisione dichiarata). Da reintegrare come fattore aggiuntivo nel `context_score` di H2 |

**Decisione esplicita sulla sequenza rispetto al test di domani (14/09):** non ancora
presa esplicitamente dall'utente in chiusura di sessione — la domanda posta era
se toccare Modulo B/H prima o dopo il test di domani mattina con mercato aperto.
**Da confermare alla ripresa**, prima di iniziare il punto 1 (target price, che
tocca `modulo_b_analysis.py`).

**Nota su aspettativa chiarita in questa sessione:** l'utente si aspettava
"proiezioni/premonizioni" sull'andamento futuro del prezzo (una curva prevista).
Chiarito esplicitamente che questo non è mai stato nel design di SAPTA in nessuna
versione, e non è in programma: il sistema classifica anomalie presenti con un
rendimento atteso stimato, non traccia percorsi di prezzo futuri. I punti 1-4
sopra sono la risposta concreta al bisogno reale dietro la richiesta ("come faccio
a sapere quando comprare/vendere, con che limiti"), non un'estensione verso la
previsione grafica.

---

Vedi `SAPTA_v5_1_1_Corretto.md` Sezione 28 per il testo completo:
1. Affidabilità feed RSS Google News — da monitorare
2. Modello di correlazione "approssimato" — da rivalutare dopo primo backtest
3. Durata job "slow" con H2/RSS — provvisoria finché non misurata
4. Calibrazione placeholder (slippage, mappatura confidenza, soglie liquidità) — **blocco esplicito: niente paper trading finché non validati walk-forward**
5. Spazio Supabase con storico esteso — verificare prima di caricare
6. Interazione Modulo G / invalidazione trade come stop-loss bracket — da chiarire prima di STEP 7

---

## Prossima azione consigliata (ordine)

1. **Lunedì 14/09, mercato aperto**: verificare che H1/H2 popolino davvero `screening_candidates` sui ~150 ticker (finora testato solo a mercato chiuso, con 0 righe attese)
2. Osservare la dashboard (`https://lnx.pujia.it/SAPTA/`) durante il primo run reale per un controllo visivo immediato, oltre alle query Supabase dirette
3. Misurare la durata reale del job "slow" con H2/RSS incluso (alert 3, §28) nelle prime esecuzioni
4. Decidere il capitale operativo per l'avvio del paper trading (oggi placeholder €1.000 in `capital_state`) — non bloccante per i test H1/H2, ma da fissare prima della Fase 7
5. Dopo aver confermato H1/H2/B stabili con dati reali: passare al Rischio di Portafoglio (Sezione 15, punto 6 di questo documento), poi al Ranking finale (punto 7)
6. **Storico daily completato** (punto 8) — una volta pronti Rischio di Portafoglio e Ranking, si può passare al backtest walk-forward (Sezione 22), inclusi gli stress test su marzo 2020/bear 2022
