# SAPTA — Backtest indicatori tecnici aggiuntivi: prima passata (24/09/2026)

Eseguito su richiesta esplicita dell'utente (protocollo dettagliato fornito in
chat il 24/09), query in `scripts/backtest_indicatori.sql`, dati reali da
Supabase (nessuna soglia della pipeline operativa toccata).

## Limite strutturale, da leggere prima dei numeri

`screening_candidates` (la definizione attuale di "anomalia SAPTA", H1/H2)
esiste solo dal **18/09/2026** — 6 giorni di calendario, 234 eventi, 88
ticker. Conseguenza diretta:

- **+1d, +3d**: calcolabili, N modesto.
- **+5d**: N=0 per la quasi totalità degli eventi (i più vecchi hanno appena
  raggiunto 5 giorni di borsa).
- **+10d, +20d**: **DATA_UNAVAILABLE, N=0 su tutta la linea** — non è un
  limite tecnico, è impossibile che esistano oggi eventi con 10-20 giorni di
  borsa già trascorsi da un pool nato 6 giorni fa.

Inoltre, tutti gli eventi vengono da **4-6 giornate di mercato consecutive**:
le osservazioni non sono indipendenti (un giorno di mercato generale forte o
debole si riflette su tutti i sottogruppi insieme). Per questo la
classificazione qui sotto è quasi ovunque **DA VERIFICARE**, mai
INFORMATIVO — coerente con la Sezione 12 del protocollo (non considerare
significativo un risultato da pochi casi/poco tempo).

## Indicatori implementati in questa prima passata

MA (SMA20/50/200, solo trend sopra/sotto), RSI14, ATR14/ATR%, Bollinger
(posizione nella banda), ROC5, volatilità storica 20d (calcolata, non ancora
usata per raggruppare).

**Non ancora implementati** (rimandati, vedi `chatgpt_implementazione.md`
sessione 24/09): MACD (serve EMA ricorsiva), ADX (serve smoothing +DM/-DM a
più stadi), Relative Strength vs indice/settore, Gap, Supporti/resistenze,
combinazioni a 2-3 indicatori.

## Risultati (baseline + singoli indicatori, +1d e +3d)

| Gruppo | Condizione | N | Media +1d | %pos +1d | N +3d | Media +3d | %pos +3d | Classificazione |
|---|---|--:|--:|--:|--:|--:|--:|---|
| Baseline | tutte le anomalie | 172 | 0.00% | 48.8% | 66 | +0.79% | 47.0% | riferimento |
| RSI14 | <30 | 39 | -0.61% | 53.8% | 12 | -1.14% | 25.0% | DA VERIFICARE |
| RSI14 | 30-50 | 65 | -0.17% | 40.0% | 20 | +0.14% | 40.0% | DA VERIFICARE |
| RSI14 | 50-70 | 51 | +0.12% | 52.9% | 26 | +0.91% | 46.2% | DA VERIFICARE |
| RSI14 | >70 | 17 | +1.68% | 58.8% | 8 | +4.92% | 100.0% | DA VERIFICARE (N troppo piccolo, specie +3d) |
| Trend SMA20 | sopra | 83 | +0.31% | 53.0% | 40 | +1.42% | 55.0% | DA VERIFICARE |
| Trend SMA20 | sotto | 89 | -0.29% | 44.9% | 26 | -0.18% | 34.6% | DA VERIFICARE |
| Trend SMA50 | sopra | 90 | +0.43% | 52.2% | 38 | +1.84% | 57.9% | DA VERIFICARE |
| Trend SMA50 | sotto | 82 | -0.47% | 45.1% | 28 | -0.63% | 32.1% | DA VERIFICARE |
| Trend SMA200 | sopra | 116 | +0.22% | 51.7% | 48 | +1.26% | 52.1% | DA VERIFICARE |
| Trend SMA200 | sotto | 56 | -0.45% | 42.9% | 18 | -0.46% | 33.3% | DA VERIFICARE |
| Bollinger | vicino banda bassa | 54 | -0.60% | 42.6% | 17 | -1.00% | 23.5% | DA VERIFICARE |
| Bollinger | vicino banda alta | 35 | +0.75% | 51.4% | 16 | +2.28% | 62.5% | DA VERIFICARE |
| Bollinger | centrale | 83 | +0.07% | 51.8% | 33 | +0.99% | 51.5% | DA VERIFICARE |
| ROC5 | positivo | 99 | +0.35% | 51.5% | 46 | +1.52% | 56.5% | DA VERIFICARE |
| ROC5 | negativo | 73 | -0.48% | 45.2% | 20 | -0.90% | 25.0% | DA VERIFICARE |
| +5d / +10d / +20d | tutti i gruppi | 0 | — | — | — | — | — | **DATA_UNAVAILABLE** |

## Osservazione qualitativa (non una conclusione)

Direzione coerente con un'intuizione da manuale (segue-trend, non
mean-reversion): stare sopra le medie mobili va meglio che stare sotto in
questo campione; RSI alto (>70) non ha mostrato inversione nei dati
raccolti finora; vicino alla banda di Bollinger bassa il rendimento
successivo è stato peggiore, non migliore. Nessuno di questi è ancora
INFORMATIVO per i motivi sopra (N e finestra di mercato) — vanno ri-letti
quando la finestra si allarga.

## Prossimo passo

Ri-eseguire `scripts/backtest_indicatori.sql` tra 2-3 settimane (per +10d
utilizzabile) e tra 5-6 settimane (per +20d). Nel frattempo, se richiesto,
implementare MACD/ADX/Relative Strength/Gap/combinazioni. Nessuna modifica
alla pipeline operativa finché il backtest non è concluso, come da vincolo
esplicito del protocollo (Sezione 16).
