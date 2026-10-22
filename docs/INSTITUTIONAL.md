# Institutional research layer v1

Implemented as a deterministic addition to the existing macro strategy. These
thresholds are initial research hypotheses, not optimised rules or probabilities.
There is no automatic broker connection, live approval or performance claim.

## Expectations before an announcement

Longs require revenue guidance midpoint at least 2% above comparable consensus
available strictly before the guidance release; shorts require at least 2% below.
Revenue and EPS aggregate estimates must both move in the trade direction over
30 and 90 calendar days. Changes use `(current - old) / abs(old)`, including EPS
loss estimates. Zero bases are rejected. No analyst-level revision breadth is
claimed; changes in analyst coverage can change aggregate estimates.

Consensus must match fiscal period, reported/organic basis and currency. Current
snapshots must be at most seven days old. Historical snapshots must already have
been available at the 30/90-day anchor and recorded within seven days before it.
Pre-announcement consensus must have been recorded within seven days of release.
At least three analysts and a consistent provider are required. Guidance withdrawal
is blocked pending a separately validated expectations model. This strict model
will intentionally skip companies with incomplete histories.

Each existing guidance row additionally needs `release_at`. Each `consensus` row:

```json
{
  "source": "Source document or licensed snapshot reference",
  "point_in_time_verified": true,
  "available_at": "2025-04-01T12:00:00Z",
  "recorded_at": "2025-04-01T11:59:00Z",
  "metric": "revenue",
  "fiscal_period": "FY2025",
  "currency": "USD",
  "basis": "reported",
  "analyst_count": 8,
  "provider": "Provider identifier",
  "mean": 500000000
}
```

EPS requires corresponding `metric: eps` rows with compatible reporting basis;
never compare adjusted EPS to reported EPS or different fiscal targets. The
upstream normaliser owns currency/unit consistency and independent verification.
A verification flag alone does not establish provenance.

## Portfolio gate

`portfolio` is an audited snapshot with `source`, `point_in_time_verified`,
`available_at`, `equity_usd`, `peak_equity_usd` and `positions`. It must be no more
than one day old and available by the decision timestamp. Each existing position
needs `symbol`, `side` (`BUY` or `SHORT`), positive `units`, `mark_usd`, `stop_usd`,
`sector`, `theme`, and finite `beta`. USD values must include currency conversion.
The snapshot provider must verify all positions, marks, open commitments and costs;
this module does not fetch or reconcile them. Open orders are not modelled yet.

`classification` supplies the candidate's `sector`, `theme`, `beta` plus source,
verification and availability fields. Maximum age is 90 days. Beta must be an
estimate using data available at that timestamp, not a current estimate backfilled.

After adding the proposed position, gates are:

| Measure | Limit |
| --- | --- |
| Gross notional / equity | 60% |
| Absolute signed beta exposure / equity | 60% |
| Each sector and each theme gross exposure | 30% |
| Sum of remaining stop losses / equity | 3% |
| Loss in any specified stress scenario | 10% |
| Position count | Five |
| Current peak-to-trough drawdown | Block at 12% |

Existing same-symbol holdings block automatic pyramiding. Existing positions are
marked to the supplied snapshot; risk measures remaining mark-to-stop loss, not
original entry loss. A stop beyond the mark contributes zero further stop loss;
actual execution status must be reconciled separately.

Market stress applies +/-10% market moves scaled by each supplied beta, with
signed long/short P&L. Separate adverse-gap stress applies simultaneous 15% falls
to longs and 30% rises to shorts with no hedge credit. These are fixed scenarios,
not a covariance model or worst-case bounds. Correlation, volatility shifts,
liquidation costs and short squeezes beyond 30% still need modelling. A 15%
maximum drawdown is an objective, not a guarantee.

Each bundle is evaluated against its supplied account independently. Multiple
passing candidates cannot simply all be executed: sequential risk reservation,
open-order accounting and an approval-time portfolio recheck are not implemented.
The `compare` command retains its four original variants; it does not claim to
backtest these new portfolio constraints over a changing account.

## Reports and validation

Recommendation cards include expectations and portfolio stress explanations and
feed those sections to the existing PDF renderer. They remain research-only.
`select` also writes `validation.json` plus a local `experiments.jsonl` record.
`validate` can create the same audit without selecting trades.

Audits identify synthetic inputs, duplicate snapshots, missing dated evidence,
input SHA-256 and Python code SHA-256. Coverage measures presence, not correctness
or freshness. The registry is a local append log, not tamper-proof storage or a
preregistered experiment service. It is not a return report and always sets
`ready_for_live_trading` to false. No holdout, benchmark or walk-forward result is
inferred from synthetic tests. Selection rules perform additional semantic checks.

## Verification and next work

29 unit/integration tests pass, including future-data exclusion, pre-release
consensus timing, comparability, short stress signs, concentration, missing inputs,
registry reproducibility and all previous strategy/approval checks.

Next: source and independently audit historical consensus/guidance and broker
terms; build dynamic portfolio replay with benchmark and chronological holdout;
implement fresh-quote approval rechecks, authenticated hosting and Capital.com
demo execution. Real data coverage and entitlements remain to be established.
