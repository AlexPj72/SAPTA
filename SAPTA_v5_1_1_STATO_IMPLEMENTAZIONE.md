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

- **XGBoost (14-15/09): addestrato, NON pronto per produzione.** Script e
  workflow committati, primo training reale eseguito (split temporale
  2025-01-01, out-of-sample). Risultato: accuracy 44%, di poco sopra il
  livello "predici sempre HOLD" (41.6% della distribuzione test); SELL
  riconosciuto male (recall 0.07). Report completo in
  `XGBOOST_TRAINING_REPORT.md`. Da rivedere (soglie label, feature, bilanciamento
  storico tra ticker) prima di considerarlo un canale utilizzabile.

- **Dashboard (14-15/09): punto 4+5 audit ChatGPT avanzati in parallelo da
  due AI (Claude + ChatGPT), poi riconciliati senza conflitti reali.**
  Aggiunto: `decisions.php` (paper trading, human_decisions con policy
  INSERT/UPDATE), `grafico.php` (storico giornaliero + intraday 15m,
  overlay target/invalidation), colonna target/invalidation in `index.php`,
  fix backend (`target_price` non passava da Modulo B a `signals_filtered`
  — bug reale corretto). ChatGPT ha aggiunto `universo.php` (tutti i ticker
  dell'universo, non solo quelli con segnali) e restyling di `style.css`.
  Verificato live su pujia.it: tutto coerente, nessun lavoro perso. Causa
  di un falso allarme ("vedo solo 3 link"): normale, il link al grafico è
  per-ticker in tabella, non in header. Causa di letture stantie da parte
  di Claude: caching lato Aruba, ora disabilitato dall'utente.
- **Decisione da mantenere (fonte: chatgpt_implementazione.md): broker
  scelto per il futuro trading automatico è Interactive Brokers (IBKR),
  non Alpaca.** Fase 5, solo dopo validazione paper trading completa.

- **Backtest walk-forward (15/09): completato, ultimo punto audit
  ChatGPT.** Modulo F riscritto (era: singola finestra, solo RSI, metriche
  hardcoded a 0.0). Ora: 734 finestre da 6 mesi su 134 ticker,
  rendimento medio +4.69%/finestra, Sharpe 0.56, win rate 94.4%.
  **Caveat da verificare**: mediana 0.00% molto sotto la media suggerisce
  che molte finestre non generano mai un trade (RSI+MACD+BB raramente si
  allineano insieme) — il win rate alto potrebbe basarsi su pochi trade
  reali, non centinaia. **Scomposto (15/09)**: 446/734 finestre (60.8%) senza alcun trade;
  nelle 288 attive, ~1 trade/finestra in media, rendimento medio +14.86%
  quando scatta, ma campione di poche centinaia di trade reali totali —
  incoraggiante ma non statisticamente solido.
  Testato solo il canale rule-based, non IA/XGBoost (storico insufficiente
  per quelli). **Con questo, tutti i 6 punti dell'audit ChatGPT del 14/09
  sono stati affrontati** (non tutti "risolti al 100%", vedi dettagli sopra
  per ciascuno).

- **Verdetto esplicito (15/09): paper trading SÌ pronto per iniziare;
  trading automatico NO, non pronto.** Motivi per l'automatico: campione
  backtest piccolo, ai_agent_decisions mai popolata con dati live (zero
  confronto reale tra i 3 canali), XGBoost debole (44% accuracy), nessuna
  integrazione IBKR nel codice, nessun controllo di rischio testato live.
  Decisione di passare all'automatico da trattare come conversazione
  dedicata separata, non come punto di lista.

## 0ter. Novità sessione 16/09 (riepilogo)

- **Diagnosi H1 chiarita**: dopo un doppio controllo (la prima analisi era
  viziata da un filtro qualità-dato non presente nell'algoritmo reale), **H1
  funziona correttamente**. Al momento del controllo nessun ticker soddisfa
  contemporaneamente `volume_ratio≥3.0` e `price_change≥1.5%`; il quasi-caso
  più vicino (STLAM.MI, -5.01% con volume 3.49x) viene correttamente escluso
  perché la sua ultima barra ha `data_quality_flag='stale'` (mercato di
  Milano già chiuso). `screening_candidates` a zero righe non è quindi un bug,
  solo la conseguenza di soglie che raramente scattano insieme + storico
  intraday ancora corto (8-13 barre/ticker).
- **Rischio di Portafoglio (Sezione 15) e Ranking finale (Sezione 16):
  implementati.** Vedi sezioni 6 e 7 sotto, ora aggiornate da ⬜ a ✅.
- **Dashboard PHP: riscritta completamente (v2).** Nuovo tema chiaro
  coerente su tutte le pagine (prima `universo.php` usava classi CSS
  assenti dal vecchio `style.css` — dashboard incoerente), grafici Chart.js
  con assi/tooltip/area leggibili (prima linee sottili senza indicazioni),
  guida passo-passo al paper trading in `decisions.php`, e nuova funzione
  `spiega_segnale()` (in `helpers.php`) che traduce i punteggi in una
  spiegazione testuale italiana per ogni segnale — risposta alla richiesta
  di "alert spiegati". File committati anche nel repo (cartella
  `dashboard/`, che prima era solo su Aruba senza backup — vedi sezione 9).

## 0quater. Novità sessione 17/09 (riepilogo)

- **Chiarito con l'utente**: nessun sistema può prevedere prima dell'apertura
  quali titoli faranno un preciso +2/+4% quel giorno (limite strutturale dei
  mercati, non di SAPTA — se un metodo lo facesse in modo affidabile,
  smetterebbe di funzionare non appena abbastanza persone lo usassero).
  Ridefinito l'obiettivo realistico insieme all'utente: una shortlist
  qualitativa ragionata stile "nota mattutina di un analista", non una
  previsione validata.
- **Nuovo Modulo Briefing** (`src/modulo_briefing.py`, workflow
  `sapta_briefing.yml`, 06:00 UTC Lun-Ven): per ogni ticker legge
  variazione 1gg/5gg (da `prezzi`), settore, tono GDELT del paese (2
  chiamate cache, non per ticker), earnings entro 1gg; una sola chiamata
  NewsAPI per headline macro del giorno (non per ticker, per non consumare
  la quota free già usata da Modulo B); UNA sola chiamata Gemini con tutto
  il contesto in tabella compatta, che sceglie e motiva le 8 opportunità
  più meritevoli di attenzione. Scrive su nuova tabella `daily_briefing`
  (migrazione applicata). Esplicitamente etichettato ovunque (codice, UI)
  come ipotesi qualitativa non validata da backtest, non una previsione di
  prezzo. Testato in locale con dati/chiamate esterne finte: nessuna eccezione.
- **Nuova Chat AI nella dashboard** (`dashboard/chat.php` + `helpers.php:
  gemini_chat()`/`build_chat_context()`): conversazione con Gemini
  (stessa auth/modello di Modulo I) basata SOLO sul contesto reale (briefing
  di oggi, ultimi segnali, capitale) passato come primo turno della
  conversazione — non inventa prezzi o notizie, e lo dichiara nel prompt di
  sistema. Storia mantenuta in sessione PHP, non persistita su Supabase.
  **Richiede che l'utente inserisca la propria chiave Gemini in
  `dashboard/config.php` (costante `GEMINI_API_KEY`, oggi vuota per non
  esporre segreti nel repo)** — senza chiave la pagina mostra un avviso
  invece di rompersi.
- Nuova pagina `dashboard/briefing.php`: mostra la shortlist del giorno con
  lo stesso disclaimer, link ai grafici, e rimando alla Chat AI.
- **Ricevuto dall'utente un documento unificato (ChatGPT, "SAPTA v6")** con
  audit + critica architetturale alla Chat AI + roadmap. Diagnosi condivisa:
  la Chat AI era troppo "passiva" (rispondeva solo su un contesto fisso
  pre-caricato). Sequenza concordata: prima consolidare/validare quanto
  esiste, **in parallelo** trasformare la Chat AI (Fase 2), poi eventuale
  AI Analyst Team multi-agente (Fase 3+, non ancora iniziata - complessità
  prematura su una base non ancora validata).
- **Fase 2 completata in questa sessione**: `chat.php`/`helpers.php`
  riscritti con vero **tool layer** (function calling Gemini) — 4 funzioni
  (`get_universe_movers`, `get_ticker_detail`, `get_screening_activity_today`,
  `get_sector_peers`) che eseguono query reali su Supabase on-demand,
  invece di un contesto fisso caricato una volta. Eliminata la frase
  "non dispongo di analisi previsionali" dal comportamento atteso, sostituita
  da: spiega il limite strutturale in una frase, poi usa comunque i tool per
  un'analisi sistematica. Testato in locale (tutte le funzioni tool con dati
  finti): nessun warning/errore.

## 0quinquies. Novità sessione 18/09 (riepilogo)

- **Fix grafici**: Chart.js era caricato da CDN esterno (cdnjs.cloudflare.com),
  probabilmente bloccato da ISP italiani o dal browser dell'utente (grafici
  completamente vuoti su ogni titolo, confermato dall'utente in produzione).
  Reso self-hosted: `dashboard/assets/chart.umd.min.js` (scaricato via npm,
  minificato con terser, ~200KB), nessuna dipendenza di rete esterna residua.
  Aggiunto anche un avviso visibile se la libreria non si carica, invece di
  una pagina bianca silenziosa.
- **Nuovo Modulo AI Watch** (`src/modulo_ai_watch.py`), agganciato come step
  aggiuntivo nel workflow `sapta_fast.yml` (stesso schedule di H1: ogni 15
  minuti, 9-17 UTC Lun-Ven — nessuna schedulazione/costo nuovo). Risponde
  alla richiesta esplicita dell'utente: H1 scarta tutto ciò che non supera
  ENTRAMBE le soglie rigide (volume≥3x E prezzo≥1.5%); questo modulo calcola
  le stesse metriche per OGNI ticker con dati sufficienti (stessa regola
  H1_MIN_BARS_FOR_BASELINE=8 e scarto se ultima barra non 'ok') e lascia a
  Gemini il giudizio qualitativo su cosa merita attenzione anche sotto
  soglia. Un solo alert per ticker al giorno (unique index su `ai_hypotheses`
  ticker+data) per evitare spam sullo stesso movimento. Canali di notifica,
  entrambi opzionali/fail-open: **Telegram** (bot API) ed **Email** (SMTP) —
  richiedono che l'utente aggiunga i relativi secret GitHub
  (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `SMTP_HOST`, `SMTP_PORT`,
  `SMTP_USER`, `SMTP_PASSWORD`, `ALERT_EMAIL_TO`) — senza, il modulo salta
  semplicemente l'invio, non blocca la pipeline. Aggiunta anche una sezione
  "Ipotesi IA di oggi" in `dashboard/index.php` per vedere le stesse ipotesi
  anche senza aspettare l'alert push. Testato in locale (calcolo metriche
  con esclusioni corrette per barre insufficienti/dato stale, dedup,
  formattazione messaggio): nessuna eccezione. Il loop reale con Gemini/
  Telegram/SMTP live non è testabile senza credenziali - da verificare al
  primo giorno di mercato aperto con i secret configurati.

## 0sexies. Novità sessione 18/09 (parte 2 - riepilogo)

- **Grafici**: aggiunti trend mensile (30gg) e trend settimanale (ultimi 5
  giorni di mercato, dettaglio 15m) in `grafico.php` - ora 4 grafici totali
  insieme a storico 120gg e intraday sessione corrente (quest'ultimo ora
  filtrato per mostrare solo l'ultima sessione, non un mix di più giorni).
  Aggiunta bandiera mercato (🇺🇸/🇮🇹 - l'universo copre solo USA e Milano,
  nessun titolo di Londra) e indicatore aperto/chiuso indicativo. Aggiunto
  filtro "Solo USA"/"Solo Italia" in `universo.php`.

- **[CRITICO] Trovata e risolta la causa radice di gran parte dei problemi
  di dati scarsi visti nelle sessioni precedenti**: il cron interno di
  GitHub Actions (`*/15 9-17 * * 1-5` in `sapta_fast.yml`) non veniva quasi
  mai onorato - verificato che negli ultimi giorni il workflow girava solo
  1-2 volte al giorno invece delle ~33 attese. È un limite noto e
  documentato di GitHub Actions: i cron molto frequenti (ogni 15 min)
  possono essere ritardati o saltati, specialmente su repository a bassa
  attività. Questo spiega retroattivamente: dati intraday sempre scarsi,
  `screening_candidates` quasi sempre vuota, grafico 15 min che mostrava
  solo apertura/chiusura del giorno prima.
  **Fix**: creato un token GitHub fine-grained (solo repo SAPTA, permesso
  Actions: Read and write, scadenza 2026-12-17 - GitHub avvisa via email
  prima della scadenza) e un cronjob esterno su **cron-job.org** che ogni
  15 minuti (9:00-22:00 UTC Lun-Ven, finestra estesa per coprire sia
  l'apertura di Milano che la chiusura di Wall Street) chiama
  `POST /repos/AlexPj72/SAPTA/actions/workflows/sapta_fast.yml/dispatches`
  per forzare l'esecuzione dall'esterno invece di affidarsi al cron interno.
  Verificato funzionante (risposta 204) e confermato dall'utente in serata:
  il grafico intraday ora si popola correttamente con dati della sessione
  reale. **Dipendenza nuova da tenere a mente**: la pipeline "fast" ora
  dipende da un servizio esterno (cron-job.org) e da un token con scadenza
  a 90 giorni - se il token scade senza essere rinnovato, la pipeline torna
  silenziosamente al comportamento sporadico del cron interno di GitHub
  (che resta comunque presente come schedule di backup in `sapta_fast.yml`,
  solo inaffidabile in frequenza).

- **Modulo AI Watch confermato funzionante in produzione**: primo alert
  email reale ricevuto con 5 ipotesi su titoli italiani (DIA.MI, BC.MI,
  IRE.MI, PST.MI, MONC.MI). Telegram inizialmente silente, poi confermato
  funzionante dall'utente.

- **Prossimo passo suggerito**: iniziare a registrare vere decisioni di
  paper trading (`decisions.php`) nei prossimi giorni di mercato, ora che
  il flusso dati è finalmente regolare - punto di partenza concreto per la
  validazione più volte indicata come priorità nei documenti di progetto.

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
| Concentrazione settoriale tra candidati sopravvissuti a E | ✅ | Esisteva già (v5.1.1, `check_sector_concentration`, max 2 posizioni/settore su 10gg) — soddisfa anche la correlazione approssimata, come permesso esplicitamente dalla spec |
| Correlazione approssimata (settore/mercato) | ✅ | Vedi sopra: coperta dalla stessa funzione, non serve un modello a parte in questa fase |
| Esposizione totale stimata | ✅ | **[NUOVO 16/09]** `check_portfolio_exposure()` in `modulo_e_cost_filter.py`: somma le posizioni BUY approvate + la nuova candidata, declassa a HOLD oltre il 60% del capitale (`MAX_PORTFOLIO_EXPOSURE_PERCENT`, placeholder non calibrato). Nuove colonne `signals_filtered.sector_concentration_count` e `.portfolio_exposure_pct` |

## 7. Ranking finale (Sezione 16)

| Elemento | Stato | Note |
|---|---|---|
| Formula combinata | ✅ | **[NUOVO 16/09]** `compute_final_rank_score()` in `modulo_e_cost_filter.py`: score 0-100 da anomaly_score + context_score + confidence_multiplier + rendimento netto + qualità dato - penalità di rischio. Pesi in `scoring_weights_v1.json` v3 (`ranking_weights`) — **PLACEHOLDER non calibrati**, stesso principio di `context_weights`: da validare col backtest walk-forward prima di dare peso operativo al ranking. Nuova colonna `signals_filtered.final_rank_score`. **Non ancora testato con un segnale reale** — serve un BUY/SELL vero da Modulo B (fermo dall'11/09) |

## 8. Storico e Backtest (Sezioni 21-22)

| Elemento | Stato | Note |
|---|---|---|
| Storico base 2 anni, tutto l'universo | ✅ | **Fatto in questa sessione**: 134/135 ticker, 67.278 righe, copertura 2024-09-11 → oggi. Manca solo `BPSO.MI` (stesso ticker già noto senza sector/industry via yfinance — limitazione nota, non bloccante) |
| Storico esteso 5-6 anni, 15-20 ticker per stress test | ✅ | **Fatto in questa sessione**: 18 ticker (mix LIQ_HIGH/MEDIUM/LOW, settori diversi, incluso l'unico LIQ_LOW disponibile `AVIO.MI`), storico dal 2019-06-03 — copre sia marzo 2020 sia il bear market 2022. Script: `src/load_historical_data.py`, workflow one-off `load_historical.yml` |
| Backtest walk-forward | ✅ | **Completato 15/09** (vedi sezione 0bis e `BACKTEST_WALKFORWARD_REPORT.md`): 734 finestre/6 mesi su 134 ticker, rendimento medio +4.69%/finestra, Sharpe 0.56, win rate 94.4% — ma 60.8% delle finestre senza alcun trade e solo canale rule-based testato (non XGBoost/IA). Campione ancora piccolo, non validante da solo per il ranking (punto 7) |
| Stress test marzo 2020 / bear 2022 | ⬜ | Dati disponibili dal 13/09, backtest dedicato su questi periodi non ancora eseguito separatamente |

## 9. Dashboard PHP (Aruba)

| Elemento | Stato | Note |
|---|---|---|
| Hosting chiarito e strutturato | ✅ | Un account Aruba "Windows & Linux", FTP unico, motore Linux dedicato ai progetti (`lnx.pujia.it/<progetto>/`), motore Windows al sito personale |
| `index.php`, `config.php`, `signals.php`, `anomalies.php`, `capital.php`, `assets/style.css` | ✅ | Creati e pubblicati su `https://lnx.pujia.it/SAPTA/` (nota maiuscole, vedi sezione 0). Verificati funzionanti: leggono segnali, capitale, candidati da Supabase |
| `anomalies.php` aggiornata per leggere `screening_candidates` invece della vecchia tabella `anomalies` | ✅ | Fatto contestualmente alla creazione (non serviva più un fix separato, la tabella legacy non viene nemmeno referenziata nel nuovo codice) |
| `capital.php` — gestione capitale con storico | ✅ | Form di aggiornamento + tabella storico, scrive su `capital_state` via anon key (stesso pattern di sicurezza già accettato per `human_decisions`: anon key resta lato server PHP) |
| Badge fuorviante "HOLD → APPROVATO" in `index.php` | ✅ | Fix sessione 13/09: badge "APPROVATO/DECLASSATO" compare solo per BUY/SELL; HOLD genuino mostra "— nessuna azione" |
| **[NUOVO 16/09] Restyling completo v2** | ✅ | Tema chiaro unico e coerente (Inter, card, badge, KPI), `grafico.php` riscritto con Chart.js leggibile (assi €, gridline, tooltip, area fill, target/stop annotati), `decisions.php` trasformato in guida passo-passo al paper trading, nuovo `helpers.php` condiviso con `spiega_segnale()` (spiegazione testuale di ogni segnale — confidenza, contesto/GDELT, news, rischio di portafoglio). Testato in locale con dati finti (php -l + server PHP, dati pieni e vuoti): nessun errore |
| File PHP nel repo GitHub | ✅ | **Risolto 16/09**: cartella `dashboard/` nel repo ora allineata alla versione v2 deployata su Aruba (backup automatico via commit, non serve più gestire solo da File Manager). Il deploy resta comunque manuale: caricare i file su Aruba dopo ogni commit, non c'è ancora un deploy automatico dal repo |

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

## Prossima azione consigliata (ordine) — aggiornato 16/09

1. **Continuare a monitorare H1/H2** con mercato aperto: nessuna promozione a `screening_candidates` è ancora avvenuta in condizioni reali (confermato non essere un bug, vedi sezione 0ter) — non richiede intervento, solo tempo/osservazione
2. **Caricare la nuova dashboard v2 su Aruba** (file già committati in `dashboard/` nel repo, sezione 9) — sostituire l'intera cartella `sapta/` esistente, cancellare a mano `test_esecuzione.php` se ancora presente
3. **Testare Sezione 15/16 con un segnale reale** appena Modulo B produce un BUY/SELL vero (fermo dall'11/09) — verificare che `sector_concentration_count`, `portfolio_exposure_pct` e `final_rank_score` si popolino come atteso
4. Decidere il capitale operativo per l'avvio del paper trading (oggi placeholder €1.000 in `capital_state`)
5. Calibrare i pesi placeholder (`context_weights`, `ranking_weights`, soglie liquidità) col backtest walk-forward — già disponibile (sezione 8), ma finora testato solo sul canale rule-based: da ripetere includendo il nuovo ranking (punto 7) una volta che ci sono segnali reali da valutare
6. Stress test dedicati su marzo 2020 / bear 2022 (dati disponibili dal 13/09, backtest specifico ancora da lanciare)
7. Avviare in parallelo la pratica di apertura conto IBKR (paper trading) — non blocca i punti sopra, ma la verifica identità richiede tempo (vedi `chatgpt_implementazione.md`)
