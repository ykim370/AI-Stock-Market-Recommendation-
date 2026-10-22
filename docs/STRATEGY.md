# Strategy version growth-options-v1

Status: implemented research rules; NOT a validated investment strategy. All numeric
thresholds below are initial hypotheses. No win probability or return is promised.
Capital.com orders remain absent. Every generated card has research_only=true and
cannot pass approval. Prior user approval is not simulated as a real execution.

## Selection rules

Universe: supplied US-equity universe, price >= $5, trailing 20-session average
dollar volume >= $10m. Price/sector/market histories need >=60 completed bars,
aligned sessions, source provenance and audited availability timestamps. There is
no automatic historical universe download or survivorship audit yet.

Long fundamentals: all four latest consecutive fiscal quarters grow YoY, latest
>=15%; same-period revenue-guidance midpoint raised >=2%; operating-margin change
>= -2 percentage points; positive TTM FCF OR >=24-month runway; net debt/revenue
<=1; EV/sales <=2.5 times peer median. Market and sector must be above rising
50-session averages; stock above SMA50 and 20-session return exceeding its sector.

Short fundamentals: revenue guidance cut >=2% or explicitly withdrawn, AND one
of nonpositive latest revenue growth, three successive decelerating growth rates,
margin deterioration >=2 pp, or negative FCF with <18 months runway. Market and
sector below falling SMA50; stock below SMA50 and underperforming sector. Failing
the long criteria does not establish a short thesis.

Broker availability, minimum size, size increment, spread/slippage estimate and
annual financing must have dated provenance. Earnings within two calendar days
blocks new entries. Missing evidence produces an explained NO_TRADE.

## Comparison variants

1. baseline: fundamental eligibility + trend + volatility/risk + broker/catalyst gates.
2. options: additionally require dated options/OI and use the top three 8-30 DTE
   directional gamma concentrations to constrain a prospective target.
3. confirmation: additionally require volume-confirmed entry conditions.
4. macro: additionally apply the CPI surprise/yield-response risk adjustment.

These are additive experiments, not claims that the full version is better.
`compare` runs all four from the same supplied timeline. It does not tune parameters,
create walk-forward folds or independently verify data provenance.

## Options model

Contract gamma concentration = gamma * open_interest * contract_multiplier *
spot^2 * 0.01. Units: estimated USD hedge-notional change per 1% spot move.
Aggregate separately for calls and puts and for 1-7, 8-30, 31-60 calendar DTE.
0DTE and >60 DTE are excluded; zero-OI, invalid and duplicate contracts are counted.
Call/put walls mean maximum gross concentration within a bucket, never guaranteed
resistance/support. The live dealer inventory is unobserved.

Gamma flip: recompute Black-Scholes gamma over 60%-140% of snapshot spot in 0.5%
increments, interpolate sign crossings, and retain all crossings. Two explicit
scenarios are calculated: calls positive/puts negative and dealers short both.
Both long calls and long puts have positive gamma. Assigned signs express assumed
inventory, not an intrinsic call/put property. No crossing is a valid result.
IV, rates and dividend yield are held fixed; default rates/yield are zero. This
European-option approximation does not model American exercise or intraday flow.

Max pain: by individual expiry, find all strike-grid minima of summed intrinsic
payout, weighted by OI and contract multiplier. Premiums are excluded. Max pain
has no directional weight. Only the 8-30 DTE bucket currently gates swing entries;
the others are diagnostics. Reference spot and OI dates must be no more than four
calendar days old; spot must be within 5% of the equity reference price.

## Entries, risk and exits

Daily-bar confirmations, not 30-minute execution signals:
* Breakout long: close above prior 20-session high, relative volume >=1.5.
* Pullback long: today's low near/below SMA20 +0.5 ATR; close above SMA20,
  daily anchored VWAP and previous close; relative volume >=1.1.
* Breakdown short: close below prior 20-session low and VWAP; relative volume >=1.5.

Daily anchored VWAP uses HLC3 * volume anchored to the latest 20 sessions by default.
It is an approximation, not tick VWAP or an earnings-date anchor. ATR14 is the mean
of 14 true ranges (not Wilder smoothing). Support/resistance uses preceding bars.

Initial stop: beyond recent five-session extreme by 0.25 ATR, with distance at
least 1.5 ATR. Initial target: 3 times stop distance, constrained by an intervening
options concentration where present. Require >=1.5:1 reward/risk after estimated
round-trip and ten-calendar-day financing costs. Size for <=0.5% initial equity
risk INCLUDING those estimated costs and <=15% notional per name, rounded DOWN
to broker increment; reject below minimum size. Never round a stop toward less
risk and claim a tighter guarantee. Current report is indicative pending tick rules.

CPI: original monthly core actual minus pre-release consensus in percentage points.
Both publication and consensus timestamps are required. A surprise >=+0.1 pp with
rising two-year yields is adverse to longs; <=-0.1 pp with falling yields is adverse
to shorts. Adverse/high-sensitivity entries are blocked; other adverse entries have
half risk. Sensitivity is a supplied, audited label, not an implemented regression.
Headline CPI and conflicting component analysis remain future enhancements.

Backtest entries fill next available session open; recheck direction and after-cost
reward/risk at that price. Carry through proposed stop/target, maximum size, broker
increments and cost/financing assumptions. If both stop and target hit within a
bar, stop is conservatively assumed first. Gap stops use opening price. No separate
limit-fill, queue, market-impact or manual-approval-delay model exists.

Five-session default time exit. At 8% drawdown risk halves; at 12% entries block and
positions exit next open; at 15% a persistent halt is recorded. These are daily
checks, not a guaranteed 15% cap. Intraday monitoring and dynamic thesis exits are
not implemented. Portfolio correlation/sector caps remain to be added.

## Point-in-time input contract

Use examples/build_fixture.py for a fully worked SYNTHETIC schema. `as_of` must be
timezone-aware; each bar and evidence record has `available_at`. Revenue records
include fiscal year/quarter, period_end, currency, revenue and source. Only versions
available by the decision time are considered; corresponding prior-year quarters
must exist. Guidance needs two updates with matching fiscal_period, revenue metric,
currency and basis. A verified flag is an upstream auditor's assertion, not evidence
that the program has checked a source document. Audit all flags before using real data.

Latest Alpha Vantage statements are NOT silently promoted into historical facts.
Normalized guidance, quality, calendars, macro and broker histories must currently
be prepared upstream. Options CLI can analyse the original Alpha Vantage response,
but does not mark it verified for selection automatically. If --multiplier 100 is
used, all contracts' standard deliverables must be verified independently.

## Validation performed

18 automated tests cover gamma formula/units, max-pain expiry separation/ties,
multiple/no flip cases, invalid options, long/short qualification, future bars and
restatements, comparable guidance, missing data, adverse CPI, thin reward, risk
halts, research approval blocking, gap fills and four-variant integration.

Actual API checks succeeded for MSFT income statements, daily prices and historical
options. A 2025-10-20 MSFT chain had 3,316 records; 943 usable nonzero-OI contracts
fell in the selected 1-60 DTE range. Calculation used an assumed multiplier of 100;
this is a connectivity/calculation check, NOT independent validation of dealer
positioning or evidence of strategy returns. Raw provider data remains private.

No real historical strategy return, calibrated success rate or out-of-sample edge
has yet been established. Synthetic returns are software checks only.

Primary API documentation: https://www.alphavantage.co/documentation/#options
