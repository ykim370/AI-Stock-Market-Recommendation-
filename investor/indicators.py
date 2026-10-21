"""Indicators computed only from completed, timestamped bars available at as_of."""
from math import isfinite
from statistics import mean
from .recommendations import utc


def visible_bars(rows, as_of):
    cutoff = utc(as_of)
    result=[]
    seen=set()
    for row in rows:
        if utc(row['available_at']) > cutoff:
            continue
        if row['date'] > cutoff.date().isoformat() or utc(row['available_at']).date().isoformat() < row['date']:
            raise ValueError('Invalid bar availability date')
        if row['date'] in seen:
            raise ValueError('Duplicate visible bar')
        seen.add(row['date'])
        bar=dict(row)
        for key in ('open','high','low','close','volume'):
            bar[key]=float(row[key])
            if not isfinite(bar[key]) or bar[key] <= 0:
                raise ValueError('Invalid bar value')
        if not bar['low'] <= min(bar['open'],bar['close']) <= max(bar['open'],bar['close']) <= bar['high']:
            raise ValueError('Invalid OHLC')
        result.append(bar)
    return sorted(result,key=lambda x:x['date'])


def features(rows, as_of, anchor_date=None):
    bars=visible_bars(rows,as_of)
    if len(bars)<60:
        raise ValueError('At least 60 completed bars required')
    close=[x['close'] for x in bars]
    tr=[max(bars[i]['high']-bars[i]['low'],abs(bars[i]['high']-close[i-1]),abs(bars[i]['low']-close[i-1])) for i in range(1,len(bars))]
    # Daily HLC3-volume approximation, not tick-accurate execution VWAP.
    anchor_date=anchor_date or bars[-20]['date']
    anchored=[x for x in bars if x['date']>=anchor_date]
    if not anchored:
        raise ValueError('VWAP anchor is after visible data')
    vwap=sum((x['high']+x['low']+x['close'])/3*x['volume'] for x in anchored)/sum(x['volume'] for x in anchored)
    sma20=mean(close[-20:]); sma50=mean(close[-50:]); old50=mean(close[-55:-5])
    return dict(last_date=bars[-1]['date'], available_at=bars[-1]['available_at'],price=close[-1],previous_close=close[-2],
        sma20=sma20,sma50=sma50,sma50_change=sma50/old50-1,
        market_up=close[-1]>sma50 and sma50>old50,
        market_down=close[-1]<sma50 and sma50<old50,
        returns={str(n):close[-1]/close[-n-1]-1 for n in (1,5,20,59)},
        atr14=mean(tr[-14:]),relative_volume=bars[-1]['volume']/mean([x['volume'] for x in bars[-21:-1]]),
        dollar_volume20=mean([x['volume']*x['close'] for x in bars[-20:]]),
        anchored_vwap=vwap,vwap_anchor=anchor_date,
        prior_high20=max(x['high'] for x in bars[-21:-1]),prior_low20=min(x['low'] for x in bars[-21:-1]),
        low5=min(x['low'] for x in bars[-5:]),high5=max(x['high'] for x in bars[-5:]),
        last_low=bars[-1]['low'],last_high=bars[-1]['high'])
