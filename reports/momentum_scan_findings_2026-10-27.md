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
