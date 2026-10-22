"""Transparent option concentration and scenario gamma estimates, not dealer inventory.
Dollar gamma units: hedge-notional change for a 1% underlying move.
Black-Scholes revaluation assumes fixed IV, rate and dividend yield; American
exercise and intraday positioning changes are not modeled. No 0DTE extrapolation.
"""
from collections import defaultdict
from datetime import date
from math import exp, isfinite, log, pi, sqrt

BUCKETS = ((1, 7), (8, 30), (31, 60))


def positive(value, allow_zero=False):
    value = float(value)
    if not isfinite(value) or value < 0 or (value == 0 and not allow_zero):
        raise ValueError('Expected finite positive number')
    return value


def bs_gamma(spot, strike, years, iv, rate=0.0, dividend_yield=0.0):
    spot, strike, years, iv = map(positive, (spot, strike, years, iv))
    if not all(isfinite(x) for x in (rate, dividend_yield)):
        raise ValueError('Invalid rate')
    d1 = (log(spot/strike) + (rate-dividend_yield+iv*iv/2)*years)/(iv*sqrt(years))
    return exp(-dividend_yield*years-d1*d1/2)/(sqrt(2*pi)*spot*iv*sqrt(years))


def max_pain(contracts):
    """Minimum total intrinsic payout per expiration; premiums are not included."""
    by_expiry = defaultdict(list)
    for c in contracts:
        by_expiry[c['expiration']].append(c)
    result = {}
    for expiry, chain in by_expiry.items():
        costs = []
        for price in sorted({c['strike'] for c in chain}):
            total = sum(c['open_interest']*c['multiplier']*max(0, (price-c['strike']) if c['type']=='call' else (c['strike']-price)) for c in chain)
            costs.append((price, total))
        minimum = min(cost for _, cost in costs)
        result[expiry] = {'strikes': [p for p, cost in costs if abs(cost-minimum) < 1e-6], 'intrinsic_payout': minimum}
    return result


def crossing_levels(profile):
    """Return every bracketed crossing, not a fabricated single flip."""
    if not profile or all(abs(y) < 1e-12 for _, y in profile):
        return []
    result = []
    for (a, ya), (b, yb) in zip(profile, profile[1:]):
        if ya == 0:
            result.append(a)
        elif ya*yb < 0:
            result.append(a+(b-a)*abs(ya)/(abs(ya)+abs(yb)))
    if profile[-1][1] == 0:
        result.append(profile[-1][0])
    return sorted(set(round(x, 6) for x in result))


def analyse(contracts, spot, as_of_date, rate=0.0, dividend_yield=0.0):
    spot = positive(spot)
    today = date.fromisoformat(as_of_date)
    valid, exclusions, seen = [], defaultdict(int), set()
    for raw in contracts:
        try:
            c = {k: raw[k] for k in ('type','expiration')}
            if c['type'] not in ('call','put'):
                raise ValueError('type')
            c['strike'] = positive(raw['strike'])
            c['multiplier'] = positive(raw['multiplier'])
            c['open_interest'] = positive(raw['open_interest'], True)
            c['gamma'] = positive(raw['gamma'], True)
            c['iv'] = positive(raw['implied_volatility'])
            c['dte'] = (date.fromisoformat(c['expiration'])-today).days
            if not 1 <= c['dte'] <= 60:
                exclusions['outside_1_60_days_including_0dte'] += 1
                continue
            key = (c['type'],c['expiration'],c['strike'],c['multiplier'])
            if key in seen:
                exclusions['duplicate_contract'] += 1
                continue
            seen.add(key)
            if c['open_interest'] == 0:
                exclusions['zero_open_interest'] += 1
                continue
            valid.append(c)
        except (ValueError, TypeError, KeyError, OverflowError):
            exclusions['invalid_contract'] += 1
    if not valid:
        raise ValueError('No usable options with verified multiplier, IV, gamma and OI')
    groups = {}
    for low, high in BUCKETS:
        chain = [c for c in valid if low <= c['dte'] <= high]
        if not chain:
            continue
        call, put = defaultdict(float), defaultdict(float)
        for c in chain:
            value = c['gamma']*c['open_interest']*c['multiplier']*spot*spot*.01
            (call if c['type']=='call' else put)[c['strike']] += value
        # Explicit convention scenarios. Neither is a measurement of dealer books.
        scenarios = {}
        for name, call_sign, put_sign in (('calls_positive_puts_negative', 1, -1), ('dealers_short_both', -1, -1)):
            profile=[]
            for i in range(161):
                price=spot*(.6+i*.005)
                value=sum((call_sign if c['type']=='call' else put_sign)*bs_gamma(price,c['strike'],c['dte']/365,c['iv'],rate,dividend_yield)*c['open_interest']*c['multiplier']*price*price*.01 for c in chain)
                profile.append((price,value))
            scenarios[name]={'net_gamma_at_spot':profile[80][1], 'flip_levels':crossing_levels(profile), 'grid_min':spot*.6,'grid_max':spot*1.4}
        ranked_calls=sorted(call.items(),key=lambda x:(-x[1],x[0]))
        ranked_puts=sorted(put.items(),key=lambda x:(-x[1],x[0]))
        groups[f'{low}_{high}']={
            'call_wall': ranked_calls[0][0] if ranked_calls and ranked_calls[0][1] > 0 else None,
            'put_wall': ranked_puts[0][0] if ranked_puts and ranked_puts[0][1] > 0 else None,
            'call_concentrations':ranked_calls,'put_concentrations':ranked_puts,
            'gamma_scenarios':scenarios,'max_pain_by_expiry':max_pain(chain), 'contract_count':len(chain)}
    return {'spot':spot,'date':as_of_date,'buckets':groups,'exclusions':dict(exclusions),
            'units':'USD hedge-notional change per 1% spot move',
            'assumptions':['Open interest does not reveal signed dealer inventory',
              'Call/put walls are gamma concentrations, not guaranteed support/resistance',
              'Gamma flips depend on inventory assumptions and fixed-IV Black-Scholes approximation',
              'No flip within the scanned range is a valid result',
              'Max pain excludes premiums; it has no directional vote',
              '0DTE is excluded; multiplier must be supplied explicitly']}
