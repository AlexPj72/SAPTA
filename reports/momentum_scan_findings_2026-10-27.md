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


## Fourth test: threshold sensitivity with data-quality filtering (27 October, SQL SELECT)

This pass uses only bars flagged `ok` (or NULL) and requires a positive volume plus a same-ticker, same-UTC-slot 10-day median volume baseline. The candidate outcomes require four future 15m bars. It is therefore a stricter sample than the earlier exploratory TOD table and cannot be compared 1:1 with it.

| Rule | Signals | Tickers | Mean close after 1h | Median close after 1h | Positive close | Future high >= +2% | Future low <= -1.5% |
|---|---:|---:|---:|---:|---:|---:|---:|
| Momentum >=1.0%, volume >=1.0x, near breakout | 612 | 115 | +0.063% | +0.074% | 53.8% | 4.1% | 6.0% |
| Momentum >=1.0%, volume >=1.5x, near breakout | 423 | 112 | +0.082% | +0.091% | 55.1% | 4.0% | 6.6% |
| Momentum >=1.5%, volume >=1.0x, near breakout | 370 | 105 | +0.084% | +0.128% | 53.8% | 4.1% | 6.8% |
| Momentum >=1.5%, volume >=1.5x, near breakout (TOD-A) | 271 | 102 | +0.099% | +0.153% | 55.4% | 4.1% | 7.7% |
| Momentum >=1.5%, volume >=2.0x, near breakout | 200 | 84 | +0.053% | +0.143% | 54.5% | 2.5% | 8.5% |
| Momentum >=2.0%, volume >=1.0x, near breakout | 248 | 90 | +0.048% | +0.087% | 52.8% | 4.8% | 8.9% |
| Momentum >=2.0%, volume >=1.5x, near breakout | 183 | 80 | +0.076% | +0.134% | 55.2% | 4.9% | 9.8% |
| Momentum >=2.0%, volume >=2.0x, near breakout | 138 | 68 | +0.026% | +0.118% | 54.3% | 2.2% | 10.9% |
| Momentum >=1.5%, volume >=1.5x, strict breakout | 222 | 95 | +0.044% | +0.128% | 54.5% | 3.6% | 9.0% |

Near breakout means close is no more than 0.3% below the previous 8-bar high or above it. Even the best gross mean (+0.099% after one hour) is below the configured round-trip cost floor for USA high-liquidity shares (+0.20%, see cost test below), before taxes or adverse execution.

## Fifth test: regime concentration and gap classification

The TOD-A result is highly dependent on a few dates:

| Sample | Signals | Mean close after 1h | Median close after 1h | Positive close | Future high >= +2% | Future low <= -1.5% |
|---|---:|---:|---:|---:|---:|---:|
| All TOD-A signals | 271 | +0.099% | +0.153% | 55.4% | 4.1% | 7.7% |
| Excluding 23 October | 247 | +0.007% | +0.107% | 52.6% | 1.6% | 8.5% |
| Excluding both 19 and 23 October | 234 | -0.037% | +0.050% | 50.9% | 1.7% | 9.0% |

The apparent positive average is not stable across dates. The strong 23 October session materially lifts the aggregate; removing it reduces the mean to almost zero. This is a major overfitting/regime-dependence warning.

A separate gap check distinguished an opening/session gap (more than 30 minutes since the prior bar) from an intraday gap (30 minutes or less):

| TOD-A subset | Signals | Mean close after 1h | Positive close | Future high >= +2% | Future low <= -1.5% |
|---|---:|---:|---:|---:|---:|
| Opening/session gap >1% | 24 | -0.463% | 58.3% | 4.2% | 20.8% |
| Intraday gap >1% | 37 | +0.249% | 54.1% | 13.5% | 10.8% |
| No absolute gap >1% | 210 | +0.136% | 55.2% | 2.4% | 5.7% |

The opening-gap subset has a materially worse average and more downside tails. The intraday-gap subset is more promising on gross high excursion, but it has only 37 observations, overlapping signals and no evidence yet of a robust net edge. It is not approved for deployment.

## Sixth test: market split and non-overlapping signals

With data-quality filtering, four complete future bars and the same TOD-A rule, the market split was:

| Market | Signals | Tickers | Mean close after 1h | Median close after 1h | Positive close | Future high >= +2% | Future low <= -1.5% |
|---|---:|---:|---:|---:|---:|---:|---:|
| Italy (.MI) | 43 | 15 | +0.196% | +0.340% | 58.1% | 0.0% | 4.7% |
| USA/other non-.MI | 228 | 87 | +0.080% | +0.128% | 54.8% | 4.8% | 8.3% |

The Italian subset is small and generated no +2% future highs in this sample. The US/other subset has higher tail upside but a negative result after configured round-trip costs below.

Using a conservative non-overlap screen (reject a signal if another signal for the same ticker occurred in the previous hour), the 129 complete, data-quality-filtered trades fell to 94. Their average close return was -0.139%, median -0.020%, positive closes 48.9%, future high >= +2% 3.2%, and future low <= -1.5% 10.6%. A conservative first-touch +1.0% target / -0.75% stop proxy had mean gross return +0.038%; subtracting round-trip cost sensitivities gives:
- cost 0.10%: -0.062%;
- cost 0.15%: -0.112%;
- cost 0.20%: -0.162%;
- cost 0.30%: -0.262%.

The non-overlap screen is conservative rather than a full portfolio scheduler: it rejects signals based on any earlier signal in the preceding hour, even if that earlier signal would itself have been rejected. This avoids overstating trade count, but a final portfolio-level simulation would need a true sequential execution ledger.

## Seventh test: configured SAPTA costs applied to simulated trades

I read the active `public.costi_operazione` rows (SELECT only) and the cost calculation in `src/modulo_e_cost_filter.py` on `main`; neither was changed. The database currently configures:

- **Alpaca / USA:** variable commission 0%; spread assumption 0.05%; fixed commission €0; plus per-side slippage assumption by liquidity: 0.05% high, 0.15% medium, 0.40% low.
- **Interactive Brokers / EU:** fixed commission €1 per operation; variable commission 0.05%; spread assumption 0.10%; plus the same per-side slippage tiers.
- Both rows use a 26% capital-gains tax reserve, applied by SAPTA only when expected net return is positive.

These are the values currently configured in SAPTA, **not independently verified broker quotes**. For a round trip (entry + exit), before tax, they imply approximately:

| Market / liquidity | €160 position | €260 position |
|---|---:|---:|
| USA high | 0.20% | 0.20% |
| USA medium | 0.40% | 0.40% |
| USA low / unknown | 0.90% | 0.90% |
| EU high | 1.65% | 1.17% |
| EU medium | 1.85% | 1.37% |
| EU low / unknown | 2.35% | 1.87% |

The EU estimates include €1 fixed fee on both entry and exit, plus variable commission, spread and slippage on both sides. They are sensitive to actual order size and fill conditions.

I then applied those configured costs to the data-quality-filtered TOD-A trades with a 1-hour first-touch proxy (target +1.0%, stop -0.75%; stop assumed first if both are crossed in the same 15m bar). The subset with complete outcomes contained 126 USA signals and only 3 EU signals with known high-liquidity metadata:

| Market | Position notional used | Signals | Mean gross simulated return | Mean round-trip cost | Mean net before tax |
|---|---:|---:|---:|---:|---:|
| USA high-liquidity metadata | €160 | 126 | +0.089% | 0.200% | -0.111% |
| USA high-liquidity metadata | €260 | 126 | +0.089% | 0.200% | -0.111% |
| EU high-liquidity metadata | €160 | 3 | -0.419% | 1.650% | -2.069% |
| EU high-liquidity metadata | €260 | 3 | -0.419% | 1.169% | -1.588% |

The EU sample is far too small for inference, but the configured fixed fee makes small positions structurally expensive. For USA, the average gross simulated result is less than half the configured round-trip cost floor. The strategy therefore fails the cost test even under the high-liquidity assumption, before tax. Medium/low liquidity assumptions make the result worse.

Important implementation finding: `calculate_operation_cost()` in the current cost filter calculates one operation's cost. The backtest's round-trip calculation above doubles per-side commission/spread/slippage for entry plus exit. This test does not change the production module; it flags that any strategy evaluation must model both sides consistently.

## Eighth test: data coverage and quality

Read-only database inventory for 1–26 October:
- 30,526 intraday 15m rows across 136 tickers; actual 15m history starts 13 October and ends 26 October 19:45 UTC.
- Of 30,526 rows, 19,350 (63.4%) are flagged `ok`, 7,557 (24.8%) `zero_volume`, and 3,619 (11.9%) `stale`.
- Daily data exists for 134 tickers, from 1 October through 23 October, but daily data cannot replace missing intraday bars for this test.
- There are only about two weeks of intraday observations; the 10-day time-of-day baseline consequently has very few historical samples for some slots.
- The SQL test filters out stale and zero-volume bars for signal creation and future outcomes. The original Python helper still needs a separate code-level validation before it can be treated as the canonical reproducer; its data-quality handling and its rolling-volume baseline do not exactly match the SQL TOD-A experiment.

## Final conclusion

**Do not activate this momentum scanner as an operational BUY rule and do not modify SAPTA's live BUY logic on the basis of these tests.** The most promising gross filter is momentum >=1.5%, near-breakout, same-time-of-day volume >=1.5x median, but:
1. Mean forward close return is only +0.099% gross and collapses to +0.007% when 23 October is excluded.
2. The conservative non-overlap sample has mean close return -0.139% and only 48.9% positive closes.
3. The first-touch stop/target proxy averages +0.089% gross for the cost-classified US sample, below the configured 0.20% high-liquidity round-trip floor; net average is -0.111% before tax.
4. Configured EU round-trip costs are approximately 1.17–2.35% at €160–€260 notional, so the strategy cannot plausibly overcome them at the observed one-hour return scale.
5. The 15m history is too short and quality flags exclude 36.6% of bars. A handful of strong dates dominates the apparent edge.

The correct next development step, if more evidence is desired, is **data collection and out-of-sample paper evaluation**, not a live-rule change: preserve timestamped candidate signals, simulate sequential fills with both-side costs and gap/slippage rules, and evaluate on several months of complete intraday history. Until that evidence exists, this branch is diagnostic only.

## Final safety boundary

All new database work was SELECT-only. No INSERT/UPDATE/DELETE, DDL, schema change, secret change, alert change, portfolio change or production code edit was performed. Test work remains on `test/momentum-scanner-backtest`, separate from `main`, and the draft PR remains unmerged.


## Final correction: authoritative rerun with quality-filtered future bars

A final audit found that the earlier threshold-sensitivity and regime tables filtered data quality on the signal bar but did not consistently filter the four future bars used for outcome measurement. Those earlier forward-outcome figures are therefore **exploratory only and must not be used as the decision basis**. I reran the rule grid and the TOD-A outcome cohorts requiring all four future 15m bars to be `ok` or NULL, with no future bar flagged `stale` or `zero_volume`. The cost-classified first-touch simulation also uses quality-filtered future bars.

### Authoritative threshold grid

| Rule | Complete signals | Tickers | Mean close after 1h | Median close after 1h | Positive close | Future high >= +2% | Future low <= -1.5% |
|---|---:|---:|---:|---:|---:|---:|---:|
| Momentum >=1.0%, volume >=1.0x, near breakout | 282 | 91 | -0.018% | +0.009% | 50.0% | 3.9% | 8.5% |
| Momentum >=1.0%, volume >=1.5x, near breakout | 200 | 83 | -0.007% | +0.026% | 51.5% | 4.0% | 9.5% |
| Momentum >=1.5%, volume >=1.0x, near breakout | 174 | 74 | -0.076% | -0.009% | 48.9% | 2.9% | 10.3% |
| Momentum >=1.5%, volume >=1.5x, near breakout (TOD-A) | 129 | 67 | -0.086% | -0.003% | 49.6% | 3.1% | 11.6% |
| Momentum >=1.5%, volume >=2.0x, near breakout | 96 | 55 | -0.081% | -0.020% | 49.0% | 3.1% | 13.5% |
| Momentum >=2.0%, volume >=1.0x, near breakout | 122 | 62 | -0.214% | -0.135% | 43.4% | 2.5% | 13.1% |
| Momentum >=2.0%, volume >=1.5x, near breakout | 91 | 54 | -0.221% | -0.124% | 46.2% | 2.2% | 14.3% |
| Momentum >=2.0%, volume >=2.0x, near breakout | 71 | 44 | -0.198% | -0.124% | 45.1% | 1.4% | 16.9% |
| Momentum >=1.5%, volume >=1.5x, strict breakout | 111 | 64 | -0.124% | -0.036% | 48.6% | 3.6% | 12.6% |

**All nine rule variants have a negative mean one-hour close return before costs** once future-bar quality is enforced. Stronger momentum thresholds degrade the mean and increase downside-tail incidence. The earlier +0.099% TOD-A mean was caused by including lower-quality future bars and is superseded by -0.086%.

### Authoritative TOD-A cohorts

| Subset | Complete signals | Mean close after 1h | Median close after 1h | Positive close | Future high >= +2% | Future low <= -1.5% |
|---|---:|---:|---:|---:|---:|---:|
| All | 129 | -0.086% | -0.003% | 49.6% | 3.1% | 11.6% |
| Excluding 23 October | 127 | -0.084% | +0.021% | 50.4% | 3.1% | 11.8% |
| Excluding 19 and 23 October | 123 | -0.109% | -0.003% | 49.6% | 3.3% | 12.2% |
| Opening/session gap >1% | 21 | -0.660% | +0.079% | 57.1% | 4.8% | 23.8% |
| Intraday gap >1% | 20 | +0.027% | -0.191% | 45.0% | 15.0% | 15.0% |
| No absolute gap >1% | 88 | +0.025% | -0.020% | 48.9% | 0.0% | 8.0% |
| Italy (.MI) | 3 | -0.217% | -0.145% | 0.0% | 0.0% | 0.0% |
| USA/other non-.MI | 126 | -0.083% | +0.026% | 50.8% | 3.2% | 11.9% |

The clean opening-gap subset has a mean return of -0.660% and 23.8% of cases hit a future low at least -1.5%. The intraday-gap subset has only 20 observations, median -0.191%, 45% positive closes and 15% downside-tail incidence. Its 15% future +2% high rate is not sufficient evidence of an edge given the tiny sample, negative median and downside risk.

### Final decision after corrected rerun

The conclusion is stronger than the preliminary one: **no tested threshold variant has positive average one-hour close return before costs on the quality-filtered sample.** The TOD-A first-touch proxy has +0.089% average gross simulated return in the US high-liquidity subset, but the configured round-trip cost floor is 0.20%, resulting in -0.111% mean net before tax. The sample is short, overlapping and regime-limited; no variant should be promoted to operational BUY.

This correction supersedes any earlier positive forward-close statistics in this report where future-bar quality was not enforced. All underlying queries remained SELECT-only; no production files or database state were changed.
