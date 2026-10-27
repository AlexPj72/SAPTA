# SAPTA intraday momentum scan — read-only findings (2026-10-27)

## Scope and safety
Read-only SQL against existing `public.prezzi` 15-minute bars, window 2026-10-13 00:00 UTC through 2026-10-27 00:00 UTC. No production code, live alerts, database rows, or portfolios changed. These are close/high-based diagnostics, not simulated fills; costs and slippage are excluded.

## Rule comparison
Rules were tested against the same available 15m history. Volume ratio in this SQL comparison uses average prior non-zero volume over up to 20 prior bars; this differs from the Python backtest's prior-volume median and is therefore an approximation.

| Rule | Signals | Tickers | Mean close after 1h | Positive close after 1h | Reached +2% intrahour high | Fell to -1.5% or worse at a future close |
|---|---:|---:|---:|---:|---:|---:|
| A: momentum >=2%, breakout, current volume >=1.5x average | 71 | 53 | -0.108% | 50.7% | 5.6% | 14.1% |
| B: momentum >=2%, breakout, no volume filter | 296 | 93 | +0.013% | 50.3% | 5.1% | 7.8% |
| C: momentum >=1%, breakout, no volume filter | 777 | 124 | +0.032% | 50.5% | 4.4% | 5.3% |
| D: momentum >=1.5%, close within 0.3% of/beyond prior 8-bar high, volume burst >=1.5x in current or previous 3 bars | 376 | 101 | +0.094% | 52.9% | 5.6% | 5.9% |
| E: same as D without recent volume-burst condition | 574 | 108 | +0.065% | 51.6% | 4.2% | 4.9% |

## What happened on 23 October
The strict rule requiring volume expansion on the same bar missed several useful early signals because the volume burst occurred on the opening bar and the price-momentum condition matured on a later bar.

- CRWD, 13:30 UTC: 4-bar momentum +1.82%, above prior 8-bar high by 1.19%, volume 3.59x prior average. Next-hour close +2.46%. The >=2% momentum rule missed this first bar.
- CRWD, 14:00 UTC: momentum +2.60%, above prior high by 1.03%, current volume only 1.19x average. Next-hour close +2.94%. A same-bar >=1.5x volume filter would reject it.
- PANW, 14:15 UTC: momentum +3.77%, above prior high by 1.83%, current volume 0.09x average, but an opening volume burst was present within the recent 4-bar window. Next-hour close +2.09%.
- SLB, 13:45 UTC: momentum +2.27%, close only 0.30% below the previous 8-bar high, while the opening bar had volume 3.25x average. Next-hour close +2.89%. A strict breakout threshold and same-bar volume requirement both miss it.

The recent-volume-burst rule D flags all four of the above useful 23 October observations, but it also produces many other signals; the aggregate mean next-hour close return is only +0.094% gross. It is a better candidate for further testing, not an actionable buy rule.

## Data-quality caveats
- The available 15m history is short and incomplete for some symbols.
- Many bars have zero volume, while the 19:45 UTC bar often carries a very large volume spike, consistent with a closing-auction/time-of-day effect. A single rolling volume baseline is therefore unreliable.
- Signals overlap; the outcomes use later closes/highs and do not model executable entries, stops, spread, commissions, or gaps.
- No claim of statistically significant predictive edge is supported by this sample.

## Next test
Before changing SAPTA's live BUY logic, test volume relative to the same time-of-day across previous sessions, separately flag opening gaps, enforce minimum data quality, and evaluate non-overlapping trades with stop/target and estimated existing SAPTA transaction costs. Keep the scanner in paper/test mode until it demonstrates a robust net edge on a longer sample.


## Second test: volume normalized by time of day (27 October)
I ran additional read-only SQL using the median volume for the same ticker and exact UTC 15-minute slot over the prior 10 calendar days. This is intended to reduce distortion from opening/closing bars. Results remain exploratory; some slots have few historical observations.

| Rule | Signals | Tickers | Mean close after 1h | Positive close after 1h | Future high +2% | Future low/close risk proxy |
|---|---:|---:|---:|---:|---:|---:|
| TOD-A: momentum >=1.5%, close within 0.3% of/beyond prior 8-bar high, same-slot volume >=1.5x median | 271 | 102 | +0.099% | 55.4% | 4.1% | 7.7% hit future low at least -1.5% |
| TOD-B: same momentum/near-breakout, no volume filter | 574 | 108 | +0.065% | 51.6% | 4.2% | 5.4% hit future low at least -1.5% |
| TOD-C: momentum >=2%, strict breakout, same-slot volume >=1.5x median | 149 | 74 | -0.016% | 53.7% | 4.0% | 12.1% hit future low at least -1.5% |

The same-time-of-day volume filter improves the share of positive one-hour closes versus TOD-B, but the absolute mean return remains small and the future +2% high rate is only 4.1%. The stricter +2% momentum/breakout rule remains unattractive.

## Third test: hypothetical stop/target sensitivity
For the 271 TOD-A candidate signals, I tested a one-hour horizon with first-touch stop/target logic on the next four 15m bars. If stop and target are both crossed within the same bar, the conservative assumption is that the stop is hit first. These are bar-based approximations, not real fills, and trades still overlap.

| Target | Stop | Target hits | Stop hits | Time exits | Mean gross return | Mean after hypothetical 0.20% round-trip cost |
|---:|---:|---:|---:|---:|---:|---:|
| +1.0% | -0.75% | 62 | 62 | 147 | +0.126% | -0.074% |
| +1.5% | -0.75% | 28 | 63 | 180 | +0.176% | -0.024% |
| +2.0% | -0.75% | 11 | 64 | 196 | +0.164% | -0.036% |
| +1.0% | -1.00% | 64 | 40 | 167 | +0.118% | -0.082% |
| +1.5% | -1.00% | 29 | 41 | 201 | +0.165% | -0.035% |
| +2.0% | -1.00% | 11 | 41 | 219 | +0.153% | -0.047% |
| +1.0% | -1.25% | 64 | 24 | 183 | +0.107% | -0.093% |
| +1.5% | -1.25% | 29 | 25 | 217 | +0.153% | -0.047% |
| +2.0% | -1.25% | 11 | 25 | 235 | +0.141% | -0.059% |

The 0.20% cost is a sensitivity assumption, not a verified cost quote for every ticker/broker. All nine combinations have negative mean returns after that assumed cost. This is not evidence for deploying the rule. A valid next stage must use verified per-market costs, avoid overlapping trades, and evaluate a longer history with time-of-day volume coverage.

## Explicit change boundary
All findings above were computed with read-only `SELECT` queries against existing bars. No INSERT/UPDATE/DELETE, schema changes, secrets changes, or production SAPTA code edits were made. Test assets remain isolated on `test/momentum-scanner-backtest`; nothing was merged to `main`.
