# SAPTA — Documento Unificato di Aggiornamento Progetto
## Stato al 17/09/2026 + Metodo di lavoro + Roadmap v6

> Questo documento integra tre fonti prodotte lo stesso giorno:
> 1. **Handoff di stato** (tracking dettagliato di ciò che è implementato/testato/da validare in SAPTA v5.1.1);
> 2. **Analisi critica sulla Chat AI** (perché l'attuale chat è "passiva" e cosa deve diventare);
> 3. **Brief tecnico SAPTA v6** (architettura target multi-agente e roadmap di evoluzione).
>
> Obiettivo del documento: fornire un'unica base di contesto, coerente e senza duplicazioni, per riprendere il progetto senza perdere lo storico e senza ripartire da zero.
>
> **Regola di fondo che vale per l'intero documento**: quanto segue è *tracking*, non fonte di verità assoluta. Prima di dichiarare qualcosa come fatto, mancante o da correggere, verificare sempre repository GitHub, Supabase e workflow reali.

---

## 0. Sintesi esecutiva

SAPTA ha superato la fase di prototipo. La pipeline principale (ingestion → anomaly detection → analisi → filtro costi/rischio → ranking), la dashboard, il briefing giornaliero, la chat AI e un primo backtest walk-forward **esistono e funzionano tecnicamente**.

Sono emerse però due esigenze parallele, che questo documento tiene insieme invece di trattare come alternative:

- **Consolidare e validare** ciò che c'è già (calibrazione, stress test, paper trading) — è la priorità immediata, perché nulla di quanto costruito è ancora statisticamente validato.
- **Far evolvere l'architettura** verso SAPTA v6: da pipeline rule-based lineare a sistema multi-canale (Rule Engine + ML + AI Analyst Team) con una Chat AI che smette di essere passiva e diventa un vero analista pre-market capace di raccogliere e ragionare sui dati, non solo di commentare quelli già pronti.

La sequenza corretta è: **prima consolidare/validare quanto esiste, poi costruire il livello AI Analyst Team sopra una base stabile** — non il contrario. Il trading automatico resta esplicitamente fuori scope finché non è completata la validazione (backtest esteso, stress test, paper trading).

---

## 1. Contesto e obiettivo del progetto

SAPTA è un sistema proprietario di analisi e screening di titoli finanziari.

**Non è** un sistema che pretende di prevedere che un titolo farà +2%/+3%/+4% il giorno dopo. **È** un sistema che, prima e durante la giornata di mercato:

1. raccoglie dati di mercato;
2. analizza anomalie di prezzo e volume;
3. analizza contesto e sentiment;
4. analizza news ed eventi;
5. individua titoli meritevoli di attenzione;
6. produce segnali BUY/SELL/HOLD con confidenza e motivazione;
7. definisce target price e invalidazione;
8. considera costi, slippage e rischio di portafoglio;
9. ordina/ranka le opportunità;
10. permette all'utente di discutere i segnali con un agente AI;
11. valida progressivamente il sistema tramite backtest, walk-forward e paper trading;
12. solo in una fase successiva valuta il trading automatico tramite broker.

Il modello concettuale è una **"sala analisti" automatizzata**: dati quantitativi + analisi tecnica + anomalie + news + contesto macro/geopolitico + modelli ML + LLM + gestione del rischio + giudizio finale sintetico — con l'utente che mantiene supervisione, interpretazione e decisione finale.

### Limitazione strutturale da tenere sempre presente

Non esiste un sistema affidabile in grado di sapere prima dell'apertura quali titoli faranno esattamente +2/+3/+4%. Se un modello ci riuscisse in modo sistematico e stabile, la sua efficacia verrebbe erosa dall'utilizzo stesso del segnale. SAPTA quindi ottimizza **selezione, qualità dell'informazione, velocità, ranking, rischio, disciplina, validazione** — non "predizione magica".

---

## 2. Profilo dell'utente (per calibrare il modo di lavorare)

- Competenza avanzata in GIS/QGIS: analisi dei problemi, modellazione logica, analisi territoriale, progettazione di sistemi, workflow.
- Esperienza pregressa (ma arrugginita) in SQL e Python.
- Non vuole reimparare sintassi che l'AI può generare al posto suo.
- Vuole invece: capire cosa chiedere all'AI, verificare ciò che produce, progettare l'architettura, individuare errori logici, strutturare sistemi complessi, validare risultati, supervisionare codice e modelli.

Implicazione operativa: Claude deve fare la parte pesante di implementazione, ma spiegare le scelte in modo che l'utente possa verificarle e decidere, non limitarsi a produrre codice opaco.

---

## 3. Stack tecnologico

GitHub · Supabase · Python · PHP · Aruba Hosting · Gemini API · yfinance · NewsAPI · GDELT · HuggingFace/FinBERT · XGBoost · Chart.js · GitHub Actions.

**Hosting**: Aruba "Hosting Basic Windows & Linux" — sito personale su motore Windows, progetti su motore Linux. SAPTA pubblicato su `https://lnx.pujia.it/SAPTA/` (directory `SAPTA` con maiuscole, Linux è case-sensitive). Il repo GitHub contiene ora anche `dashboard/` (prima esisteva solo sul server). **Il deploy su Aruba resta manuale.**

---

## 4. Architettura attuale (v5.1.1) vs architettura target (v6)

### Pipeline attuale

```
A (ingestion) → H1/H2 (anomaly radar) → B (analysis) → E (cost/risk filter) → output/ranking
```

con canali aggiuntivi: Modulo I (agente AI/Gemini), XGBoost (ML), Modulo F (backtest), Dashboard, Briefing pre-market, futuro Modulo G (gestione operativa/trading).

### Architettura target SAPTA v6

```
                         MARKET DATA
                              │
        ┌─────────────────────┼─────────────────────┐
        ↓                     ↓                      ↓
    PREMARKET                NEWS                MACRO/EVENTI
        └─────────────────────┼─────────────────────┘
                              ↓
                          DATA HUB
                              ↓
                 ┌────────────────────────┐
                 │     AI ANALYST TEAM     │
                 │  Market · Technical ·   │
                 │  News/Sentiment ·       │
                 │  Fundamental · Macro ·  │
                 │  Risk Analyst           │
                 └────────────┬────────────┘
                              ↓
                       CHIEF ANALYST AI
                              ↓
              RULE ENGINE + XGBOOST + AI (confronto canali)
                              ↓
                   DAILY OPPORTUNITY RANKING
                              ↓
                     DASHBOARD + CHAT AI
                              ↓
                        PAPER TRADING
                              ↓
                         VALIDATION
                              ↓
                   EVENTUALE EXECUTION (IBKR)
```

Punto chiave: **la pipeline rule-based attuale (H1→H2→B→E) non va eliminata**. Diventa uno dei tre canali (Rule Engine), affiancato da XGBoost (ML) e da un futuro AI Analyst Team (ragionamento), con un livello di meta-analisi che confronta concordanza/divergenza dei canali senza assumere a priori che la concordanza sia un segnale positivo — va misurata empiricamente sugli outcome reali.

---

## 5. Stato reale al 17/09/2026

### 5.1 Funzionante / implementato

Ingestion · universo ticker (~128, in alcuni storici 134/135) · dati 15m e 1d · quality flag · H1/H2 anomaly radar · Modulo B (tecnica, sentiment, news, earnings, confidence, invalidation, opportunity type, target price) · GDELT (integrato in `compute_context_score()`, peso `gdelt_tone: 0.15`) · Modulo E (settore da Supabase, slippage per liquidità, position sizing su invalidation_price, capitale dinamico, concentrazione settoriale, esposizione portafoglio) · ranking finale (`compute_final_rank_score()`) · storico pluriennale (2 anni + storico esteso 18 ticker dal 2019, copre marzo 2020 e bear 2022) · backtest walk-forward (734 finestre, 6 mesi, 134 ticker) · dashboard PHP v2 (index/signals/anomalies/capital/decisions/grafico/universo/briefing/chat/helpers/config) · briefing giornaliero (06:00 UTC, lun-ven) · Chat AI (Gemini) · Modulo I / Gemini agent (autenticazione e modello corretti) · XGBoost (training iniziale).

**Importante**: "implementato" non equivale a "validato per produzione". Il trading automatico non è pronto; il paper trading è il prossimo passo corretto.

### 5.2 Sperimentale

XGBoost (accuracy ~44% vs baseline HOLD ~41.6%, recall SELL ~0.07 → modello debole, non ancora utilizzabile come canale operativo) · calibrazione confidence · calibrazione ranking · pesi GDELT · soglia esposizione portafoglio (tutti attualmente placeholder, non validati statisticamente).

### 5.3 Da validare

Segnali reali con mercato aperto · confronto AI/rule-based · stress test marzo 2020 · stress test bear 2022 · walk-forward su ranking · walk-forward XGBoost · paper trading.

### 5.4 Non pronto

Trading automatico · integrazione IBKR · esecuzione reale · gestione automatica completa del portafoglio.

### 5.5 Fix e sessioni recenti (13–15/09)

- **Bug corretto**: `sapta_us_close.yml` non passava `--force-reprocess` a Modulo B → rischio di saltare candidati già processati nel giorno. Corretto, committato, pushato.
- **`capital_state`** introdotta: il capitale non è più hardcoded (`CAPITAL_EUR = 10000`); Modulo E lo legge da Supabase a runtime tramite `get_current_capital()` (fallback €1.000). Valore iniziale placeholder per paper trading: **€1.000**. Tabella append-only, `change_type` ∈ {manual_set, deposit, withdrawal, realized_pnl (futuro)}.
- **Modulo I (Gemini)**: era rotto per autenticazione obsoleta (`?key=`) incompatibile con chiavi nel nuovo formato `AQ.` e modello `gemini-2.5-flash` con RPD troppo basso. Corretto con header `x-goog-api-key` e modello `gemini-3.1-flash-lite` (RPD ~500). Codice pronto; da verificare se esistono decisioni reali in `ai_agent_decisions`.
- **Bug pandas**: import corretto è `pandas_ta_classic` (pacchetto `pandas-ta-classic`), non `pandas_ta`. Risolto.
- **Target price**: `compute_target()` già implementato, colonna `target_price` presente su Supabase e collegata alla pipeline.
- **GDELT**: reintegrato (DOC 2.0 API, gratuita, senza chiave, tono medio per paese, finestra 7 giorni). Va considerato fattore di contesto/rischio, non predittore diretto di prezzo.
- **Screening candidates a zero**: analizzato più volte, **non è un bug**. H1 richiede contemporaneamente `volume_ratio ≥ 3.0` e `|price_change| ≥ 1.5%`; nei test nessun ticker soddisfaceva entrambe le condizioni con dati validi (es. STLAM.MI vicino alla soglia ma escluso correttamente per `data_quality_flag = stale`, mercato di Milano già chiuso). Da monitorare con mercato realmente aperto, non da "correggere".
- **Backtest walk-forward** (15/09): riscritto da zero (prima: singola finestra, solo RSI, metriche hardcoded a 0). Nuovo: 734 finestre su 6 mesi, 134 ticker → rendimento medio +4.69%/finestra, Sharpe 0.56, win rate 94.4%, **ma il 60.8% delle finestre (446/734) non ha generato alcun trade**; nelle 288 finestre attive ~1 trade/finestra con rendimento medio ~+14.86%. Interpretazione: risultato interessante ma **non statisticamente sufficiente** per validare SAPTA — campione piccolo, riguarda solo il canale rule-based, non XGBoost né AI.

### 5.6 Rischi noti

| # | Rischio | Nota |
|---|---|---|
| 1 | RSS/Google News | Affidabilità del feed da monitorare |
| 2 | Correlazione | Modello di correlazione approssimato via settore/mercato, non matrice statistica reale |
| 3 | Durata workflow slow (H2/RSS) | Da misurare realmente |
| 4 | Placeholder non calibrati | Slippage, confidence mapping, liquidità, context weights, ranking weights, portfolio exposure |
| 5 | Supabase | Monitorare spazio occupato dallo storico esteso |
| 6 | Modulo G (futuro) | Da chiarire gestione dell'invalidazione come vero stop-loss bracket prima del trading automatico |

---

## 6. Il problema della Chat AI (analisi architetturale)

La Chat AI attuale (`dashboard/chat.php` + `helpers.php`, Gemini) è costruita per **rispondere solo sul contesto che SAPTA le passa già pronto** (briefing del giorno, ultimi segnali, capitale). Se riceve 6 ticker tutti HOLD, conclude correttamente che non c'è altro da dire — ma questo non è il comportamento di un analista pre-market, è il comportamento di un commentatore di dati già confezionati.

**Il problema è architetturale, non di prompt.** Serve trasformare la chat da:

> "Spiegami i dati che ho già raccolto"

a:

> "Analizza autonomamente il mercato prima dell'apertura, raccogli informazioni, confronta i titoli dell'universo SAPTA e costruisci una shortlist motivata."

Perché questo avvenga, la chat deve poter interrogare (non solo ricevere in pancia): dati prezzo/volume recenti, pre-market quando disponibile, variazioni overnight, volatilità, volume anomalo, gap vs chiusura precedente, settore e forza/debolezza relativa, calendario earnings, news societarie e macro, indici di riferimento, futures quando disponibili, sentiment, eventi geopolitici, storico del titolo, segnali H1/H2, ranking SAPTA, capitale e vincoli di rischio.

E soprattutto: **non deve aspettare che Modulo B abbia già prodotto BUY/SELL**. Il Modulo B attuale è downstream rispetto allo screening; la chat/AI Analyst deve poter lavorare *prima*, come analista pre-market.

### Frase da eliminare dal comportamento della chat

> "Non dispongo di analisi previsionali…"

Non perché la chat debba inventare previsioni, ma perché la richiesta dell'utente è un'analisi probabilistica/qualitativa del mercato, non una previsione certa. La risposta corretta è del tipo:

> "Non posso sapere quali titoli saliranno del 2%. Posso però analizzare sistematicamente le informazioni disponibili prima dell'apertura e identificare i titoli con le condizioni più coerenti con un movimento significativo."

Questa è la stessa distinzione già adottata per il Briefing (ipotesi qualitativa ragionata, non previsione).

### Proposta operativa (due modalità, senza eliminare quella esistente)

1. **CHAT — Analisi su richiesta**: l'utente chiede ("Analizza il mercato italiano di oggi", "Confronta UCG col settore bancario"), l'AI raccoglie i dati disponibili tramite tool e risponde.
2. **PRE-MARKET SCAN — automatizzato** (06:00/07:00): Data → Market data → News → Macro → Pre-market → Anomaly detection → Technical analysis → Sector relative strength → Eventi → GDELT → LLM Analyst → 8 titoli da attenzionare → Dashboard.

La chat usa poi quel dataset completo, ma può anche effettuare nuove analisi on-demand. Passo successivo concreto: riscrivere `chat.php` + `helpers.php` + il motore di raccolta dati affinché la chat diventi realmente l'analista pre-market di SAPTA, mantenendo sempre separati i **fatti raccolti** dalle **conclusioni dell'AI**.

---

## 7. SAPTA v6 — AI Analyst Team (architettura target)

L'obiettivo non è un "oracolo del mercato" ma un sistema che replica, per quanto tecnicamente possibile, il processo di lavoro di un analista/trader umano:

```
DATI → RICERCA → ANALISI → CONFRONTO DELLE EVIDENZE → RAGIONAMENTO AI
     → SCENARI → RANKING → SPIEGAZIONE → MONITORAGGIO LIVE → VALUTAZIONE A POSTERIORI
```

### 7.1 I sei agenti proposti

| Agente | Compito | Output concettuale |
|---|---|---|
| **Market Analyst** | Prezzo, volume, volume relativo, volatilità, gap, momentum, trend, premarket, forza relativa vs indici/settore, liquidità | Market condition (Bullish/Neutral/Bearish) + evidenze + evidenze contrarie + rischio |
| **Technical Analyst** | RSI, MACD, Bollinger, ATR, VWAP, medie mobili, supporti/resistenze, breakout/breakdown, volume profile | Distingue segnale significativo vs debole vs contraddittorio |
| **News/Sentiment Analyst** | News, comunicati, earnings, guidance, filing, eventi geopolitici, sentiment | Positiva/Negativa/Neutra/Ambigua **+ Confermata vs Rumor**; fonti sempre registrate |
| **Fundamental Analyst** | Ricavi, utili, EPS, guidance, margini, debito, cash flow, valuation (quando disponibili) | Flag esplicito `fundamental_data_available = true/false` |
| **Macro Analyst** | Calendario macro, Fed, tassi, CPI/PPI, occupazione, PMI, eventi geopolitici, futures indici | Contesto risk-on / risk-off / neutral / uncertain (mai come previsione certa) |
| **Risk Analyst** | Volatilità, liquidità, spread, concentrazione, esposizione settoriale, correlazioni, earnings imminenti, qualità dati/feed | Deve poter **contraddire** gli altri agenti (es. earnings tra 30 minuti → rischio elevato anche con setup tecnico favorevole) |

### 7.2 Chief Analyst AI (componente centrale)

Non riceve un prompt generico ("quali azioni saliranno oggi?"), ma il risultato strutturato degli altri agenti + dati verificabili (market/technical/news/fundamental/macro/risk analysis, rule-based signal, XGBoost output, contesto storico, stato portafoglio, capitale corrente).

Output: `candidate, thesis, supporting_evidence, contradictory_evidence, risk, conditions, confidence, scenario, reasoning`.

**Principio critico**: la confidence dell'AI non va mai presentata come probabilità matematica se non è stata realmente calibrata. Distinguere sempre "AI confidence" da "statistically calibrated probability".

### 7.3 Confronto multi-canale (Rule / ML / AI)

```
RULE ENGINE   XGBOOST   AI TEAM
     └────────────┼────────────┘
                   ↓
            META-ANALYST
                   ↓
            FINAL ANALYSIS
                   ↓
              SHORTLIST
```

Classificare ogni caso come **Full agreement / Partial agreement / Disagreement**, registrare sempre l'outcome reale e verificare *a posteriori* se la concordanza abbia effettivo valore statistico — non assumerlo a priori.

### 7.4 Tool layer per l'AI

L'AI deve avere strumenti strutturati da interrogare durante il ragionamento, non solo testo statico in pancia: `get_premarket()`, `get_market_snapshot()`, `get_intraday_data()`, `get_volume_analysis()`, `get_news()`, `get_company_news()`, `get_sec_filings()`, `get_earnings()`, `get_macro_events()`, `get_sector_data()`, `get_historical_patterns()`, `get_similar_setups()`, `get_current_positions()`, `get_portfolio_risk()`, `get_capital_state()`, `get_previous_briefing()`, `get_previous_ai_decisions()`.

MCP è indicato come possibile layer per esporre questi tool a un agente AI in modo strutturato (`market_data`, `supabase`, `news`, `portfolio`, `backtest`, `signals`, `historical_data`), da introdurre solo se realmente utile — non per aumentare complessità.

### 7.5 Memoria persistente e dataset di apprendimento

La chat attuale mantiene la cronologia solo nella sessione PHP (non persistita). Per v6 serve memoria persistente su: `daily_briefing`, `ai_analysis`, `ai_decisions`, `market_context`, `candidate_history`, `thesis_history`, `outcomes`.

Schema concettuale del dataset di valutazione, da registrare per ogni analisi:
`TIMESTAMP, MARKET_STATE, TICKER, AVAILABLE_DATA, NEWS, TECHNICAL_STATE, FUNDAMENTAL_STATE, AI_ANALYSIS, AI_CONFIDENCE, RULE_SIGNAL, XGBOOST_SIGNAL, FINAL_RANK, THESIS, RISK, OUTCOME`.

Ciclo di apprendimento: Analisi → Decisione/Ipotesi → Mercato reale → Risultato → Confronto → Errore → Analisi dell'errore → Miglioramento. **Non partire dal fine-tuning**: prima accumulare una quantità sufficiente di dati di valutazione reali. Idea "AI che addestra AI": non implementarla subito; prima costruire un Evaluation Engine (AI → Analisi → Risultato reale → Evaluation Engine → errore/causa/categoria/suggerimento), e comunque nessuna AI deve modificare autonomamente il sistema di produzione senza validazione fuori campione.

### 7.6 Principi trasversali obbligatori

- **Anti-allucinazione**: l'AI deve poter dire "non ho dati sufficienti" / "questa informazione non è disponibile" / "le fonti sono discordanti". Mai inventare prezzi, volumi, news, earnings, dati finanziari o risultati storici. Ogni informazione rilevante deve avere una fonte o provenire da Supabase/data provider.
- **Tracciabilità**: ogni decisione AI significativa deve essere ricostruibile — `timestamp, model, prompt/version, input data, tools used, sources, analysis, decision, confidence` — per poter rispondere anche settimane dopo a "perché SAPTA aveva selezionato questo titolo alle 09:17?".
- **Separazione analisi/execution**: `AI ANALYSIS → PROPOSAL → RISK CHECK → PAPER TRADE` resta rigorosamente separato dalla futura `AI ANALYSIS → RISK CHECK → BROKER → REAL ORDER`. La seconda va implementata solo dopo validazione indipendente.
- **No look-ahead bias**: qualunque backtest/valutazione dell'AI deve usare solo informazioni disponibili in quel momento storico (niente look-ahead, survivorship bias, leakage, dati pubblicati dopo l'orario della decisione).
- **Target/invalidation non sono promesse**: SAPTA descrive entry/reference price, target, invalidation, risk/reward come scenario, mai come garanzia sul prezzo futuro.

---

## 8. Metodo di lavoro (regola operativa, vale per ogni sessione futura)

Questa è la regola più importante del documento, ripetuta in tutte e tre le fonti: **non procedere per assunzione**.

### 8.1 Prima di modificare qualsiasi cosa

1. Verificare lo stato del repository GitHub.
2. Verificare lo stato di Supabase.
3. Verificare quali workflow (GitHub Actions) esistono realmente.
4. Verificare quali modifiche sono già state committate.
5. Verificare quali migrazioni sono già state applicate.
6. Verificare quali componenti risultano effettivamente eseguiti (non solo scritti).
7. Distinguere ciò che è solo implementato da ciò che è testato.
8. Distinguere ciò che è testato da ciò che è validato statisticamente.
9. Identificare cosa è placeholder.
10. Solo a questo punto identificare il prossimo esperimento che riduce maggiormente l'incertezza — e agire.

### 8.2 Regola contro le allucinazioni di tracking

- Non dichiarare "manca X" solo perché un documento la segna come ⬜: verificare prima nel codice/DB/workflow/output.
- Non dichiarare "X è implementato" solo perché esiste un file: verificare che sia testato, con dati reali, e idealmente validato.
- **Fonte di verità = repository + database + output reale.** I documenti (compreso questo) sono contesto, non verità assoluta.
- In caso di conflitto tra documento e stato reale: verificare → documentare il conflitto → considerare repo/DB/output come fonte di verità → aggiornare il tracking.

### 8.3 Ciclo per ogni modifica

Verificare → modificare → testare → committare → verificare il deploy. Mai dichiarare "fatto" sulla base del solo codice scritto.

### 8.4 Distinzioni da non confondere mai

"Codice presente" ≠ "testato" ≠ "testato con dati reali" ≠ "validato statisticamente" ≠ "pronto per paper trading" ≠ "pronto per produzione". In particolare: "funziona tecnicamente" ≠ "è statisticamente valido".

### 8.5 Cosa può e non può fare l'LLM

**Può**: sintetizzare, confrontare, ragionare, classificare, spiegare, formulare ipotesi.
**Non deve**: inventare dati/news/prezzi, presentare probabilità non calibrate come scientifiche, trasformare una valutazione qualitativa in previsione certa.

### 8.6 Gerarchia dato → interpretazione (da applicare in ogni output dell'agente)

Distinguere sempre, esplicitamente: **dato osservato** ("il titolo è salito del 3.2% nelle ultime 24 ore") → **segnale derivato** ("il volume è 3.5x la media") → **interpretazione** ("questo può indicare interesse anomalo") → **ipotesi** ("il movimento potrebbe continuare" — questa NON è un fatto).

### 8.7 Principio di non regressione

Non ricostruire il progetto da zero. Non riscrivere moduli già funzionanti senza una ragione tecnica precisa. Non introdurre nuove funzionalità solo perché "potrebbero essere utili" se le validazioni fondamentali non sono ancora state completate. Non aggiungere tecnologia (FastAPI, WebSocket, Redis, vector DB, ecc.) per il solo gusto di aumentare la complessità — solo se realmente necessario.

---

## 9. Step da seguire — roadmap unificata

L'ordine unisce le "prossime azioni prioritarie" dell'handoff v5.1.1 con le "fasi" del brief v6: prima consolidare, poi far evolvere l'architettura verso l'AI Analyst Team, poi validare, solo alla fine valutare l'automazione.

### Fase 0 — Audit completo dello stato reale (da fare per prima, sempre)

Confrontare tracking vs GitHub reale vs Supabase reale vs workflow reali vs dashboard/deployment, componente per componente (Modulo A, H1, H2, Modulo B, Modulo E, XGBoost, Modulo I, GDELT, Briefing, Chat, Dashboard, Backtest, Paper trading), producendo per ciascuno: stato reale, codice, DB, workflow, produzione, problemi, azione.

### Fase 1 — Consolidamento (priorità immediata)

1. **Monitoraggio H1/H2** con mercato realmente aperto, per ottenere finalmente segnali reali. Non modificare H1 senza evidenza concreta di un problema.
2. **Deploy dashboard v2 su Aruba**: sostituire la directory `SAPTA` esistente con la versione nel repo; eliminare `test_esecuzione.php` se ancora presente.
3. **Verifica di un segnale reale end-to-end** quando Modulo B produce un BUY/SELL: `target_price`, `invalidation_price`, `sector_concentration_count`, `portfolio_exposure_pct`, `final_rank_score`, position sizing, spiegazione in dashboard.
4. **Capitale paper trading**: confermare €1.000 come valore operativo di partenza.
5. **Calibrazione** via walk-forward di: context weights, ranking weights, confidence mapping, liquidità, slippage, soglie — mai trattare i placeholder attuali come scientificamente validati.
6. **Stress test dedicati**: marzo 2020 e bear market 2022 (dati già disponibili, test non ancora eseguiti separatamente).
7. **Avvio paper trading** (IBKR paper account), confrontando: segnale SAPTA (rule-based), decisione umana, Modulo I/Gemini, eventuale XGBoost, risultato reale. Registrare per ogni trade: entry, exit, target, invalidation, P&L, costi, slippage, tempo di permanenza, motivo decisione, canale che ha generato il segnale.

Non aggiungere nuova complessità architetturale finché pipeline, database, dashboard, AI agent e briefing non sono coerenti tra loro.

### Fase 2 — Trasformazione della Chat AI in analista pre-market

Riscrivere `chat.php` + `helpers.php` + motore di raccolta dati, mantenendo la modalità "Chat — Analisi su richiesta" esistente e aggiungendo la modalità "Pre-market Scan" automatizzata (06:00/07:00). Eliminare le risposte tipo "non dispongo di analisi previsionali" a favore di risposte che spiegano il limite reale (non prevedere il prezzo) ma offrono comunque un'analisi sistematica.

### Fase 3 — AI Analyst Team (implementazione progressiva)

Ordine consigliato: Market Analyst → Technical Analyst → News/Sentiment Analyst → Fundamental Analyst → Macro Analyst → Risk Analyst → Chief Analyst. Non è necessario implementarli come sette modelli distinti: possono essere ruoli/agenti che condividono lo stesso LLM con tool e contesti diversi.

### Fase 4 — Tool layer

API/funzioni strutturate per far interrogare agli agenti: Supabase, market data, news, macro, storico, portfolio, ranking (eventualmente esposte via MCP).

### Fase 5 — Memoria persistente

Registrare analisi, tesi, decisioni, risultati, errori in tabelle dedicate (vedi §7.5).

### Fase 6 — Evaluation Engine

Sistema che confronta sistematicamente AI vs Rule vs XGBoost con i risultati reali osservati.

### Fase 7 — Paper trading esteso

Uso del sistema completo (multi-canale) in tempo reale senza capitale reale.

### Fase 8 — Validazione statistica

Analizzare, senza fermarsi a una singola metrica: performance, drawdown, precision, recall, expectancy, Sharpe, win rate, loss rate, profit factor, costi, slippage, stabilità per regime di mercato.

### Fase 9 — Eventuale execution

Solo dopo validazione sufficiente: SAPTA → Risk Engine → IBKR Paper → IBKR Live. Broker già deciso: **Interactive Brokers (IBKR)**, non Alpaca — ma non ancora integrato nel codice. Prima dell'execution reale: API, order state, execution state, broker reconciliation, stop/target, failure recovery, duplicate order prevention, kill switch, limite esposizione, audit log.

---

## 10. Obiettivo finale (esperienza utente desiderata)

**Mattina** — l'utente apre SAPTA e trova un vero briefing (mercato, contesto macro, eventi, top opportunities), non solo una lista di ticker.
**Su richiesta** — "Perché XYZ?" → SAPTA analizza i dati reali e risponde con tesi, evidenze pro/contro, rischio.
**Durante la giornata** — "Aggiorna" → SAPTA raccoglie nuovi dati e rivaluta gli scenari; "Cosa è cambiato rispetto alle 09:30?" → confronto tra stato precedente e attuale.
**Fine giornata** — "Come sono andate le tesi di questa mattina?" → confronto tesi vs risultato reale.
**Nel tempo** — il sistema accumula decisioni + risultati + errori e permette di capire quali componenti funzionano davvero.

Questa è la visione di SAPTA v6: non "un chatbot che parla di borsa", ma **un sistema di market intelligence con interfaccia conversazionale AI**, dove il vero prodotto è Data + Analysis + Tools + Models + Memory + Evaluation + Risk, e la chat è solo l'interfaccia.

---

## 11. Nota finale per le prossime sessioni

Quando si riprende SAPTA, l'obiettivo primario non è scrivere subito nuovo codice, ma mantenere continuità progettuale:

1. Se disponibile accesso diretto a GitHub e Supabase, usarlo per verificare lo stato reale prima di proporre modifiche.
2. In caso di conflitto tra questo documento e lo stato reale: verificare, documentare il conflitto, considerare repo/DB/output come fonte di verità, aggiornare il tracking.
3. Non ricostruire il progetto da zero, non riscrivere moduli funzionanti senza motivo tecnico, non aggiungere funzionalità "perché potrebbero servire" prima di aver completato le validazioni fondamentali.
4. Non assumere che una funzione manchi solo perché descritta come "futura" nella roadmap v6: verificare sempre nel codice/DB/workflow reali.

**Priorità attuale, in una frase**: non aggiungere continuamente nuove funzionalità — **validare** quello che esiste (segnali reali, calibrazione, stress test, paper trading), e in parallelo iniziare a trasformare la Chat AI da "spiegatrice di dati pronti" a vero analista pre-market, come primo passo concreto verso l'architettura v6.

---
*Documento compilato integrando: handoff di stato SAPTA v5.1.1 (17/09/2026), analisi architetturale sulla Chat AI, brief tecnico SAPTA v6.*
