# SAPTA — Verifica stato progetto

**Data:** 14 settembre 2026  
**Repository:** `AlexPj72/SAPTA`  
**Branch:** `main`

## Sintesi esecutiva

SAPTA ha una base backend funzionante e i dati di mercato stanno arrivando in Supabase, ma il progetto non è ancora completo rispetto all'obiettivo v5.1.1.

Il problema principale emerso dalla verifica è doppio:

1. **Backend/dati:** l'ingestion Fast sta riprendendo a funzionare correttamente dopo la correzione del workflow. I dati 15m vengono inseriti in `prezzi`.
2. **Frontend/web:** la dashboard pubblica attuale non rappresenta ancora il sistema SAPTA completo. Nel repository GitHub non risultano file PHP; quindi il sito `pujia.it/sapta/` è una parte separata/parziale rispetto al repository SAPTA.

---

## 1. Workflow Fast

File: `.github/workflows/sapta_fast.yml`

Cron attuale:

```yaml
on:
  schedule:
    - cron: '*/15 9-17 * * 1-5'
  workflow_dispatch:
```

Il workflow esegue:

- Module A — ingestion 15m
- Module H / H1 — anomaly screening
- cleanup condizionale

La verifica sui dati ha mostrato una ripresa dell'ingestion dopo la correzione del workflow.

Esempio dei blocchi 15m verificati:

- `2026-09-14 11:15 UTC` → 35 ticker
- `2026-09-14 12:45 UTC` → 35 ticker
- `2026-09-14 12:30 UTC` → 1 ticker

Il buco tra le 12:00 e le 12:15 UTC coincide con il periodo in cui il workflow era in correzione manuale e non va quindi interpretato come un nuovo problema di ingestion.

**Conclusione:** il flusso Fast è tornato operativo; va comunque continuato il monitoraggio dei prossimi cicli.

---

## 2. Database Supabase

### `prezzi`

Verifica precedente:

- circa 91.868 righe
- dati giornalieri dal 2019
- dati 15m presenti e in aggiornamento

Distribuzione verificata:

- `1d`: circa 91.344 righe
- `15m`: dati recenti in aggiornamento

### Tabelle operative

| Tabella | Stato verificato |
|---|---|
| `prezzi` | popolata |
| `signals_raw` | 42 righe |
| `signals_filtered` | 42 righe |
| `screening_candidates` | 0 righe |
| `ai_agent_decisions` | 0 righe |
| `ticker_sectors` | 136 ticker |
| `capital_state` | presente |

Il fatto che `screening_candidates` sia ancora vuota è importante: il funnel H1/H2 non sta ancora alimentando la parte AI/trading come previsto.

---

## 3. Module A — Ingestion

`src/modulo_a_ingestion.py`

Implementato:

- universo ticker
- dati 15m
- yfinance
- cross-check Finnhub per USA
- controllo qualità dati
- stato `ok`, `stale`, `zero_volume`
- upsert su `prezzi`

L'universo attuale contiene circa 136 ticker.

---

## 4. Module H — Screening anomalie

`src/modulo_h_anomaly.py`

H1 e H2 risultano implementati a livello di codice.

### H1

Analizza gli ultimi dati 15m e cerca anomalie di:

- volume
- variazione prezzo
- qualità dati

I candidati dovrebbero essere scritti in `screening_candidates`.

### H2

Aggiunge contesto tramite:

- news
- GDELT
- SMA50
- SMA200
- distanza dai massimi/minimi

Il flusso H2 dovrebbe promuovere i candidati verso Module B.

**Problema attuale:** la tabella `screening_candidates` risulta ancora vuota nel database verificato. Occorre quindi verificare l'esecuzione reale di H1/H2 e i log del workflow, non solo la presenza del codice.

---

## 5. Module B — Analysis

`src/modulo_b_analysis.py`

Risulta implementata la parte relativa a:

- analisi
- segnali
- earnings
- confidence
- invalidation price
- target price

I segnali esistono già in `signals_raw` e vengono trasferiti in `signals_filtered`.

---

## 6. Module E — Cost Filter

`src/modulo_e_cost_filter.py`

Implementato:

- settore da `ticker_sectors`
- liquidità
- slippage
- position sizing
- capitale da `capital_state`
- filtri sui segnali
- output `signals_filtered`

---

## 7. Backtest

`src/modulo_f_backtest.py`

È ancora una versione semplice basata su RSI 30/70.

Non rappresenta ancora il backtest completo previsto dalla roadmap v5.1.1.

Mancano in particolare:

- strategia completa SAPTA
- walk-forward
- stress test completo
- confronto sistematico delle versioni
- metriche operative complete

---

## 8. AI Trading

La tabella `ai_agent_decisions` risulta vuota.

Il Module I previsto dalla roadmap non è ancora operativo come terzo canale di decisione.

Quindi **non è ancora possibile mostrare sulla dashboard un'AI che sta realmente facendo trading**, perché non esistono ancora decisioni AI persistite da visualizzare.

La struttura prevista dovrà distinguere almeno:

- decisione SAPTA
- decisione AI
- confidence
- motivazione
- timestamp
- ticker
- prezzo di riferimento
- BUY / SELL / HOLD

---

## 9. Paper Trading

La parte paper trading completa non risulta ancora presente come sistema operativo integrato.

Per il periodo di prova di 2–3 mesi dovrà essere predisposto almeno:

- capitale iniziale
- portafoglio SAPTA
- portafoglio AI
- portafoglio manuale utente
- ordini virtuali
- posizioni aperte
- storico operazioni
- P&L realizzato/non realizzato
- equity curve
- drawdown
- commissioni e slippage
- confronto SAPTA vs AI vs manuale

Il paper trading deve usare i prezzi reali acquisiti da SAPTA, senza effettuare ordini reali sul mercato.

---

## 10. Dashboard / sito web

La dashboard attuale non è ancora il frontend completo previsto dal progetto.

È stata verificata l'assenza di file `.php` nel repository GitHub `AlexPj72/SAPTA` tramite ricerca del codice.

Quindi il sito pubblico `https://www.pujia.it/sapta/index.php` deve essere considerato una frontend separata/parziale rispetto al repository backend SAPTA.

### Struttura web necessaria

La versione completa dovrebbe avere almeno:

1. **Dashboard principale**
   - stato sistema
   - mercato
   - ultimi segnali
   - performance
   - alert

2. **Tutti i titoli**
   - elenco completo universo
   - prezzo attuale
   - variazione giornaliera
   - variazione 15m
   - volume
   - segnale
   - confidence
   - stato analisi

3. **Scheda titolo**
   - grafico prezzo
   - storico
   - indicatori
   - segnali
   - target
   - invalidation
   - news/context

4. **Storico**
   - pagina separata
   - dati storici
   - segnali storici
   - performance storiche

5. **Segnali SAPTA**
   - segnali raw
   - segnali filtrati
   - ranking

6. **AI Trading**
   - decisioni AI
   - BUY/SELL/HOLD
   - confidence
   - motivazione
   - performance AI

7. **Paper Trading**
   - portafoglio virtuale
   - ordini
   - posizioni
   - capitale
   - P&L
   - equity curve
   - confronto AI/SAPTA/manuale

8. **Backtest**
   - risultati
   - metriche
   - drawdown
   - confronti

9. **Performance**
   - rendimento
   - win rate
   - profit factor
   - drawdown
   - benchmark

10. **Monitoraggio sistema**
    - ultimo ciclo Fast
    - ultimo ciclo Slow
    - qualità dati
    - ticker acquisiti
    - errori

---

## 11. Priorità operative

### Priorità 1 — Stabilizzare pipeline dati

Continuare a verificare i cicli Fast e Slow e verificare che H1/H2 producano realmente candidati.

### Priorità 2 — Sbloccare screening

Capire perché `screening_candidates` è ancora vuota nonostante il codice H1/H2 sia presente.

### Priorità 3 — Implementare Module I

Attivare il canale AI con decisioni persistite in `ai_agent_decisions`.

### Priorità 4 — Implementare paper trading

Creare il motore virtuale per il test di 2–3 mesi.

### Priorità 5 — Costruire il frontend completo

Collegare il sito alla base Supabase e creare tutte le sezioni sopra indicate.

### Priorità 6 — Backtest/walk-forward

Completare il motore di validazione della strategia v5.1.1.

---

## 12. Giudizio finale

**SAPTA non è rotto: è una base backend in evoluzione, ma non è ancora il prodotto completo che era stato progettato.**

La parte ingestion sta funzionando e il database contiene uno storico consistente. Il punto debole attuale è il passaggio da dati → screening → AI → paper trading → dashboard.

In particolare:

- dati storici: **OK**
- ingestion 15m: **operativa, da monitorare**
- Module A: **implementato**
- H1/H2: **codice presente, esecuzione da verificare**
- Module B: **implementato**
- Module E: **implementato**
- backtest completo: **NO**
- Module I AI: **NO**
- decisioni AI: **0**
- paper trading completo: **NO**
- dashboard completa: **NO**
- frontend PHP nel repository SAPTA: **NO**

### Nessuna modifica effettuata durante questa verifica

Questa verifica è stata diagnostica. Non sono stati modificati workflow, database o codice SAPTA.
