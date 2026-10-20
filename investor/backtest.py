"""Small daily-bar reference simulator. Input signals must be point-in-time verified.

Schema: bars(date,symbol,open,high,low,close), signals(date,symbol,side,known_at,
verified). date is the decision date; all orders fill next available market day.
Bars must use a consistent corporate-action basis. Price-only simulation does not
model dividends; do not use its results as validated investment performance.
"""
import csv
import math
from collections import defaultdict
from datetime import date


def run(bars_path, signals_path, holding_days=5, cost_bps=10, annual_financing=.10):
    if holding_days < 1 or cost_bps < 0 or annual_financing < 0:
        raise ValueError('Invalid simulation parameters')
    days = defaultdict(dict)
    with open(bars_path) as f:
        for row in csv.DictReader(f):
            values = {k: float(row[k]) for k in ('open','high','low','close')}
            if not all(math.isfinite(v) and v > 0 for v in values.values()):
                raise ValueError('Invalid price')
            if not values['low'] <= min(values['open'],values['close']) <= max(values['open'],values['close']) <= values['high']:
                raise ValueError('Invalid OHLC')
            if row['symbol'] in days[row['date']]:
                raise ValueError('Duplicate bar')
            days[row['date']][row['symbol']] = values
    signals = defaultdict(list)
    with open(signals_path) as f:
        for row in csv.DictReader(f):
            if row['verified'].lower() != 'true' or row['known_at'] > row['date']:
                raise ValueError('Unverified or future signal')
            if row['side'] not in ('BUY','SHORT') or row['date'] not in days:
                raise ValueError('Invalid signal')
            signals[row['date']].append(row)
    cash = peak = 10000.
    positions, pending, curve, trades = {}, [], [], []
    halted = False
    dd = max_dd = 0.
    prev_date = None
    fee = cost_bps / 10000

    def close(symbol, price, reason, day):
        nonlocal cash
        pos = positions.pop(symbol)
        pnl = pos['side']*pos['units']*(price-pos['entry'])
        exit_fee = pos['units']*price*fee
        cash += pnl-exit_fee
        trades.append(dict(symbol=symbol, opened=pos['date'], closed=day, reason=reason,
                           pnl_after_costs=pnl-exit_fee-pos['entry_fee']-pos['financing']))

    for day, market in sorted(days.items()):
        if 'SPY' not in market:
            raise ValueError('SPY benchmark required every day')
        for symbol in list(positions):
            if symbol not in market:
                raise ValueError('Missing held position bar: supply delisting/action treatment')
            pos = positions[symbol]
            elapsed = (date.fromisoformat(day)-date.fromisoformat(prev_date)).days
            financing = pos['units']*pos['mark']*annual_financing/365*elapsed
            cash -= financing
            pos['financing'] += financing
            pos['age'] += 1
            if halted or dd >= .12 or pos['age'] >= holding_days:
                close(symbol, market[symbol]['open'], 'risk_exit' if halted or dd >= .12 else 'time_exit', day)
        for signal in pending:
            symbol = signal['symbol']
            if halted or dd >= .12 or symbol in positions or symbol not in market or len(positions) >= 5:
                continue
            entry = market[symbol]['open']
            side = 1 if signal['side']=='BUY' else -1
            equity = cash + sum(p['side']*p['units']*(market[s]['open']-p['entry']) for s,p in positions.items())
            risk = max(0,equity)*(.0025 if dd >= .08 else .005)
            units = min(risk/(entry*.05), max(0,equity)*.15/entry)
            if units <= 0:
                continue
            entry_fee = units*entry*fee
            cash -= entry_fee
            positions[symbol] = dict(entry=entry, units=units, side=side, stop=entry*(1-.05*side), age=0, date=day, mark=entry, financing=0.,entry_fee=entry_fee)
        for symbol in list(positions):
            pos, bar = positions[symbol], market[symbol]
            crossed = bar['low'] <= pos['stop'] if pos['side']==1 else bar['high'] >= pos['stop']
            if crossed:
                fill = min(bar['open'],pos['stop']) if pos['side']==1 else max(bar['open'],pos['stop'])
                close(symbol, fill, 'stop', day)
            else:
                pos['mark'] = bar['close']
        equity = cash+sum(p['side']*p['units']*(p['mark']-p['entry']) for p in positions.values())
        peak = max(peak,equity)
        dd = (peak-equity)/peak
        max_dd = max(max_dd,dd)
        halted = halted or dd >= .15
        curve.append(dict(date=day,equity=equity,drawdown=dd))
        # Overall-market trend uses information known at this close only.
        recent_days = [d for d in sorted(days) if d <= day][-50:]
        mean = sum(days[d]['SPY']['close'] for d in recent_days)/len(recent_days)
        up = market['SPY']['close'] > mean
        pending = [s for s in signals[day] if len(recent_days)==50 and ((s['side']=='BUY' and up) or (s['side']=='SHORT' and not up))]
        prev_date = day
    if curve:
        for symbol in list(positions):
            close(symbol, positions[symbol]['mark'], 'end_of_test', curve[-1]['date'])
        curve[-1]['equity'] = cash
        max_dd = max(max_dd,(peak-cash)/peak)
        curve[-1]['drawdown'] = (peak-cash)/peak
    return dict(label='RESEARCH SIMULATION - NOT VALIDATED', initial_equity=10000, final_equity=cash,
                return_pct=(cash/10000-1)*100, maximum_drawdown_pct=max_dd*100,
                halted=halted, trades=trades, equity_curve=curve,
                limitations=['Daily bars; intraday order sequence approximated','Constant cost and financing assumptions',
                              'No dividend, historical broker availability or CPI consensus integration',
                              'Signals supplied externally; verified flag requires upstream audit',
                              'Approval delay not modeled; automatic signals are an upper-bound operational assumption'])
