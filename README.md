# AI Stock Market Recommendation

A Python research prototype for a $10,000 Capital.com portfolio. It targets shorter,
trend-aware holds, growing revenue and raised management guidance for longs,
deteriorating fundamentals for shorts, and a 15% peak-to-trough drawdown objective.
The objective is not a guaranteed loss limit.

## Current status

Implemented: Alpha Vantage snapshot/options ingestion; deterministic long/short
selection; point-in-time input filtering; call/put gamma concentrations; gamma-flip
scenarios; per-expiry max pain; trend, volume, volatility and core-CPI filters;
explanatory PDF cards; research approvals; and a daily-bar backtester with an
additive four-variant comparison runner. The institutional research variant adds
pre-announcement expectations, 30/90-day estimate revisions, portfolio exposure
and stress gates, and a reproducible input-audit report.

**No live broker execution, scheduled jobs or deployed email service exists.**
The selection engine consumes audited normalized historical evidence; automatic
collection/verification of guidance, CPI consensus and broker histories is not yet
implemented. Latest financial snapshots cannot substitute for those histories.

All generated strategy cards are research-only and cannot be approved for trading.
The generic approval inbox records intent only; it has no broker adapter. No real
historical investment performance is claimed. See [strategy details](docs/STRATEGY.md)
for exact rules, assumptions, test results and remaining limitations.

## Run locally

Python 3.11+:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m investor report examples/recommendations.json
python -m investor serve
```

The PDF is generated in `output/pdf/recommendations.pdf`. Click its review link
while the local server is running. GET requests display proposals only; a button
submits a POST decision. Sample proposals can be rejected, never accepted.

Environment variables are documented in `.env.example`. This program does not
automatically load `.env`; inject variables through your shell or secret manager.
Do not put API keys, recipients, financial data or approval databases in GitHub.

```bash
python -m investor fetch MSFT
python -m investor backtest private/bars.csv private/signals.csv --holding-days 5
python -m investor report private/recommendations.json --send
```

Sending requires a configured SMTP account, recipient and an HTTPS approval URL.
The approval service must remain online with persistent private database storage.
Local HTTP is for development only. Email scanners cannot approve by following links.
Tokens are bearer credentials: anyone receiving a forwarded link could decide.
Production deployment should add authenticated owner sign-in, request limits,
HTTPS proxy configuration and durable notification retry/deduplication.

## Recommendation brief

Each card requires a plain-language thesis; timestamped prices; entry, stop,
target and units; and sourced, publication-dated evidence for:

* Four quarters of year-over-year revenue growth and consistency.
* Same-period management guidance revisions, distinct from analyst estimates.
* Profitability, free cash flow, debt, financing needs and cash runway.
* Valuation compared with peers and expected growth.
* Overall-market and sector trend and relative strength.
* CPI actual versus pre-release consensus, yield reaction and rate sensitivity.
* Price performance, volatility, liquidity and recent drawdown.
* Upcoming catalysts, earnings, downside scenarios and reasons the thesis could fail.
* Capital.com instrument availability, spread, financing and trade restrictions.

Missing/expired evidence means **do not approve**. All numbers in the example
are illustrative, not current quotes, forecasts or verified investment claims.
Live approval must ultimately bind to exact order terms and expiry; recheck
price, broker availability, portfolio risk and open orders immediately before
execution. Material changes require a new approval. Notify only after broker
confirmation, including fills, rejected orders, partial fills and closed P&L.

## Backtest inputs and limitations

`bars.csv`: date,symbol,open,high,low,close. Include SPY each session; use ISO dates.
Corporate-action handling must be consistent; do not mix raw and adjusted bars.
`signals.csv`: date,symbol,side,known_at,verified. Side is BUY or SHORT; verified is
true only following an upstream point-in-time audit. Dates are daily, not release
instant timestamps. Signal on date D can fill only next available market day.

A 50-session SPY average filters direction. Maximum five positions, 15% initial
notional per name, 0.5% initial planned equity risk per trade and 5% price stops.
At 8% drawdown new risk halves; at 12% entries stop and positions exit next open;
at 15% a persistent halt is set. Daily observation cannot guarantee a 15% cap.
Default costs are **assumptions**: 10 basis points per side and 10% annual financing.
No short borrow or broker cost is claimed to be historically verified.

The simulator lacks dividends, intraday event ordering, historical broker
universe/availability, precise CPI release handling, realistic approval delays
and automatic historical evidence ingestion. Missing held bars fail rather than
silently dropping a delisted company. Final positions close with costs.
Latest Alpha Vantage statements are saved with retrieval timestamps and explicitly
marked not verified for historical availability. Never backfill their current
values into earlier decisions without reconciling original releases/restatements.

## Strategy commands

```bash
# Fully synthetic, repeatable software demonstration (not investment results).
python examples/build_fixture.py
python -m investor select output/fixture/bundles.json --variant macro --output output/selection
python -m investor select output/fixture/institutional-bundle.json --output output/institutional
python -m investor validate output/fixture/institutional-bundle.json
python -m investor compare output/fixture/bundles.json output/fixture/bars.csv
python -m investor report output/selection/cards.json

# Real provider access; set ALPHAVANTAGE_API_KEY securely first.
python -m investor fetch-options MSFT 2025-10-20
# Multiplier is explicit; verify standard contract deliverables before using 100.
python -m investor options private/options/MSFT/2025-10-20.json --spot 100 --date 2025-10-20 --multiplier 100
```

The spot value above is a placeholder; replace it with the actual same-date raw
underlying close. Never use today's quote for an old chain. Commands operate on
local files; no report is emailed unless --send is explicitly supplied.

The `select` CLI defaults to the stricter `institutional` variant. Its additional
input schema, assumptions and limitations are in [the institutional specification](docs/INSTITUTIONAL.md).
The four-way `compare` remains unchanged; it does not test the new portfolio gates.

## Next implementation milestones

1. Audit Alpha Vantage entitlements and sample coverage; obtain point-in-time
   financial/guidance history, CPI actual/consensus and Capital.com instrument costs.
2. Build source-grounded guidance extraction and feed audited real records into the implemented growth/short rules.
3. Expand the core-CPI overlay to headline/components, add intraday execution, benchmarks and
   chronological walk-forward evaluation; keep an untouched test period.
4. Deploy authenticated HTTPS approvals and configure SMTP. Schedule by US market
   sessions and daylight saving, with pre-market PDFs and event updates.
5. Integrate Capital.com **demo only** with confirm-before-retry reconciliation,
   duplicate prevention and notifications for confirmed execution.
6. Evaluate demo results before any separate decision to enable live execution.

Email approval is required for proposed trades. Whether protective exits can
execute without new approval remains a user decision before broker integration.
