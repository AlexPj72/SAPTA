# ChatGPT – Implementazione SAPTA

## Scopo
Questo documento è il registro delle sessioni di lavoro eseguite da ChatGPT sul progetto SAPTA.

**Regola:** non utilizzare `SAPTA_v5_1_1_STATO_IMPLEMENTAZIONE.md` per registrare le modifiche effettuate da ChatGPT. Le attività di ChatGPT vanno registrate esclusivamente in questo file.

---

## Decisioni progettuali da mantenere

### Broker per il futuro trading automatico
- **Broker scelto: Interactive Brokers (IBKR).**
- Alpaca è stato escluso e **non deve essere considerato il broker di riferimento di SAPTA**.
- La scelta di IBKR va mantenuta tra le attività/decisioni del progetto perché il percorso previsto comprende una fase di **paper/virtual trading prima di qualsiasi investimento reale**.
- Requisiti della scelta: supporto dei mercati europei oltre a quelli USA e disponibilità di un ambiente di paper trading/API per validare SAPTA prima dell'operatività reale.
- **Da fare:** integrare/verificare IBKR nel Modulo G / fase di esecuzione quando SAPTA avrà superato le fasi di validazione e paper trading previste.

---

## Cose ancora da fare – Fase 5 / integrazione broker IBKR

1. **Definire l'interfaccia IBKR/API di SAPTA**
   - scegliere il canale API da utilizzare;
   - definire autenticazione/sessione e gestione delle credenziali in sicurezza;
   - definire le funzioni broker necessarie.

2. **Realizzare il modulo broker IBKR**
   - connessione al broker;
   - lettura conto/capitale disponibile;
   - lettura posizioni;
   - invio ordini;
   - modifica e cancellazione ordini;
   - gestione degli esiti e degli errori;
   - registrazione dei dati delle operazioni.

3. **Collegare il broker al motore decisionale SAPTA**
   - dati di mercato → analisi/AI → segnale → risk management → ordine IBKR;
   - impedire l'esecuzione di ordini che non superano i controlli previsti.

4. **Implementare e validare il paper trading IBKR**
   - collegamento all'account paper;
   - verifica di quantità, prezzo, capitale e posizione;
   - simulazione/validazione di ordini, stop loss e take profit;
   - registrazione completa delle operazioni nel database.

5. **Implementare i controlli di sicurezza prima dell'automazione**
   - limite per singola operazione;
   - limite di perdita giornaliera;
   - controllo del capitale disponibile;
   - controllo delle posizioni già aperte;
   - prevenzione degli ordini duplicati;
   - kill switch/blocco immediato dell'esecuzione;
   - logging completo e tracciabilità.

6. **Eseguire i test end-to-end**
   - verificare l'intero flusso da segnale SAPTA a ordine paper IBKR;
   - verificare errori, rifiuti, riconnessioni e casi anomali;
   - validare che i limiti di rischio blocchino correttamente le operazioni.

7. **Solo dopo la validazione paper**
   - valutare il passaggio all'operatività reale;
   - iniziare con capitale limitato e supervisione;
   - non collegare l'account reale prima del completamento dei test e della validazione prevista.

**Nota:** l'integrazione software può essere sviluppata e testata senza collegare ora un account IBKR reale.

---

## Sessione 15/09/2026 – Restyling Dashboard e nuova pagina Universo

### Richiesta
- Creare una nuova pagina `universo.php` per visualizzare l'intero universo dei titoli.
- Mantenere `index.php` come pagina iniziale/home del dashboard.
- Inserire sulla `index.php` i collegamenti alle nuove sezioni.
- Rendere la dashboard più accattivante e meno asettica.

### Modifiche effettuate da ChatGPT

#### 1. Nuova pagina `dashboard/universo.php`
- Creata la pagina Universo completa.
- L'universo viene letto da `ticker_sectors`, quindi è indipendente dai ticker che hanno generato segnali.
- Visualizzazione di ticker, settore, prezzo più recente, variazione giornaliera e mini-grafico (sparkline).
- Indicazione dell'eventuale segnale disponibile.
- Collegamento alla pagina grafico del singolo ticker.
- Aggiunti filtri per ricerca ticker/settore, andamento (tutti/su/giù) e segnali.
- Aggiunto ordinamento per ticker, variazione e prezzo.
- Layout responsive.

**Commit:** `9a6b01970c61ec032a8abebfd8d0fed1e8fe03c7`

#### 2. Aggiornamento `dashboard/index.php`
- `index.php` rimane la homepage del dashboard.
- Aggiunta una testata/hero con stato del sistema, ultimo aggiornamento e capitale.
- Aggiunta barra di navigazione tra Dashboard, Universo, Segnali, Paper Trading e Capitale.
- Aggiunte KPI principali: numero titoli dell'universo, segnali, segnali approvati e capitale.
- Aggiunti collegamenti rapidi alle sezioni principali.
- Mantenute le tabelle dei segnali e dello screening.

**Commit:** `d5bf9ec4bb19e91b42deba55605ee341d013698d`

#### 3. Aggiornamento `dashboard/assets/style.css`
- Rifatto completamente lo stile del dashboard.
- Nuova interfaccia dark/modern con pannelli, card KPI e navigazione più evidente.
- Migliorata gerarchia visiva di titoli, valori e stati.
- Aggiunti badge e indicatori per segnali/variazioni.
- Stile dedicato alla pagina Universo, inclusi toolbar, filtri e sparkline.
- Tabelle e collegamenti più leggibili.
- Layout responsive per dispositivi mobili.

**Commit:** `f294216395eddd8828d0aba22d21c01b3b38fa89`

### Ambito modifiche
- Modificati/creati esclusivamente file del frontend/dashboard.
- **Nessuna modifica al database Supabase.**
- **Nessuna modifica alle pipeline/workflow GitHub Actions.**
- `SAPTA_v5_1_1_STATO_IMPLEMENTAZIONE.md` non è stato modificato.

### Sessione 15/09/2026 – Ripristino `dashboard/index.php`
- Ripristinata la versione precedente di `dashboard/index.php`, su richiesta dell'utente.
- La versione ripristinata corrisponde al blob SHA `23077359ce2b2ea8395e26f87bb041b4865d8491`.
- **Commit:** `bbbebbb304c95fcf49c791edb01c877186e9cbf6`
- `dashboard/universo.php` e il nuovo `dashboard/assets/style.css` non sono stati modificati in questa operazione.

### Stato
Dashboard frontend aggiornato e nuova sezione Universo implementata su `main`; `dashboard/index.php` è stato successivamente riportato alla versione precedente richiesta dall'utente.

---

## Sessione 15/09/2026 – Aggiornamento attività future Fase 5

### Richiesta
- Salvare in `chatgpt_implementazione.md` le attività ancora da completare per l'implementazione della Fase 5 con il broker scelto IBKR.

### Modifica effettuata da ChatGPT
- Aggiunta la sezione **"Cose ancora da fare – Fase 5 / integrazione broker IBKR"** con le attività di progettazione API, modulo broker, collegamento al motore decisionale, paper trading, controlli di sicurezza, test end-to-end e successiva eventuale attivazione reale.
- Nessun altro file del progetto è stato modificato.
- `SAPTA_v5_1_1_STATO_IMPLEMENTAZIONE.md` non è stato modificato.

---

## Sessione 16/09/2026 – Claude: diagnosi H1, Sezione 15/16, restyling dashboard v2

### Richiesta
- Aggiornare la roadmap valutando il piano Fase 5 (IBKR), riverificare le pipeline, completare Rischio di Portafoglio e Ranking finale, poi rifare la dashboard partendo dall'export reale da Aruba: stile più curato ma **chiaro, non dark** (il restyling dark/moderno della sessione 15/09 sopra non era mai stato caricato su Aruba), grafici singoli titoli più leggibili, e un sistema che guidi passo-passo al paper trading con alert spiegati basati su storico e contesto/notizie.

### Modifiche effettuate da Claude

#### 1. Diagnosi H1/H2
- Verificato via query dirette su Supabase: H1 funziona correttamente. Nessun bug — `screening_candidates` a zero righe riflette soglie che raramente scattano insieme + storico intraday ancora corto, non un errore di codice.

#### 2. `src/modulo_e_cost_filter.py` — Sezione 15 (Rischio di portafoglio) + Sezione 16 (Ranking)
- Aggiunta `check_portfolio_exposure()`: esposizione totale stimata vs capitale, soglia placeholder 60%.
- Aggiunta `compute_final_rank_score()`: score 0-100 combinato (anomaly, contesto, confidenza, rendimento netto, qualità dato, rischio). Pesi in `scoring_weights_v1.json` (bump a v3, sezione `ranking_weights`) — placeholder non calibrati.
- Nuove colonne Supabase: `signals_filtered.sector_concentration_count`, `.portfolio_exposure_pct`, `.final_rank_score`.
- **Commit:** `76d8d70e021d3d8e16ec5fa86a7def7482ed3612` (modulo_e), `b325f220f9e18bb324da46b58db097224ae725af` (scoring_weights v3).

#### 3. `dashboard/` — restyling v2 (tema chiaro, sostituisce il dark di questo stesso file sopra)
- Nuovo `assets/style.css` unico e coerente su tutte le pagine (in precedenza `universo.php` referenziava classi assenti dal CSS allora live).
- `grafico.php` riscritto: assi con etichette in €, gridline, tooltip, area fill, target/invalidazione annotati con legenda, etichette X diradate.
- `decisions.php`: guida passo-passo esplicita (5 step) al paper trading + spiegazione del segnale di origine.
- Nuovo `helpers.php` condiviso: navigazione, formattazione, `sparkline_svg()`, e **`spiega_segnale()`** — traduce i punteggi (confidenza, context_score/GDELT, news, rischio di portafoglio) in una spiegazione testuale italiana per ogni segnale, mostrata come tendina "perché?" in dashboard e come pannello fisso nella pagina grafico.
- Tutte le pagine testate in locale (php -l + server PHP integrato con `supabase_query` finta, dati pieni e vuoti): nessun warning/errore.
- File consegnati all'utente come pacchetto scaricabile per il caricamento su Aruba, e committati anche in `dashboard/` nel repo (prima esisteva solo su Aruba senza backup).
- **Commit:** 10 file in `dashboard/` (index, universo, grafico, decisions, capital, signals, anomalies, config, helpers, assets/style.css).

#### 4. `SAPTA_v5_1_1_STATO_IMPLEMENTAZIONE.md`
- **Aggiornato in questa sessione** (a differenza delle sessioni precedenti sopra): sezioni 6, 7, 8, 9 portate da ⬜ a ✅ dove pertinente, aggiunta sezione "0ter. Novità sessione 16/09", aggiornata la lista "Prossima azione consigliata".
- **Commit:** `5e09dc18fa...`

### Ambito modifiche
- Modificati: `src/modulo_e_cost_filter.py`, `src/scoring_weights_v1.json`, tutta la cartella `dashboard/`, `SAPTA_v5_1_1_STATO_IMPLEMENTAZIONE.md`.
- Migrazione Supabase applicata (nuove colonne `signals_filtered`, vedi punto 2). Nessuna modifica alle pipeline/workflow GitHub Actions.

---

## Sessione 17/09/2026 – Claude: Modulo Briefing pre-apertura + Chat AI

### Richiesta
- L'utente voleva sapere prima dell'apertura quali titoli avrebbero avuto rendimenti tipo +2/+4% e una chat AI integrata per ragionarci. Chiarito che la prima parte non è possibile in modo affidabile (limite strutturale dei mercati); costruita invece una shortlist qualitativa ragionata + chat per discuterne.

### Modifiche effettuate da Claude
- Nuovo `src/modulo_briefing.py` + workflow `sapta_briefing.yml` (06:00 UTC Lun-Ven): shortlist giornaliera via Gemini su trend/settore/GDELT/earnings/headline macro, scritta su nuova tabella `daily_briefing`.
- Nuove pagine dashboard: `briefing.php` (shortlist con disclaimer esplicito "non è una previsione") e `chat.php` (conversazione Gemini con contesto reale: briefing, segnali, capitale).
- Nuovi helper in `helpers.php`: `gemini_chat()`, `build_chat_context()`.
- `config.php`: aggiunta costante `GEMINI_API_KEY` (vuota — da compilare dall'utente con la stessa chiave usata nei secret GitHub, non impostata da Claude per non gestire segreti nel repo).
- **Commit:** modulo_briefing.py, sapta_briefing.yml, dashboard/{index,helpers,config,briefing,chat}.php.

### Ambito modifiche
- Nuova tabella Supabase `daily_briefing` (migrazione applicata). Nessuna modifica alle pipeline A/H/B/E esistenti.

---

## Sessione 17/09/2026 (parte 2) – Claude: recepito doc unificato v6, Fase 2 chat (tool layer)

### Documento ricevuto
L'utente ha passato a Claude un documento unificato (ChatGPT) che integra handoff di stato + analisi critica sulla Chat AI + brief v6. Diagnosi condivisa dalle due IA: la Chat AI era "passiva" (contesto fisso pre-caricato, non raccoglieva dati). Sequenza concordata: consolidare/validare PRIMA, ma trasformare la Chat AI (Fase 2 del doc) IN PARALLELO come primo passo verso v6 — non l'intero AI Analyst Team multi-agente (Fase 3+), giudicato complessità prematura su una base non ancora validata da segnali reali.

### Modifiche effettuate da Claude
- `dashboard/helpers.php` + `dashboard/chat.php`: sostituito il contesto fisso con un vero **tool layer** — 4 function declarations Gemini (`get_universe_movers`, `get_ticker_detail`, `get_screening_activity_today`, `get_sector_peers`), loop di function-calling con max 4 round per risposta, ogni tool esegue una query reale su Supabase (nessun dato inventato). Rimossa la frase "non dispongo di analisi previsionali" dalle istruzioni di sistema, sostituita dall'istruzione di spiegare il limite strutturale e poi comunque analizzare con i tool disponibili.
- Testato in locale: tutte le funzioni tool con dati Supabase finti, nessun warning/errore. Il loop di function-calling con Gemini reale non è testabile senza chiave live — verificare al primo uso reale.
- **Commit:** `dashboard/helpers.php` (ad11783631), `dashboard/chat.php` (6c04e7d1e1), `SAPTA_v5_1_1_STATO_IMPLEMENTAZIONE.md`.

### Non fatto in questa sessione (deliberatamente)
- AI Analyst Team multi-agente (Fase 3 del doc v6) — rimandato, serve prima vedere se anche solo la chat con tool layer funziona bene nell'uso reale.
- Tool layer esteso a fonti esterne (premarket data provider, futures) — non disponibili nello stack attuale (yfinance/NewsAPI free non li coprono bene), da valutare se e quando serve davvero.

---

## Sessione 18/09/2026 (parte 2) – Claude: grafici estesi + fix critico affidabilità pipeline

### Modifiche dashboard
- `grafico.php`: aggiunti trend mensile (30gg) e settimanale (5gg, dettaglio 15m); intraday ora filtrato alla sola sessione corrente; bandiera mercato + stato aperto/chiuso indicativo nell'header.
- `universo.php` + `helpers.php`: bandiera mercato (🇺🇸/🇮🇹) per ogni ticker, filtro "Solo USA"/"Solo Italia".
- **Commit:** dashboard/grafico.php, dashboard/helpers.php, dashboard/universo.php.

### Fix critico: affidabilità del cron GitHub Actions
Diagnosi: il cron interno `*/15 9-17 * * 1-5` di `sapta_fast.yml` girava solo 1-2 volte/giorno invece delle ~33 attese - limite noto di GitHub Actions sui cron molto frequenti. Causa radice retroattiva di gran parte dei problemi di dati scarsi delle sessioni precedenti.

Fix: token GitHub fine-grained (repo SAPTA, Actions:write, scadenza 17/12/2026) + cronjob esterno su cron-job.org (ogni 15 min, 9-22 UTC Lun-Ven) che chiama l'API `workflow_dispatch` per forzare l'esecuzione dall'esterno. Verificato e confermato funzionante in produzione dall'utente (grafico intraday ora si popola correttamente).

**Nuova dipendenza esterna da monitorare**: cron-job.org + token con scadenza 90gg (GitHub avvisa via email prima della scadenza, ma va comunque rinnovato manualmente quando arriva l'avviso).

### Stato Modulo AI Watch
Confermato funzionante in produzione: primo alert email reale ricevuto (5 ipotesi su titoli italiani). Telegram confermato funzionante dopo una verifica iniziale.

### Prossimo passo indicato all'utente
Iniziare a registrare vere decisioni di paper trading, ora che il flusso dati è regolare - primo passo concreto verso la validazione operativa già indicata come priorità nei documenti precedenti.

---

## Sessione 19/09/2026 – Claude: Punto 1 di 4, Modulo EOD Verify

### Contesto
L'utente ha portato un'analisi di ChatGPT che confronta manualmente gli alert AI Watch del 18/09 con le chiusure reali (fonte stockanalysis.com/Reuters), concludendo che la combinazione prezzo+volume era il vero segnale operativo. Concordati 4 punti di miglioramento con l'utente, da fare uno alla volta con consegna di file/doc ad ogni punto. Questo è il punto 1.

### Modifiche effettuate da Claude
- `src/modulo_ai_watch.py`: aggiunto campo `entry_price` (prezzo assoluto al momento dell'alert) alle metriche e alla riga salvata su `ai_hypotheses` - serve al nuovo modulo per calcolare la variazione reale a chiusura.
- Nuovo `src/modulo_eod_verify.py`, agganciato a `sapta_us_close.yml` (21:30 UTC): confronta ogni ipotesi del giorno con la chiusura reale, calcola `eod_direction_held` e aggrega su nuova tabella `ai_watch_daily_stats` (breakdown per tipo_anomalia). Automatizza il controllo che ChatGPT ha fatto a mano.
- `dashboard/index.php`: KPI "Affidabilità AI Watch" + colonna "Esito EOD" nella tabella Ipotesi IA.
- **Commit:** modulo_ai_watch.py (06a11ed18f), modulo_eod_verify.py (23edc5f6aa), sapta_us_close.yml (b4c0c142ca), dashboard/index.php (8eeab985ce).
- Testato in locale con dati finti: 3 casi (confermato/invertito/senza entry_price) tutti corretti.

### Prossimi punti (concordati, uno alla volta)
2. Vista unica "Da valutare oggi" + pagina di decisione guidata per singolo titolo
3. Cruscotto paper trading con curva P&L nel tempo
4. Filtro mercato/settore (rimandato, più corposo)

---

## Sessione 19/09/2026 (parte 2) – Claude: Punto 2 di 4, vista e decisione guidata

### Modifiche effettuate da Claude
- Nuovo `dashboard/today.php` ("Da valutare oggi"): unifica segnali operativi reali + ipotesi AI Watch confermate in un'unica lista ordinata per orario, un pulsante "Valuta →" per elemento.
- Nuovo `dashboard/valuta.php`: pagina guidata per singolo titolo - grafico ridotto, spiegazione, rischio (se disponibile), form di decisione che invia a `decisions.php` (riuso, nessuna duplicazione di logica).
- Refactor: funzioni Chart.js estratte in `dashboard/assets/charts.js`, riusate da `grafico.php` e `valuta.php`; corretto un bug potenziale (`Chart.defaults` senza guardia) emerso durante l'estrazione.
- Nuova voce nav "🎯 Da valutare".
- **Commit:** dashboard/today.php (abee86a950), dashboard/valuta.php (d63c91e8f1), dashboard/assets/charts.js (6f27f5cba4), dashboard/grafico.php (b99e7728e7), dashboard/helpers.php (c908b1e7d6).
- Testato in locale: un warning trovato e corretto, resto pulito.

### Prossimi punti
3. Cruscotto paper trading con curva P&L nel tempo
4. Filtro mercato/settore (rimandato)

---

## Sessione 19/09/2026 (parte 3) – Claude: Punto 3 di 4, cruscotto paper trading nel tempo

### Modifiche effettuate da Claude
- `dashboard/decisions.php`: nuova sezione "Andamento nel tempo" con curva P&L cumulato e win rate cumulato (Chart.js, tutto lo storico chiuso, non solo ultime 15).
- Fix bug minore: KPI P&L totale/win rate erano calcolati solo sulle ultime 15 chiuse, ora su tutto lo storico.
- `dashboard/assets/charts.js`: `buildChart()` accetta ora un parametro `unit` ('eur' default o 'pct') per grafici percentuali.
- **Commit:** dashboard/decisions.php (776164843d), dashboard/assets/charts.js (bfdeb73459).
- Testato in locale con 3 posizioni chiuse: curva e KPI corretti, nessun warning.

### Prossimo e ultimo punto
4. Filtro mercato/settore (rimandato - richiede una fonte dati nuova, indice di mercato tipo SPY/FTSE MIB, non presente nello stack attuale)

---

## Sessione 19/09/2026 (parte 4) – Claude: Punto 4 di 4, filtro mercato/settore

### Correzione a quanto detto in precedenza
La parte "settore" non serve una fonte dati nuova - si calcola da dati già presenti (media variazione altri titoli stesso settore). Serve una fonte nuova solo per il mercato generale (indici).

### Modifiche effettuate da Claude
- `src/modulo_a_ingestion.py`: ingestione di 2 indici (`^GSPC` S&P 500, `FTSEMIB.MI` FTSE MIB), esclusi da `TICKERS`/screening.
- Nuovo `src/market_context.py`: `get_market_direction()`, `get_sector_strength()` (fail-open).
- `src/modulo_ai_watch.py`: prompt Gemini ora considera contesto mercato/settore (in linea vs controtendenza) - risposta diretta all'osservazione dell'utente su NFLX/VZ.
- Dashboard: banner mercato in `today.php`, confronto titolo-vs-mercato in `valuta.php`, `get_market_direction_dashboard()` in `helpers.php`.
- **Commit:** modulo_a_ingestion.py (cf2f27ad32), market_context.py (435a260519), modulo_ai_watch.py (d00faf8d9b), dashboard/helpers.php (304ee1dc4d), dashboard/today.php (724266f813), dashboard/valuta.php (5793f2c774).
- Bug trovato e corretto durante lo sviluppo: `get_sector_strength()` non escludeva il ticker stesso dalla media (contraddiceva la propria docstring).
- **Da verificare al primo run reale**: simboli Yahoo Finance degli indici (se uno risulta vuoto nei log, va corretto).

### Chiusura dei 4 punti
Con questo si chiudono tutti e 4 i punti concordati con l'utente il 19/09 a partire dall'analisi ChatGPT sulle mail del 18/09 (verifica esiti automatica, vista/decisione guidata, cruscotto paper trading nel tempo, filtro mercato/settore).

---

## Sessione 20/09/2026 – Claude: Regola sperimentale non operativa

### Contesto
ChatGPT ha proposto una regola aggiuntiva (volume relativo, prezzo, settore, MA20, conferma T+1), osservando che 4 alert AI Watch reali (STM, STLAM, ENEL, PRY) avevano tutti volume relativo <0.15x - la regola li avrebbe scartati tutti. Decisione esplicita con l'utente: regola completamente separata, NON operativa, gerarchia H1/AI Watch invariata - serve solo a validare nel tempo se filtra meglio i falsi segnali, prima di qualunque cambiamento alla pipeline reale.

### Modifiche effettuate da Claude
- Nuovo `src/modulo_experimental_rule.py`, agganciato a `sapta_us_close.yml` dopo EOD Verify: classifica ogni ticker (no_signal_low_volume / watch_low_volume / watch_high_volume_no_direction / candidate_long / candidate_short) e traccia la conferma alla seduta successiva per i soli candidati.
- Nuove tabelle Supabase: `experimental_rule_candidates`, `experimental_rule_daily_stats`.
- `dashboard/index.php`: nuova sezione "🧪 Regola sperimentale (NON operativa)" con statistiche e tabella candidati recenti, distinta visivamente (sfondo viola) dal resto della dashboard operativa.
- **Commit:** modulo_experimental_rule.py (532be2d4d8), sapta_us_close.yml (c726833a36), dashboard/index.php (741d8b74d9).
- Testato in locale: i 4 titoli reali citati classificati correttamente, casi long/short/no-direzione e ciclo di conferma T+1 tutti verificati. Nessun warning.

### Prossimo passo (non ancora fatto)
Tra qualche settimana, con storico sufficiente in `experimental_rule_candidates` + `ai_watch_daily_stats`/EOD Verify: confronto quantitativo tra questa regola e la pipeline attuale, prima di decidere se/dove inserirla nella gerarchia operativa.

---

## Sessione 24/09/2026 – Claude: chiusura audit 21-22/09 (3 cause radice)

### Contesto
L'utente ha portato un audit trasversale (pagine pubbliche pujia.it/sapta/, datato 21-22/09): 0 opportunità/segnali attivi nonostante candidati promossi a B, valori H1/Anomaly apparentemente incoerenti sullo stesso ticker (es. ISRG), caso completo BC (promosso_a_B ma nessun segnale), "Chart.js non disponibile" ricorrente, refuso "1 ricontrolli". A differenza delle sessioni precedenti, Claude ha lavorato con repo clonato via token GitHub fornito dall'utente in chat (fine-grained, scope Contents) + query dirette su Supabase, non solo sui documenti statici.

### Diagnosi (confermata su dati reali, non solo sul codice)
Query Supabase: 154 candidati `promosso_a_B` negli ultimi 7gg, 78 con `b_processed_at` valorizzato nelle ultime 48h, **zero** righe in `signals_raw` (ferma all'11/09) e zero in `scartato_deterioramento`. Il commit del 22/09 di ChatGPT/utente (`6ceb693`, log diagnostico in `calculate_technical_indicators`) aveva già isolato il sintomo ma non la causa. Trovata leggendo il codice: `yf.download()` chiamato una volta per ticker in un loop seriale senza pausa (fino a ~90 chiamate/run) - quasi certamente rate-limit Yahoo Finance sugli IP dei runner GitHub Actions (Modulo A e load_historical_data.py scaricano già a batch, per questo non avevano mai avuto il problema).

### Modifiche effettuate da Claude
- `src/modulo_b_analysis.py`: nuova `fetch_daily_batch()` (batch da 20 ticker + sleep 2s, stesso pattern di `load_historical_data.py`), chiamata una volta a inizio run invece che per-candidato dentro il loop; `calculate_technical_indicators(ticker, daily_df)` riusa il dato prefetchato.
- `src/modulo_h_anomaly.py`: nuova `get_tickers_already_candidate_today()` - H1 non re-inserisce più un ticker con un candidato già aperto oggi (era la causa delle righe "duplicate" ISRG nel radar anomalie).
- `dashboard/grafico.php`: rimossa copia locale morta di `eurTick`/`sparseTicks`/`buildChart` (duplicava `assets/charts.js` dal refactor 19/09, senza guardia su Chart.js mancante - poteva causare un ReferenceError silenzioso dopo l'avviso).
- `dashboard/helpers.php` (nuovo `plural_it()`), `today.php`, `valuta.php`: fix "N ricontrolli" → singolare/plurale corretto.
- `.gitignore` aggiunto, rimossi alcuni `.pyc` committati per errore.
- **Commit:** `071981c` (tutte le modifiche sopra in un solo commit, push diretto su `main` con token fornito dall'utente in chat, non salvato).
- Nessuna soglia di scoring toccata, coerente con la linea "non toccare H1 finché non è chiuso l'audit" già decisa nel documento portato dall'utente.

### Da verificare al prossimo run reale
Che `signals_raw` ricominci a popolarsi dal prossimo ciclo `sapta_slow`. Se il rate-limit Yahoo dovesse persistere anche a batch, valutare una fonte dati alternativa per Modulo B (non ancora necessario, da provare prima con questo fix).

---

## Sessione 24/09/2026 (parte 2) – Claude: prima passata backtest indicatori tecnici

### Contesto
L'utente ha portato un protocollo dettagliato (16 sezioni) per testare se indicatori tecnici aggiuntivi (MA, RSI, MACD, ADX, ATR, Bollinger, ROC, volatilità storica, Relative Strength, gap, supporti/resistenze) aggiungono informazione utile alle anomalie SAPTA, con vincolo esplicito di non toccare la pipeline operativa prima della conclusione del backtest.

### Limite scoperto subito
`screening_candidates` (evento "anomalia SAPTA" nella definizione attuale H1/H2) esiste solo dal 18/09 - 6 giorni, 234 eventi, 88 ticker. +10d e +20d sono quindi DATA_UNAVAILABLE oggi per costruzione (nessun evento ha ancora avuto il tempo di maturare quel numero di giorni di borsa), non per un limite tecnico. +5d praticamente vuoto anch'esso (N=0). Solo +1d/+3d calcolabili, con N modesto e osservazioni non indipendenti (eventi concentrati in 4-6 giornate di mercato).

### Modifiche effettuate da Claude
- Nuovo `scripts/backtest_indicatori.sql`: query riutilizzabile (window functions su Supabase) che calcola SMA20/50/200, RSI14 (media semplice, non Wilder), ATR14/ATR%, Bollinger position, ROC5, volatilità storica 20d AS OF la data di ogni evento (nessun lookahead), e rendimenti successivi a 1/3/5/10/20 giorni di borsa via LEAD().
- Nuovo `BACKTEST_INDICATORI_REPORT.md`: risultati della prima passata, tutti classificati DA VERIFICARE (mai INFORMATIVO) per N piccolo e finestra di mercato troppo corta, coerente con la Sezione 12 del protocollo dell'utente.
- **Non implementati in questa passata** (rimandati): MACD (serve EMA ricorsiva), ADX (serve smoothing +DM/-DM multi-stadio), Relative Strength vs indice/settore, Gap, Supporti/resistenze, combinazioni a 2-3 indicatori.
- **Commit:** stesso commit di `scripts/backtest_indicatori.sql` + `BACKTEST_INDICATORI_REPORT.md`.

### Prossimo passo
Ri-eseguire la stessa query tra 2-3 settimane (per avere +10d) e 5-6 settimane (per +20d). Se richiesto dall'utente, implementare gli indicatori mancanti (MACD/ADX/Relative Strength/Gap) e le combinazioni a 2-3 condizioni prima del prossimo giro. Nessuna modifica alla pipeline operativa nel frattempo.

---
