"""Versioned, deterministic research strategy. Scores are not probabilities.
Input evidence is an audited point-in-time bundle; this module does not invent
missing guidance, dealer positions, broker availability or historical provenance.
"""
from datetime import timedelta
from math import floor, isfinite
from .indicators import features
from .options import analyse
from .recommendations import utc

VERSION='growth-options-v1'
VARIANTS=('baseline','options','confirmation','macro')


def visible(records, as_of):
    cutoff=utc(as_of)
    return sorted([r for r in records if utc(r['available_at'])<=cutoff],key=lambda x:utc(x['available_at']))


def audit(record):
    return bool(record.get('source') and record.get('point_in_time_verified') is True)


def number(record, key):
    value=float(record[key])
    if not isfinite(value):
        raise ValueError('Non-finite '+key)
    return value


def revenue_growth(records, as_of):
    # Original reports/restatements become eligible only at their own availability.
    revisions={}
    for r in visible(records,as_of):
        if audit(r):
            quarter=int(r['fiscal_quarter']); year=int(r['fiscal_year'])
            if quarter not in (1,2,3,4) or r['period_end']>utc(r['available_at']).date().isoformat():
                raise ValueError('Invalid fiscal period')
            revisions[(year,quarter)]=r
    periods=sorted(revisions)[-4:]
    if len(periods)!=4 or any((periods[i][0]*4+periods[i][1])-(periods[i-1][0]*4+periods[i-1][1])!=1 for i in range(1,4)):
        raise ValueError('Four consecutive revenue quarters required')
    growth=[]; used=[]
    for year,q in periods:
        current=revisions[(year,q)]; prior=revisions.get((year-1,q))
        if prior is None or current.get('currency')!=prior.get('currency'):
            raise ValueError('Comparable prior-year revenue unavailable')
        base=number(prior,'revenue'); value=number(current,'revenue')
        if base<=0 or value<0:
            raise ValueError('Revenue growth undefined for nonpositive base')
        growth.append(value/base-1); used.extend([prior,current])
    return growth,used


def guidance_change(records, as_of):
    rows=[r for r in visible(records,as_of) if audit(r) and r.get('metric')=='revenue']
    if not rows:
        raise ValueError('No verified revenue guidance')
    latest=rows[-1]
    if latest.get('status')=='withdrawn':
        return None,[latest],True
    peers=[r for r in rows[:-1] if all(r.get(k)==latest.get(k) for k in ('fiscal_period','metric','currency','basis')) and r.get('status')!='withdrawn']
    if not peers:
        raise ValueError('No comparable same-period previous guidance')
    previous=peers[-1]
    for r in (previous,latest):
        if not r.get('basis') or not r.get('currency') or number(r,'low')<=0 or number(r,'high')<number(r,'low'):
            raise ValueError('Invalid guidance range')
    old=(number(previous,'low')+number(previous,'high'))/2
    new=(number(latest,'low')+number(latest,'high'))/2
    return new/old-1,[previous,latest],False


def decide(bundle, variant='macro', equity=10000., drawdown=0.):
    if variant not in VARIANTS or not isfinite(equity) or equity<=0 or not 0<=drawdown<=1:
        raise ValueError('Invalid strategy parameters')
    as_of=bundle['as_of']; utc(as_of)
    result={'symbol':bundle['symbol'],'as_of':as_of,'strategy_version':VERSION,'variant':variant,
            'decision':'NO_TRADE','reasons':[],'warnings':[],'metrics':{},'sample':bool(bundle.get('sample',False))}
    def reject(reason):
        result['reasons'].append(reason)
        return result
    if drawdown>=.12:
        return reject('Portfolio drawdown blocks new entries at 12% or greater')
    try:
        if bundle.get('price_history_verified') is not True or not bundle.get('price_source'):
            return reject('Price history source and availability audit required')
        stock=features(bundle['bars']['stock'],as_of)
        market=features(bundle['bars']['market'],as_of)
        sector=features(bundle['bars']['sector'],as_of)
        if len({stock['last_date'],market['last_date'],sector['last_date']})!=1:
            return reject('Stock, market and sector sessions do not align')
        if (utc(as_of).date()-utc(stock['available_at']).date()).days>4:
            return reject('Market data too old for research selection')
        if stock['price']<5 or stock['dollar_volume20']<10_000_000:
            return reject('Price or liquidity below research universe threshold')
        growth,revenue_sources=revenue_growth(bundle['revenue'],as_of)
        guide,guidance_sources,withdrawn=guidance_change(bundle['guidance'],as_of)
        qualities=[q for q in visible(bundle['quality'],as_of) if audit(q)]
        if not qualities:
            return reject('No audited quality/valuation snapshot')
        quality=qualities[-1]
        if (utc(as_of)-utc(quality['available_at'])).days>140 or (utc(as_of)-utc(revenue_sources[-1]['available_at'])).days>140:
            return reject('Fundamentals are stale')
        margin=number(quality,'operating_margin_change_pp')
        fcf=number(quality,'free_cash_flow_ttm')
        runway=number(quality,'cash_runway_months')
        leverage=number(quality,'net_debt_to_revenue')
        valuation=number(quality,'ev_sales_to_peer_median')
        if runway<0 or valuation<=0:
            return reject('Invalid quality snapshot')
        relative=stock['returns']['20']-sector['returns']['20']
        result['metrics'].update(technicals=stock,revenue_growth_yoy=growth,guidance_change=guide,guidance_withdrawn=withdrawn,relative_strength_20d=relative,quality=quality)
        long_ok=all(g>0 for g in growth) and growth[-1]>=.15 and guide is not None and guide>=.02 and margin>=-2 and (fcf>0 or runway>=24) and leverage<=1 and valuation<=2.5
        deterioration=(guide is not None and guide<=-.02) or withdrawn
        short_ok=deterioration and (growth[-1]<=0 or growth[-1]<growth[-2]<growth[-3] or margin<=-2 or (fcf<0 and runway<18))
        side=None
        if long_ok and market['market_up'] and sector['market_up'] and stock['price']>stock['sma50'] and relative>0:
            side='BUY'
        elif short_ok and market['market_down'] and sector['market_down'] and stock['price']<stock['sma50'] and relative<0:
            side='SHORT'
        if not side:
            return reject('Fundamental eligibility, market/sector direction and relative strength do not align')
        result['reasons'] += ['Revenue and same-period guidance pass '+side+' rules', 'Market, sector and relative strength support direction']
        # No new entry within two calendar days of earnings, unless explicitly tested later.
        calendars=[x for x in visible(bundle.get('events',[]),as_of) if audit(x)]
        if not calendars:
            return reject('Verified earnings calendar is missing')
        event=calendars[-1]
        until=(utc(event['next_earnings_at'])-utc(as_of)).total_seconds()/86400
        if until<0 or until<=2:
            return reject('Earnings calendar stale or earnings within two days')
        entry=stock['price']; atr=stock['atr14']
        if atr<=0:
            return reject('Invalid volatility')
        stop=min(stock['low5']-.25*atr,entry-1.5*atr) if side=='BUY' else max(stock['high5']+.25*atr,entry+1.5*atr)
        risk=abs(entry-stop)
        target=entry+3*risk if side=='BUY' else entry-3*risk
        if stop<=0 or target<=0:
            return reject('Invalid positive price levels')
        option_result=None
        if variant in ('options','confirmation','macro'):
            opts=[o for o in visible(bundle.get('options',[]),as_of) if audit(o)]
            if not opts:
                return reject('Verified historical options snapshot unavailable')
            snapshot=opts[-1]
            d=utc(as_of).date()
            chain_date=utc(snapshot['available_at']).date()
            from datetime import date
            observation=date.fromisoformat(snapshot['date']); oi_date=date.fromisoformat(snapshot['oi_date'])
            if not oi_date<=observation<=chain_date<=d or (d-observation).days>4 or (d-oi_date).days>4:
                return reject('Stale or inconsistent option/OI dates')
            if abs(number(snapshot,'spot')/entry-1)>.05:
                return reject('Options reference price differs from stock by more than 5%')
            option_result=analyse(snapshot['contracts'],snapshot['spot'],snapshot['date'])
            result['metrics']['options']=option_result
            bucket=option_result['buckets'].get('8_30')
            if not bucket:
                return reject('No 8-30 day options coverage for swing strategy')
            # Concentrations only constrain reward; gamma sign is never a bullish vote.
            key='call_concentrations' if side=='BUY' else 'put_concentrations'
            ranked=bucket[key][:3]
            overhead=[p for p,v in ranked if v>0 and (p>entry if side=='BUY' else p<entry)]
            if overhead:
                wall=min(overhead) if side=='BUY' else max(overhead)
                target=min(target,wall-.1*atr) if side=='BUY' else max(target,wall+.1*atr)
            result['warnings'].append('Options walls and gamma flips are estimates, not guaranteed price barriers')
        setup='fundamental_trend'
        if variant in ('confirmation','macro'):
            if side=='BUY':
                breakout=entry>stock['prior_high20'] and stock['relative_volume']>=1.5
                pullback=stock['last_low']<=stock['sma20']+.5*atr and entry>stock['sma20'] and entry>stock['anchored_vwap'] and entry>stock['previous_close'] and stock['relative_volume']>=1.1
                if not breakout and not pullback:
                    return reject('No volume-confirmed breakout or pullback recovery')
                setup='breakout' if breakout else 'pullback_recovery'
            else:
                breakdown=entry<stock['prior_low20'] and stock['relative_volume']>=1.5 and entry<stock['anchored_vwap']
                if not breakdown:
                    return reject('No volume-confirmed breakdown below support/VWAP')
                setup='breakdown'
        risk_multiplier=1.
        if variant=='macro':
            observations=[c for c in visible(bundle.get('macro',[]),as_of) if audit(c)]
            if not observations:
                return reject('Verified CPI consensus/release observation unavailable')
            macro=observations[-1]
            if not utc(macro['consensus_recorded_at'])<utc(macro['release_at'])<=utc(macro['available_at']):
                return reject('CPI consensus must predate the release')
            if (utc(as_of)-utc(macro['release_at'])).days>45:
                return reject('CPI observation stale')
            surprise=number(macro,'core_actual_mom_pct')-number(macro,'core_consensus_mom_pct')
            yield_move=number(macro,'treasury_2y_change_bps')
            sensitivity=quality.get('rate_sensitivity')
            if sensitivity not in ('high','medium','low'):
                return reject('Rate sensitivity not assessed')
            adverse=(side=='BUY' and surprise>=.1-1e-9 and yield_move>0) or (side=='SHORT' and surprise<=-.1+1e-9 and yield_move<0)
            if adverse and sensitivity=='high':
                return reject('CPI surprise/yield reaction adverse to high-sensitivity position')
            if adverse:
                risk_multiplier=.5
            result['metrics']['macro']={'core_surprise_pp':surprise,'yield_change_bps':yield_move,'sensitivity':sensitivity,'risk_multiplier':risk_multiplier}
        broker_rows=[b for b in visible(bundle.get('broker',[]),as_of) if audit(b)]
        if not broker_rows:
            return reject('Historical broker availability/cost evidence missing')
        broker=broker_rows[-1]
        if not broker.get('tradable') or (side=='SHORT' and not broker.get('shortable')):
            return reject('Instrument unavailable for proposed direction')
        if (utc(as_of)-utc(broker['available_at'])).days>4:
            return reject('Broker availability/cost evidence stale')
        roundtrip=number(broker,'roundtrip_cost_bps')
        annual=number(broker,'annual_financing_rate')
        if roundtrip<0 or annual<0:
            return reject('Invalid cost assumptions')
        cost=entry*(roundtrip/10000+annual*10/365)
        reward=abs(target-entry)
        if (side=='BUY' and target<=entry) or (side=='SHORT' and target>=entry) or (reward-cost)/(risk+cost)<1.5:
            return reject('Less than 1.5:1 planned reward/risk after estimated ten-day costs')
        budget=equity*(.0025 if drawdown>=.08 else .005)*risk_multiplier
        step=number(broker,'size_increment'); minimum=number(broker,'minimum_size')
        if step<=0 or minimum<=0:
            return reject('Invalid broker size rules')
        units=floor(min(budget/(risk+cost),equity*.15/entry)/step)*step
        if units<minimum:
            return reject('Risk-sized position below broker minimum')
        result.update(decision='CANDIDATE',action=side,setup=setup,entry=entry,stop=stop,target=target,units=round(units,8),
                      planned_stop_risk=units*risk,estimated_cost=units*cost,reward_risk_after_costs=(reward-cost)/(risk+cost),
                      broker_terms=broker,execution='RESEARCH_ONLY',expires_at=(utc(as_of)+timedelta(hours=18)).isoformat())
        result['warnings'] += ['Daily-bar entry confirmation; intraday retest and fill must be checked separately',
                               'Position is not a guaranteed loss limit; gaps can exceed stop risk']
        return result
    except (KeyError,ValueError,TypeError,ZeroDivisionError,OverflowError) as exc:
        return reject('Data validation: '+str(exc))
