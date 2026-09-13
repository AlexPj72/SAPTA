# SAPTA v5.1.1
## Evoluzione architetturale — Radar di anomalie e opportunità (versione corretta, coerente e con alert di sviluppo)

> **VERSIONE:** 5.1.1
> **STATO:** Specifica evolutiva / base di implementazione
> **PRINCIPIO:** preservare il costo operativo attuale a €0, rendere SAPTA progressivamente scalabile, e chiudere le ambiguità logiche emerse nella revisione della v5.0 prima di toccare il codice.

---

## 0. Cosa cambia rispetto alla v5.0

La v5.0 ha introdotto il salto concettuale corretto: **da "segnale BUY/SELL" a "funnel anomalia → opportunità"**. Questa impostazione resta valida e non viene toccata.

La v5.1 ha corretto tre problemi strutturali rimasti aperti nella v5.0, e ha aggiunto le variabili mancanti perché una "previsione forte e sicura" richiede più che uno score di anomalia:

1. **[CORREZIONE v5.1]** Contraddizione tra H2 (usa `news_flag` nello score) e la Sezione 14 (le news si interrogano solo dopo H) — risolta con un modello di news a due livelli.
2. **[CORREZIONE v5.1]** I "pesi di contesto" (trend, settore, momentum ecc.) diventavano variabili impilate senza tracciabilità — trasformati in un oggetto di scoring **versionato e vincolato a validazione out-of-sample**, per non ricreare l'arbitrarietà che si criticava nel vecchio RSI 30/70.
3. **[CORREZIONE v5.1]** Lo slippage era generico — differenziato esplicitamente per fascia di liquidità (USA vs FTSE MIB vs small/mid cap italiane).
4. **[NUOVO v5.1]** Aggiunte le variabili che mancavano per gestire le anomalie con logica anziché con euristiche isolate: regime di mercato, rischio di portafoglio/correlazione, qualità del dato, calendario eventi, invalidazione esplicita del trade, position sizing formalizzato.

### 0.1 Cosa cambia rispetto alla v5.1 (questa revisione, v5.1.1)

Una verifica di coerenza della v5.1 ha trovato tre problemi che vanno chiusi **prima** di scrivere codice, non durante:

1. **[CORREZIONE v5.1.1 — incoerenza dati]** Sezione 21 fissava lo storico a 2 anni, ma la Sezione 22 chiedeva uno stress test su marzo 2020 e sul bear market 2022 — eventi non coperti da una finestra di 2 anni calcolata da oggi. Risolto specificando uno storico esteso solo per il sottoinsieme di ticker usato nello stress test (Sezione 21, Sezione 22).
2. **[CORREZIONE v5.1.1 — ambiguità di implementazione]** La confidenza di B (Sezione 11) era categoriale (alto/medio/basso) ma la formula di ranking (Sezione 16) la trattava insieme a componenti numeriche continue, senza dire come convertirla. Risolto con una mappatura esplicita a moltiplicatore, dentro lo stesso file versionato dei pesi di contesto (Sezione 7, Sezione 11, Sezione 16).
3. **[CORREZIONE v5.1.1 — buco di budget]** Nessuna sezione della v5.1 stimava l'impatto in minuti GitHub Actions delle nuove chiamate esterne (RSS in H2, calendario earnings in B) — l'esatto tipo di omissione che aveva già causato revisioni correttive multiple in v3/v4. Aggiunta una sezione dedicata (19bis) con stima e collocazione esplicita nei workflow.

Oltre a queste tre correzioni, sono stati aggiunti valori di default concreti per lo slippage per fascia (Sezione 12), una fonte RSS concreta invece di generica (Sezione 7, Sezione 17), la conferma esplicita che la nuova formula di position sizing **sostituisce** — non affianca — quella attualmente in `modulo_e_cost_filter.py` (Sezione 13), e una nuova sezione finale di **alert per lo sviluppo futuro** (Sezione 28) che elenca i punti ancora aperti o da sorvegliare durante l'implementazione.

Tutto il resto della v5.0/v5.1 (architettura a imbuto, watchlist ~150, moduli A/H/B/E, vincolo di costo zero) resta valido e non viene riscritto da zero.

---

# 1. Perché SAPTA passa alla v5.1

Oltre alle motivazioni già valide della v5.0:

- una pipeline a imbuto è inutile se lo score che seleziona i candidati si basa su dati che in realtà non sono ancora disponibili in quella fase (vedi punto news);
- un sistema che "pesa" trend, settore, momentum senza un meccanismo di validazione dei pesi non è più affidabile di un RSI 30/70, è solo più complesso da controllare;
- un'anomalia può essere reale nel prezzo ma inutilizzabile se il titolo è illiquido, se c'è un evento macro imminente, o se il dato stesso è sporco (split, dividendo, errore di feed);
- il rischio non si misura solo per singola posizione: un capitale di ~1.000 € concentrato su anomalie correlate (stesso settore, stesso fattore macro) è più fragile di quanto sembri guardando le singole operazioni.

---

# 2. Obiettivo strategico v5.1

Resta quello della v5.0, ma la domanda guida diventa più esplicita:

> **Tra i titoli dell'universo osservabile, quali stanno vivendo una dislocazione statisticamente rilevante, il cui contesto (trend, settore, mercato, eventi, liquidità, qualità del dato) supporta la tesi di opportunità più che quella di trappola, che rimane profittevole dopo costi/slippage realistici, e che non concentra il rischio del portafoglio in un solo fattore comune?**

```text
UNIVERSO
   ↓
QUALITÀ DATO (filtro tecnico)
   ↓
RADAR (H1)
   ↓
ANOMALIA + CONTESTO (H2)
   ↓
VALIDAZIONE (B) — anomalia vs trappola, evento vs rumore
   ↓
COSTI + RISCHIO + SIZE (E)
   ↓
RISCHIO DI PORTAFOGLIO (nuovo controllo)
   ↓
RANKING
   ↓
DECISIONE / ALERT
```

---

# 3. Universo di monitoraggio

## 3.1 Watchlist curata

Confermata l'impostazione v5.0: ~150 titoli (~100 USA alta liquidità, ~40 IT/FTSE MIB), mantenuti in `src/universe.py`.

**[NUOVO v5.1] Filtro minimo di idoneità.** Un titolo entra o resta in watchlist solo se supera soglie minime di liquidità (es. volume medio giornaliero e spread bid-ask stimato entro un limite), altrimenti anomalie "vistose" saranno spesso irraggiungibili senza uno slippage che annulla il rendimento. Questo filtro va applicato in fase di manutenzione manuale della lista, non ad ogni esecuzione.

**[NUOVO v5.1] Fasce di liquidità.** Ogni titolo dell'universo viene taggato con una fascia di liquidità (es. `LIQ_HIGH`, `LIQ_MEDIUM`, `LIQ_LOW`), usata più avanti dal modello di slippage (Sezione 12) e dal position sizing (Sezione 13).

---

# 4. Data layer

## 4.1 Prezzi intraday e storico

Confermato: `interval='15m'` per intraday, `interval='1d'` per storico a 2 anni (base), esteso su un sottoinsieme per lo stress test (Sezione 21), indice `(ticker, interval, timestamp DESC)`.

## 4.2 Qualità del dato — nuovo filtro obbligatorio

**[NUOVO v5.1 — CORREZIONE CRITICA]** Prima che un movimento di prezzo venga considerato un'anomalia, va escluso che sia un artefatto del dato:

- split o reverse split non ancora riflessi correttamente;
- stacco dividendo (gap tecnico, non anomalia di mercato);
- halt di negoziazione o dato mancante interpolato;
- prezzo anomalo per singolo tick/errore di feed (es. spike isolato di una sola candela senza volume corrispondente).

Questo controllo va eseguito **prima** di H1, come pre-filtro sui dati grezzi, altrimenti H1/H2 rischiano di dare punteggio alto a un'anomalia che è semplicemente un errore o un evento societario tecnico non di mercato.

---

# 5. Nuova pipeline v5.1

```text
                 ~150 TITOLI
                      │
                      ▼
              ┌──────────────────┐
              │ A — INGESTION     │
              │ 15 minuti         │
              └─────────┬─────────┘
                        │
                        ▼
              ┌──────────────────┐
              │ QUALITÀ DATO      │  [NUOVO v5.1]
              │ split/div/halt/   │
              │ errori feed       │
              └─────────┬─────────┘
                        │
                        ▼
              ┌──────────────────┐
              │ H1 — RADAR        │
              │ screening leggero │
              └─────────┬─────────┘
                        │
                  ~20–30 candidati
                        │
                        ▼
              ┌──────────────────┐
              │ H2 — ANOMALY      │
              │ score + contesto  │
              │ + news leggere    │  [CORRETTO v5.1]
              └─────────┬─────────┘
                        │
                   ~5–15 candidati
                        │
                        ▼
              ┌──────────────────┐
              │ B — ANALYSIS      │
              │ + news approfondite│ [CORRETTO v5.1]
              └─────────┬─────────┘
                        │
                        ▼
              ┌──────────────────┐
              │ E — COST/RISK     │
              │ + slippage per    │
              │ fascia liquidità  │  [CORRETTO v5.1]
              └─────────┬─────────┘
                        │
                        ▼
              ┌──────────────────┐
              │ RISCHIO PORTAFOGLIO│ [NUOVO v5.1]
              │ correlazione/     │
              │ concentrazione    │
              └─────────┬─────────┘
                        │
                        ▼
                RANKING OPPORTUNITÀ
```

---

# 6. Modulo A — Data Ingestion

Invariato rispetto alla v5.0: acquisizione batch via yfinance sull'`UNIVERSE_FULL`, scrittura in `prezzi` con `interval='15m'`, riconciliazione dove disponibile. Nessuna analisi tecnica pesante in A.

**[NUOVO v5.1]** A deve anche propagare i flag di qualità dato (Sezione 4.2) come parte del record, non lasciarli calcolare a valle in modo implicito.

---

# 7. Modulo H — Anomaly Radar v5.1

## H1 — Screening leggero

Invariato: variazione prezzo, volume relativo, gap, volatilità, velocità del movimento, deviazione dalla dinamica recente. Obiettivo `150 → ~20/30`.

**[NUOVO v5.1]** H1 scarta a monte i titoli con flag di qualità dato negativo (Sezione 4.2), prima ancora di calcolare lo score.

**[INVARIATO — esecuzione]** H1 resta nel workflow "fast": legge solo dati già in `prezzi`, nessuna chiamata esterna aggiuntiva, quindi non impatta il budget minuti (vedi Sezione 19bis).

## H2 — Anomaly Score (0–100)

Componenti confermate dalla v5.0 (volume, variazione, gap, volatilità, velocità, deviazione da media/settore/mercato, liquidità).

**[CORREZIONE v5.1 — news a due livelli.]** La v5.0 usava `news_flag` in H2 ma vietava l'accesso alle news prima di H. Si risolve così:

- **Livello 1 (in H2, leggero e gratuito):** un semplice conteggio di headline recenti da un feed gratuito, senza sentiment analysis. Serve solo a sapere "c'è del rumore informativo intorno a questo titolo sì/no", non a interpretarlo. Basso costo API, compatibile col vincolo di costo zero.
  **[SPECIFICATO v5.1.1]** Fonte concreta: **Google News RSS per ticker/nome titolo** (`https://news.google.com/rss/search?q=...`), non NewsAPI. Motivo: NewsAPI ha già un tetto di 100 richieste/giorno interamente occupato dal ciclo esistente (Modulo B, v3.x) — riusarlo qui ricreerebbe lo stesso collo di bottiglia già risolto con la cache news in v3.1. Il feed RSS di Google News non ha un cap giornaliero rigido comparabile e basta un conteggio di item restituiti, senza parsing del contenuto.
- **Livello 2 (in B, approfondito):** sentiment, contenuto, rilevanza dell'evento, solo sui 5–15 sopravvissuti a H2. Qui il costo per titolo è giustificato perché il campo è già ristretto — resta su HuggingFace Inference API (FinBERT), come da v3.1.

Questo chiude la contraddizione della v5.0 e rende `news_flag` un dato realmente disponibile al momento in cui H2 lo usa.

**[COLLOCAZIONE v5.1.1 — esecuzione H2]** A differenza di H1, H2 effettua chiamate esterne (RSS). Va eseguito nel workflow **"slow"**, non "fast": nel ciclo a 15 minuti il volume di chiamate (fino a 30 candidati × 16 cicli/giorno) supererebbe inutilmente il budget senza alcun vantaggio di tempestività reale su un segnale che comunque verrà validato più a fondo da B. Dettagli quantitativi in Sezione 19bis.

**[NUOVO v5.1] Contesto come sotto-punteggio versionato, non variabili impilate a mano.** Trend (posizione/pendenza SMA200, SMA50 vs SMA200), settore, momentum, distanza da massimi/minimi, volatilità storica: tutte queste variabili confluiscono in un **sotto-score di contesto** separato dall'anomaly score puro, con pesi:

- definiti in un file di configurazione versionato (`scoring_weights_v1.json`), mai hardcoded sparsi nel codice;
- validati esclusivamente tramite backtest fuori campione (Sezione 22), non impostati "a sensazione";
- aggiornabili solo con un nuovo numero di versione, cosicché ogni risultato di backtest sia riproducibile rispetto ai pesi usati in quel momento.

**[AGGIUNTA v5.1.1]** Lo stesso file `scoring_weights_v1.json` deve includere anche la **mappatura esplicita della confidenza categoriale di B a moltiplicatore numerico** (vedi Sezione 11), così che l'intero set di parametri arbitrari del sistema — pesi di contesto e conversione della confidenza — viva in un unico posto versionato, non in due punti diversi del codice.

Questo evita di ricadere nello stesso problema del vecchio RSI 30/70: più variabili, ma altrettanto arbitrarie, se i pesi non sono tracciati e testati.

---

# 8. Tipologie di opportunità

Confermate le tre famiglie della v5.0: **Mean Reversion**, **Momentum/Breakout**, **Event Driven**.

**[NUOVO v5.1]** Va aggiunta esplicitamente una quarta etichetta di uscita da H/B:

### 8.4 Deterioramento strutturale (non-opportunità)
Il movimento non rientra in nessuna delle tre categorie sopra: è coerente con un peggioramento duraturo (fondamentali, guidance, perdita di quota di mercato, causa legale strutturale). Questa etichetta **esce dal funnel senza arrivare al ranking**, ma va comunque registrata in `screening_candidates` con `status = 'scartato_deterioramento'`, perché è dato utile per il backtest e per calibrare H2 in futuro (falsi positivi che oggi vengono scartati manualmente da B potrebbero, con abbastanza storico, essere scartati già da H2).

---

# 9. Tabella `screening_candidates`

Struttura confermata dalla v5.0. **[NUOVO v5.1]** aggiungere i campi:

```text
data_quality_flag       -- esito del controllo Sezione 4.2
news_light_count        -- livello 1, calcolato in H2 (fonte: Google News RSS, v5.1.1)
context_score           -- sotto-score di contesto, versione pesi inclusa
scoring_weights_version -- riferimento al file di configurazione usato
liquidity_bucket        -- LIQ_HIGH / LIQ_MEDIUM / LIQ_LOW
```

Resta valido il principio: un record in questa tabella significa "merita approfondimento", non "va comprato".

---

# 10. Modulo B — Analysis

Invariato nell'impostazione (B riceve i candidati di H + i 6 ticker core quando previsto). B esegue: indicatori tecnici, trend, momentum, **news approfondite (livello 2, vedi Sezione 7)**, rischio, rendimento atteso.

**[NUOVO v5.1] Calendario eventi.** B deve verificare se il titolo ha eventi programmati imminenti (earnings, dividendo, split, dati macro rilevanti per il settore) entro un orizzonte breve (es. 3–5 giorni). Questo perché:

- un'anomalia di tipo *Mean Reversion* o *Momentum* con un earnings imminente ha un profilo di rischio diverso (gap overnight non controllabile con uno stop normale);
- un'anomalia già classificata *Event Driven* deve invece avere l'evento come causa nota e coerente, non come rischio residuo ignoto.

Il calendario eventi può essere ottenuto gratuitamente da yfinance (dati earnings) senza violare il vincolo di costo zero. **[NOTA v5.1.1]** Questa chiamata avviene già nel workflow "slow" sui soli 5-15 sopravvissuti a H2: costo trascurabile, nessuna modifica di collocazione necessaria (vedi Sezione 19bis).

Principio invariato: `H = "È successo qualcosa di interessante?"`, `B = "Quello che è successo è sfruttabile, e a quali condizioni?"`.

---

# 11. Distinzione fondamentale: anomalia ≠ opportunità

Invariata dalla v5.0 (schema OPPORTUNITÀ vs TRAPPOLA). **[NUOVO v5.1]** B deve produrre, oltre al verdetto, un **livello di confidenza esplicito** (es. alto/medio/basso) basato su quanti segnali di contesto convergono nella stessa direzione. Un'anomalia dove trend, settore, evento e mercato puntano tutti nella stessa direzione ha una confidenza diversa da una dove i segnali sono contraddittori — questo distinguo non deve perdersi nel passaggio a un unico score numerico finale.

**[CORREZIONE v5.1.1 — mappatura esplicita a numero.]** La v5.1 lasciava indefinito come una confidenza categoriale (alto/medio/basso) entrasse in una formula di ranking numerica (Sezione 16). Si risolve con una mappatura fissa, dentro `scoring_weights_v1.json`:

```text
confidenza_alto   → moltiplicatore 1.0
confidenza_medio  → moltiplicatore 0.7
confidenza_basso  → moltiplicatore 0.4
```

Questi valori di partenza sono placeholder ragionevoli, non calibrati: vanno validati (o corretti) insieme al resto dei pesi di contesto durante il backtest walk-forward (Sezione 22), non lasciati fissi per assunzione.

---

# 12. Modulo E — Cost Filter

Confermato il ruolo di controllo finale. **[CORREZIONE v5.1] Slippage differenziato per fascia di liquidità.**

Un modello di slippage unico per tutto l'universo sovrastima la fattibilità reale sui titoli meno liquidi. Va quindi applicato un modello per fascia (definita in Sezione 3.1):

```text
LIQ_HIGH   (~100 USA large cap)   → slippage stimato basso, spread stretto
LIQ_MEDIUM (parte FTSE MIB)        → slippage intermedio
LIQ_LOW    (small/mid cap IT)      → slippage più alto, va penalizzato nel ranking
```

**[SPECIFICATO v5.1.1] Valori di default (punto di partenza, da calibrare nel backtest):**

```text
LIQ_HIGH   → slippage stimato 0,05%
LIQ_MEDIUM → slippage stimato 0,15%
LIQ_LOW    → slippage stimato 0,40%
```

Questi valori sono coerenti in ordine di grandezza con gli spread già presenti in `costi_operazione` (`spread_medio_percentuale`) per Alpaca/IBKR e servono solo come punto di partenza operativo per non bloccare STEP 7 in attesa di calibrazione: il backtest (Sezione 22) deve confermarli o correggerli con dati reali, non restare un placeholder permanente.

Ogni fascia deve avere parametri di spread/slippage calibrati separatamente nel backtest (Sezione 22), non un valore unico "medio" che nasconde il rischio reale sui titoli meno liquidi.

E continua a considerare: rendimento lordo atteso, costi stimati, rendimento netto, rischio, concentrazione, dimensionamento.

---

# 13. Position sizing — formalizzazione obbligatoria

**[NUOVO v5.1]** La v5.0 menzionava il dimensionamento solo in termini generici. Va reso esplicito prima del paper trading:

```text
size (n. azioni) = (capitale × rischio_max_per_trade%) / (prezzo_entrata − prezzo_stop)
```

dove:

- `rischio_max_per_trade%` è un parametro configurabile (es. 0,5–1% del capitale per singola operazione, coerente con un capitale iniziale di ~1.000 €);
- `prezzo_stop` deriva da un'invalidazione tecnica esplicita (es. ATR-based), non da un valore arbitrario;
- il calcolo va sempre eseguito **dopo** aver applicato il modello di slippage/fascia di liquidità della Sezione 12, altrimenti il rischio reale è sottostimato.

**[CHIARITO v5.1.1]** Questa formula **sostituisce integralmente** quella attualmente in `modulo_e_cost_filter.py` (`max_risk_per_trade / (atr * 2)`), non va implementata come calcolo parallelo o opzionale. Il motivo: la formula attuale dimensiona in base alla volatilità (ATR) ma non in base a un vero livello di stop definito, quindi due titoli con lo stesso ATR ma stop tecnici a distanze diverse riceverebbero la stessa size — un errore di rischio, non solo un'approssimazione. Va sostituita in STEP 7 (Sezione 25), contestualmente allo slippage per fascia, non in un passaggio successivo separato.

---

# 14. Invalidazione del trade — condizione esplicita di uscita

**[NUOVO v5.1]** Ogni opportunità che arriva al ranking deve portare con sé, non solo un motivo di ingresso, ma una **condizione di invalidazione della tesi**: il livello di prezzo o l'evento che, se raggiunto/verificato, dimostra che l'anomalia non si sta comportando come previsto (es. rottura del livello di supporto usato per il Mean Reversion, notizia societaria che ribalta la tesi Event Driven). Senza questo, il ranking produce solo candidati di ingresso, non operazioni gestibili nel tempo.

---

# 15. Rischio di portafoglio — nuovo controllo prima del ranking finale

**[NUOVO v5.1 — assente nella v5.0]** Il ranking della v5.0 valutava ogni opportunità isolatamente. Con un capitale di ~1.000 € questo è rischioso: due o tre "opportunità" tecnicamente indipendenti possono condividere lo stesso fattore di rischio (stesso settore, stessa area geografica, stessa causa macro) e comportarsi come un'unica posizione concentrata.

Prima del ranking finale, SAPTA deve verificare:

- concentrazione settoriale tra i candidati sopravvissuti a E;
- correlazione storica approssimata tra i candidati (anche una stima semplice basata su settore/mercato è sufficiente in questa fase, senza bisogno di un modello di correlazione complesso);
- esposizione totale stimata se tutte le opportunità in cima al ranking venissero eseguite insieme.

Questo controllo non genera un nuovo modulo pesante: è un filtro applicato all'output di E, prima della pubblicazione del ranking.

---

# 16. Ranking delle opportunità

Confermato l'impianto v5.0 (score combinato, non lista BUY indistinta). Il punteggio finale deve combinare almeno:

- qualità dell'anomalia (H2);
- sotto-score di contesto (versionato, Sezione 7);
- confidenza del verdetto di B (Sezione 11), **applicata come moltiplicatore numerico secondo la mappatura di Sezione 11**, non come etichetta testuale;
- rendimento atteso netto (dopo slippage per fascia di liquidità, valori di default Sezione 12);
- rischio per singola posizione e contributo al rischio di portafoglio (Sezione 15);
- qualità del dato (Sezione 4.2).

**[CONFERMATO v5.1]** La formula finale resta da validare con backtest fuori campione e non va fissata arbitrariamente — principio già corretto nella v5.0, qui esteso anche ai pesi di contesto (Sezione 7) e alla mappatura di confidenza (Sezione 11).

---

# 17. News e API

Confermato e ora reso coerente (Sezione 7): livello 1 leggero in H2 su ~20–30 candidati (fonte: Google News RSS, v5.1.1), livello 2 approfondito in B su ~5–15 candidati (HuggingFace Inference API / FinBERT). Nessuna interrogazione indiscriminata sui 150 titoli.

---

# 18. Settori

Invariato dalla v5.0: settore recuperato automaticamente da yfinance, salvato in tabella Supabase dedicata, usato per il confronto titolo vs settore.

---

# 19. Costi: principio fondamentale

Invariato: nessun feed a pagamento, nessun server sempre acceso a pagamento, nessun abbonamento premium, nessuna copertura globale completa nella v5.1. Si sfrutta GitHub Actions, yfinance, Supabase free tier, API gratuite entro i limiti — incluso il feed RSS gratuito per le news di livello 1 (Sezione 7) e il calendario earnings gratuito di yfinance (Sezione 10).

---

# 19bis. Budget minuti GitHub Actions per H2 e calendario eventi [NUOVO v5.1.1]

**Perché questa sezione manca nella v5.1 ed è un problema:** ogni revisione precedente del progetto (v3.1, v3.3, v3.5, v4.1) è nata da un conto dei minuti GitHub Actions che non tornava. La v5.1 introduce due nuove fonti di chiamate esterne (RSS in H2, calendario earnings in B) senza stimarne l'impatto. Questa sezione chiude il buco prima di STEP 5/6, non dopo averli implementati.

**Stima del carico aggiuntivo:**

| Chiamata | Dove | Volume per ciclo | Cicli/giorno (workflow slow) | Chiamate/giorno |
|---|---|---|---|---|
| RSS Google News (H2, livello 1) | slow | ~20-30 candidati | ~16 | ~320-480 |
| Calendario earnings yfinance (B, già in Sezione 10) | slow | ~5-15 sopravvissuti | ~16 | ~80-240 |

Un feed RSS via `requests`/parsing XML è leggero (nessuna libreria ML aggiuntiva, nessun impatto sul tempo di installazione delle dipendenze) — il costo in **minuti** resta contenuto perché non cambia la voce che pesa di più sul tetto (installazione pacchetti pesanti, vedi v3.1 §3.1), ma cambia il **tempo di esecuzione per run**: 20-30 richieste HTTP sequenziali per ciclo possono aggiungere decine di secondi a ogni esecuzione del workflow "slow". Va quindi:

1. **Confermato che H2 gira in "slow", non in "fast"** (già specificato in Sezione 7) — un ciclo a 15 minuti con fino a 30 chiamate RSS per esecuzione avvicinerebbe il sistema al tetto senza necessità, dato che H2 non deve reagire in tempo reale quanto H1.
2. **Misurata la durata reale del job "slow" dopo l'implementazione** (non solo stimata a tavolino) nelle prime due settimane, esattamente come già raccomandato in v3.5 per il monitoraggio dei minuti — qui il rischio non è il numero di run ma la durata di ciascuno.
3. **Prevista una soglia di timeout/fallback**: se il feed RSS non risponde entro un tempo limite per un ticker, quel ticker prosegue nel funnel con `news_light_count = null` invece di bloccare l'intero job — coerente con l'approccio "fail-open" già usato nel controllo di concentrazione settoriale del Modulo E (v3.2).

**Nessuna stima definitiva di minuti/mese è possibile prima di misurare la durata reale del job con le chiamate RSS incluse** — a differenza delle stime precedenti (v3.x/v4.x) basate su installazione di dipendenze, qui la variabile dominante è la latenza di rete di chiamate sequenziali, molto più difficile da stimare a priori. Vedi Sezione 28 (alert 3).

---

# 20. Evoluzione futura senza rifare SAPTA

Invariato dalla v5.0: il feed dati può essere sostituito (yfinance → feed professionale real-time) senza riscrivere H/B/E, purché l'interfaccia dati resti stabile.

---

# 21. Storico

**[CORRETTO v5.1.1 — era "Storico 2 anni" nella v5.1]**

Storico base: `interval='1d'`, **2 anni**, su tutto l'universo (~150 titoli) — necessario per baseline, calibrazione score, backtest ordinario, valutazione della persistenza dell'edge.

**[NUOVO v5.1.1 — correzione di coerenza con Sezione 22]** I 2 anni di base **non coprono** gli eventi richiesti dallo stress test (marzo 2020, bear market 2022): con la data corrente, una finestra di 2 anni parte da settembre 2024. Per non rendere impossibile lo stress test dichiarato in Sezione 22, va caricato uno storico esteso (5-6 anni) **solo per un sottoinsieme ridotto di ticker rappresentativi** (es. 15-20 titoli, un mix di `LIQ_HIGH`/`LIQ_MEDIUM`/`LIQ_LOW` e settori diversi), non per l'intero universo — altrimenti lo spazio Supabase (limite 500 MB, free tier) va sotto pressione senza necessità reale, dato che lo stress test non richiede la copertura completa dei 150 titoli.

Questa distinzione (storico base a 2 anni su tutto l'universo, storico esteso a 5-6 anni su un sottoinsieme mirato) va decisa **prima** di STEP 11 (Sezione 25), non durante il backtest.

---

# 22. Backtest v5.1

Confermate tutte le metriche della v5.0 (rendimento lordo/netto, win rate, drawdown, Sharpe, numero operazioni, durata media, perdita/profitto medio, performance per tipologia/settore/mercato/score).

**[NUOVO v5.1] Aggiunte obbligatorie:**

- **Validazione fuori campione (walk-forward):** i pesi di contesto (Sezione 7) e la formula di ranking (Sezione 16) — inclusa la mappatura di confidenza (Sezione 11) — vanno calibrati su una finestra storica e validati su una finestra successiva mai vista, non sull'intero storico insieme. Altrimenti si rischia overfitting sui pesi, lo stesso problema — mascherato da più variabili — che si criticava nel vecchio RSI fisso.
- **Slippage differenziato per fascia di liquidità** (Sezione 12, valori di default specificati in v5.1.1) applicato nel backtest, non solo nel filtro live.
- **Performance per fascia di liquidità**, oltre a settore/mercato/score, per verificare se l'edge regge anche sui titoli meno liquidi o se va ristretto ai soli `LIQ_HIGH`.
- **Stress test su periodi di crisi nota** (marzo 2020, 2022 bear market), **eseguito sul sottoinsieme di ticker con storico esteso (Sezione 21)**, per verificare come si comporta il sistema quando molte anomalie appaiono simultaneamente e correlate — condizione in cui il controllo di Sezione 15 diventa più rilevante.
- **Analisi dei falsi positivi scartati come "deterioramento strutturale"** (Sezione 8.4): verificare quante volte lo scarto manuale di B avrebbe potuto essere anticipato da H2, per migliorare lo score nel tempo.

---

# 23. Capitale iniziale ridotto

Confermato l'impianto v5.0 (capitale ~1.000 €, evitare turnover inutile, dimensionamento esplicito — ora formalizzato in Sezione 13, rischio di portafoglio — ora esplicito in Sezione 15).

Obiettivo confermato: **dimostrare un edge statistico reale e ripetibile preservando il capitale**, non generare reddito immediato.

---

# 24. Cosa NON cambia nella v5.1

Restano validi tutti i punti della Sezione 21 della v5.0 (Supabase, GitHub Actions, moduli A/B/E/F/H, pipeline Fast/Slow, filtro costi, storico e backtest, dashboard). Le modifiche della v5.1 sono correzioni logiche e aggiunte mirate, non una riscrittura architetturale.

---

# 25. Ordine di implementazione aggiornato

### STEP 1
`src/universe.py` + tag di fascia di liquidità (Sezione 3.1). **— già caricato.**

### STEP 2
Verifica/migrazione `prezzi.interval` + campi di qualità dato (Sezione 4.2).

### STEP 3
Aggiornamento Modulo A: `UNIVERSE_FULL` + `interval='15m'` + propagazione flag qualità dato.

### STEP 4
Creazione tabella `screening_candidates` con i campi aggiuntivi della Sezione 9.

### STEP 5
Riscrittura Modulo H: H1 (in "fast", pre-filtro qualità dato) + H2 (in "slow", anomaly score + sotto-score di contesto versionato + news livello 1 via RSS — vedi Sezione 19bis per il budget).

### STEP 6
Aggiornamento Modulo B: lettura candidati, news livello 2, calendario eventi, verdetto con livello di confidenza (mappato a moltiplicatore, Sezione 11), condizione di invalidazione esplicita.

### STEP 7
Aggiornamento Modulo E: slippage per fascia di liquidità (valori di default Sezione 12), **sostituzione integrale** della formula di position sizing (Sezione 13).

### STEP 8
Nuovo controllo di rischio di portafoglio (Sezione 15), applicato prima del ranking.

### STEP 9
Ranking finale con formula versionata (`scoring_weights_v1.json` include sia i pesi di contesto sia la mappatura di confidenza, Sezione 7/11).

### STEP 10
Popolamento automatico dei settori.

### STEP 11
Caricamento storico: 2 anni su tutto l'universo + storico esteso (5-6 anni) sul sottoinsieme per stress test (Sezione 21).

### STEP 12
Backtest con validazione walk-forward, slippage per fascia, stress test su periodi di crisi (sul sottoinsieme con storico esteso).

---

# 26. Criterio di successo della v5.1

Non basta che il codice funzioni e che il backtest sull'intero storico sia positivo. Il criterio di successo richiede:

```text
ANOMALIA (dato pulito)
   ↓
OPPORTUNITÀ (contesto coerente, confidenza alta)
   ↓
RISULTATO POSITIVO SU DATI FUORI CAMPIONE (walk-forward)
   ↓
DOPO COSTI, SLIPPAGE REALISTICO PER LIQUIDITÀ E RISCHIO DI PORTAFOGLIO
   ↓
CONFERMATO IN PAPER TRADING
```

Solo a quel punto ha senso aumentare capitale, frequenza, universo o costo dell'infrastruttura.

---

# 27. Visione finale

Confermata la visione v5.0: un **radar intelligente di dislocazioni finanziarie**, non un terminale di prezzi. La v5.1 aggiunge il principio che mancava:

```text
GUARDA MOLTO
      ↓
SCARTA IL DATO SPORCO
      ↓
SELEZIONA POCO
      ↓
ANALIZZA BENE IL CONTESTO (pesi tracciati, non a sensazione)
      ↓
CONTROLLA IL RISCHIO DI PORTAFOGLIO, NON SOLO DELLA SINGOLA POSIZIONE
      ↓
RISCHIA POCO
      ↓
MISURA TUTTO FUORI CAMPIONE
      ↓
SCALA SOLO SE I DATI LO DIMOSTRANO
```

---

# 28. Alert per lo sviluppo futuro [NUOVO v5.1.1]

Punti non ancora chiusi del tutto, o che vanno sorvegliati attivamente durante l'implementazione (STEP 1-12), perché la spec da sola non li risolve — serve la verifica sul sistema reale.

**1. Affidabilità del feed RSS (Sezione 7, 17).** Google News RSS non ha un SLA garantito ed è stato in passato soggetto a cambi di formato senza preavviso. A differenza di NewsAPI (con cui il progetto ha già esperienza diretta di gestione limiti/cache, v3.1), qui manca ancora un ciclo di uso reale. Da monitorare nelle prime settimane: se il feed si rivela instabile, il fallback naturale è NewsAPI con una quota dedicata separata da quella già usata dal Modulo B esistente, non la condivisione dello stesso budget di 100 richieste/giorno.

**2. Modello di correlazione "approssimato" (Sezione 15).** La spec dichiara esplicitamente che una stima per settore/mercato è sufficiente "in questa fase". È una scelta corretta per non appesantire il sistema, ma va rivalutata dopo il primo ciclo di backtest walk-forward: se lo stress test (Sezione 22) mostra che candidati di settori diversi si muovono comunque insieme in scenari di crisi (correlazione di mercato generale, non solo settoriale), il controllo di Sezione 15 andrà esteso con un fattore di correlazione di mercato aggregato, non solo settoriale.

**3. Durata reale del job "slow" dopo l'aggiunta di H2/RSS (Sezione 19bis).** Questa è la stima meno solida dell'intero documento perché dipende da latenza di rete, non da tempi di installazione pacchetti (l'unica variabile misurata con precisione nelle revisioni precedenti). Va trattata come provvisoria finché non misurata: se il job "slow" supera il `timeout-minutes` configurato nel workflow YAML esistente, va alzato esplicitamente, non lasciato fallire silenziosamente a metà.

**4. Calibrazione dei placeholder numerici.** Tre famiglie di valori in questo documento sono dichiarate esplicitamente come punto di partenza, non come valori finali: slippage per fascia (Sezione 12), mappatura confidenza→moltiplicatore (Sezione 11), soglie di liquidità minima per l'idoneità in watchlist (Sezione 3.1). Il rischio concreto è che, sotto la pressione di voler passare al paper trading, questi restino "provvisori per sempre" senza mai passare dalla validazione walk-forward dichiarata obbligatoria in Sezione 22. Va trattato come un blocco esplicito: **niente paper trading (Fase 7, da SAPTA_v3.md/v4.md) finché questi tre gruppi di parametri non hanno superato almeno un ciclo di validazione fuori campione.**

**5. Spazio Supabase con lo storico esteso (Sezione 21).** Il free tier resta a 500 MB. Lo storico esteso a 5-6 anni, anche limitato a 15-20 ticker, va verificato in termini di spazio occupato prima di caricarlo, non dopo — coerente con l'attenzione già presente nel progetto verso il pruning dei dati intraday (v3.1).

**6. Interazione con i moduli G/PDT/bracket order già specificati in v3.2/v4.** Questo documento (v5.1.1) non tocca il Modulo G, ma il nuovo output del ranking (Sezione 16) cambia la natura di ciò che arriva a valle: non più un segnale BUY/SELL secco, ma un'opportunità con score, confidenza e condizione di invalidazione esplicita (Sezione 14). Prima di STEP 7/8, va deciso — anche solo in una nota, non necessariamente in questa revisione — come il Modulo G dovrà interpretare questo output arricchito (es. la condizione di invalidazione di Sezione 14 diventa lo stop-loss dell'ordine bracket già obbligatorio da v3.2?). Non bloccante per STEP 1-6, ma da chiarire prima di STEP 7.

---

**SAPTA v5.1.1 — specifica evolutiva corretta, coerente e con alert di sviluppo.**
