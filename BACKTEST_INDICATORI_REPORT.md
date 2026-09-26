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

**Implementati in Parte 2** (stesso giorno): MACD, ADX, Relative Strength
(proxy cross-sezionale, non indice reale), Gap, Supporti/resistenze 50gg,
2 combinazioni a 2 condizioni — vedi tabella sotto.

**Ancora non implementato**: Relative Strength vs un indice reale (servirebbe
scaricare ^GSPC/FTSEMIB e salvarli in `prezzi`, non fattibile dall'ambiente
di sviluppo per limiti di rete — andrebbe fatto da GitHub Actions), Relative
Strength vs settore (serve un indice/media per settore da `ticker_sectors`),
combinazioni a 3 condizioni, supporti/resistenze a 20/200gg (solo 50gg fatto).

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

## Parte 2 (stesso giorno, 24/09) — MACD, ADX, Relative Strength, Gap, Supporti/Resistenze, combinazioni

Query in `scripts/backtest_indicatori_parte2.sql`. MACD e ADX usano una
finestra storica più corta (125 giorni di borsa invece di 1 anno) perché il
calcolo richiede una CTE ricorsiva (EMA/Wilder smoothing) che su 88 ticker
a 1 anno va in timeout — vedi nota tecnica in testa allo script. Relative
Strength è un **proxy**: rendimento medio cross-sezionale del gruppo di
mercato (US vs IT, split per suffisso `.MI`), non un indice reale — in
Supabase non ci sono dati di indice (^GSPC, FTSEMIB) da usare come
benchmark.

| Gruppo | Condizione | N | Media +1d | %pos +1d | N +3d | Media +3d |
|---|---|--:|--:|--:|--:|--:|
| MACD | histogram positivo (sopra signal) | 73 | +0.42% | 58.9% | 33 | +1.59% |
| MACD | histogram negativo (sotto signal) | 99 | -0.31% | 41.4% | 33 | -0.01% |
| ADX | <20 (trend debole) | 63 | +0.34% | 50.8% | 25 | +1.95% |
| ADX | 20-40 | 109 | -0.20% | 47.7% | 41 | +0.08% |
| ADX | >40 (trend forte) | 0 | — | — | — | — |
| Relative Strength 5d | positiva (batte il mercato) | 98 | +0.38% | 52.0% | 46 | +1.52% |
| Relative Strength 5d | negativa (sotto il mercato) | 74 | -0.50% | 44.6% | 20 | -0.90% |
| Gap apertura | gap up (>0.5%) | 63 | -0.23% | 47.6% | 26 | +1.62% |
| Gap apertura | gap down (<-0.5%) | 31 | +0.09% | 51.6% | 8 | -0.05% |
| Gap apertura | nessun gap rilevante | 78 | +0.15% | 48.7% | 32 | +0.33% |
| Vicinanza max 50gg | vicino (entro 1%) | 13 | +0.19% | 46.2% | 4 | +1.60% |
| Vicinanza max 50gg | lontano | 159 | -0.02% | 49.1% | 62 | +0.74% |
| Vicinanza min 50gg | vicino (entro 1%) | 8 | -1.16% | 12.5% | 4 | -2.49% |
| Vicinanza min 50gg | lontano | 164 | +0.06% | 50.6% | 62 | +1.00% |
| Combo SMA20+RSI | sopra SMA20 + RSI>70 | 22 | +1.68% | 58.8% | 8 | +4.92% |
| Combo SMA20+RSI | sopra SMA20 + RSI 50-70 | 66 | +0.11% | 54.2% | 25 | +0.91% |
| Combo SMA20+RSI | sotto SMA20 + RSI<30 | 54 | -0.61% | 53.8% | 12 | -1.14% |
| Combo SMA20+RSI | sotto SMA20 + RSI 30-50 | 69 | -0.06% | 38.3% | 13 | +0.61% |
| Combo Bollinger+ROC5 | banda bassa + ROC5 neg | 80 | -0.60% | 42.6% | 17 | -1.00% |
| Combo Bollinger+ROC5 | banda alta + ROC5 pos | 45 | +0.75% | 51.4% | 16 | +2.28% |
| Combo Bollinger+ROC5 | centrale + ROC5 pos | 80 | +0.14% | 51.6% | 30 | +1.12% |

Tutto **DA VERIFICARE** per gli stessi motivi della Parte 1 (N piccolo dopo
lo split, eventi concentrati in poche giornate di mercato non indipendenti).
Il pattern più consistente sui due tagli (indicatore singolo e in
combinazione) resta "sopra SMA20 + RSI>70": +1.68%/+58.8% a +1d, +4.92%/+8
casi a +3d — ma N=17-22 è ancora un campione minuscolo, non una conclusione.
ADX>40 non ha N: nessun evento del campione ha mostrato un trend così forte
in questa finestra.

## Parte 3 (26/09) — Relative Strength con indice reale, combo a 3 condizioni, supporti/resistenze 200gg

Caricato lo storico giornaliero 2 anni di `^GSPC` e `FTSEMIB.MI` (prima
esistevano solo a 15m dal 18/09 — insufficiente per RS a 5gg) tramite
`src/load_historical_data.py --scope=indices` (nuovo scope, workflow
lanciato il 26/09, 501-506 barre scritte per indice). Query in
`scripts/backtest_indicatori_parte3.sql`.

| Gruppo | Condizione | N | N+1d | Media+1d | %pos+1d | N+3d | Media+3d |
|---|---|--:|--:|--:|--:|--:|--:|
| RS5 vs indice REALE | positiva (batte S&P500/FTSEMIB) | 129 | 90 | +0.32% | 51.1% | 45 | +1.36% |
| RS5 vs indice REALE | negativa (sotto S&P500/FTSEMIB) | 141 | 86 | -0.39% | 46.5% | 25 | -0.72% |
| Combo 3: SMA20+RSI+RS5 | sopra SMA20 + RSI≥50 + RS5+ | 97 | 65 | +0.50% | 55.4% | 33 | +1.87% |
| Combo 3: SMA20+RSI+RS5 | sotto SMA20 + RSI<50 + RS5- | 120 | 74 | -0.43% | 47.3% | 19 | -1.04% |
| Combo 3: SMA20+RSI+RS5 | sotto SMA20 + RSI<50 + RS5+ | 18 | 13 | +0.42% | 38.5% | 9 | +0.84% |
| Combo 3: SMA20+RSI+RS5 | altre combinazioni | ≤13 ciascuna | — | — | — | — | — |
| Vicinanza max/min 200gg | zona intermedia | 256 | 170 | -0.04% | 48.8% | 67 | +0.55% |
| Vicinanza max/min 200gg | vicino massimo 200gg | 7 | 4 | +1.38% | 75.0% | 2 | +3.19% |
| Vicinanza max/min 200gg | vicino minimo 200gg | 7 | 2 | -0.97% | 0.0% | 1 | +0.33% |

La RS reale conferma la stessa direzione del proxy usato in Parte 2 (RS
positiva → rendimento successivo migliore). Il combo "sopra SMA20 + RSI≥50
+ RS5 positiva" è il pattern con il miglior compromesso N/effetto visto
finora in tutto il backtest (N=65-97, non solo 15-20 come gli altri) — resta
comunque **DA VERIFICARE**, non INFORMATIVO, per la stessa finestra di
mercato corta (6-7 giornate) che vale per tutto il resto di questo report.
Vicinanza a massimo/minimo 200gg: N troppo piccolo (7 casi) per dire
qualcosa.

## Osservazione qualitativa (non una conclusione)

Direzione coerente con un'intuizione da manuale (segue-trend, non
mean-reversion): stare sopra le medie mobili va meglio che stare sotto in
questo campione; RSI alto (>70) non ha mostrato inversione nei dati
raccolti finora; vicino alla banda di Bollinger bassa il rendimento
successivo è stato peggiore, non migliore. Nessuno di questi è ancora
INFORMATIVO per i motivi sopra (N e finestra di mercato) — vanno ri-letti
quando la finestra si allarga.

## Prossimo passo

Ri-eseguire `scripts/backtest_indicatori.sql` + `_parte2.sql` + `_parte3.sql`
tra 2-3 settimane (per +10d utilizzabile) e tra 5-6 settimane (per +20d) —
avanzando le date hardcoded negli script alla finestra corrente. Storico
indici (`^GSPC`, `FTSEMIB.MI`) va ricaricato periodicamente con
`load_historical_data.py --scope=indices` se si vuole tenerlo aggiornato
oltre i 2 anni iniziali. Nessuna modifica alla pipeline operativa finché
il backtest non è concluso, come da vincolo esplicito del protocollo
(Sezione 16).
