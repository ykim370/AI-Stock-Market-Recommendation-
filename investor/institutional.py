"""Conservative research gates; thresholds are hypotheses, not calibrated forecasts."""
from datetime import timedelta
from .recommendations import utc
from .strategy import audit, visible, number, decide


def expectations(bundle, side):
    now=utc(bundle['as_of'])
    guides=[r for r in visible(bundle['guidance'],bundle['as_of']) if audit(r)]
    guide=guides[-1]
    if guide.get('status')=='withdrawn':
        raise ValueError('Withdrawn guidance needs a separately validated expectations model')
    release=utc(guide['release_at'])
    if release>utc(guide['available_at']):
        raise ValueError('Guidance availability precedes release')
    rows=[r for r in visible(bundle['consensus'],bundle['as_of']) if audit(r)]
    def comparable(r, metric):
        return all(r.get(k)==guide.get(k) and r.get(k) for k in ('fiscal_period','currency','basis')) and r.get('metric')==metric
    def valid(r):
        recorded=utc(r['recorded_at']); available=utc(r['available_at'])
        if recorded>available or number(r,'analyst_count')<3 or not r.get('provider'):
            raise ValueError('Invalid consensus provenance or insufficient analyst coverage')
        return r
    pre=[valid(r) for r in rows if comparable(r,'revenue') and utc(r['available_at'])<release and release-utc(r['recorded_at'])<=timedelta(days=7)]
    if not pre:
        raise ValueError('Pre-announcement comparable revenue consensus missing/stale')
    pre=pre[-1]; estimate=number(pre,'mean')
    if estimate<=0:
        raise ValueError('Nonpositive revenue consensus')
    surprise=((number(guide,'low')+number(guide,'high'))/2)/estimate-1
    revisions={}; sources=[guide,pre]
    for metric in ('revenue','eps'):
        eligible=[valid(r) for r in rows if comparable(r,metric) and r.get('provider')==pre['provider']]
        if not eligible:
            raise ValueError('Missing '+metric+' consensus')
        current=eligible[-1]
        if now-utc(current['recorded_at'])>timedelta(days=7):
            raise ValueError('Stale current '+metric+' consensus')
        for days in (30,90):
            anchor=now-timedelta(days=days)
            old=[r for r in eligible if utc(r['available_at'])<=anchor and anchor-utc(r['recorded_at'])<=timedelta(days=7)]
            if not old:
                raise ValueError(f'Missing {days}-day {metric} consensus history')
            old=old[-1]; base=number(old,'mean')
            if base==0:
                raise ValueError('Zero consensus base; relative revision undefined')
            change=(number(current,'mean')-base)/abs(base)
            revisions[f'{metric}_{days}d']=change
            sources.extend([old,current])
    direction=1 if side=='BUY' else -1
    passed=direction*surprise>=.02-1e-9 and all(direction*v>0 for v in revisions.values())
    return {'passed':passed,'guidance_surprise':surprise,'revisions':revisions,
            'sources':[{'source':r['source'],'available_at':r['available_at']} for r in sources],
            'limitation':'Aggregate revisions can reflect analyst coverage changes; no analyst-level breadth claim.'}


def portfolio_check(account, candidate, classification, as_of):
    now=utc(as_of)
    if not audit(account) or not timedelta(0)<=now-utc(account['available_at'])<=timedelta(days=1):
        raise ValueError('Audited portfolio snapshot missing, future or stale')
    equity=number(account,'equity_usd'); peak=number(account,'peak_equity_usd')
    if equity<=0 or peak<equity:
        raise ValueError('Invalid account equity/high-water mark')
    if not audit(classification) or utc(classification['available_at'])>now:
        raise ValueError('Audited dated sector/theme/beta classification required')
    if now-utc(classification['available_at'])>timedelta(days=90):
        raise ValueError('Stale classification/beta')
    positions=list(account['positions'])
    if any(p['symbol']==candidate['symbol'] for p in positions):
        raise ValueError('Existing symbol position: automatic pyramiding disabled')
    positions.append(dict(symbol=candidate['symbol'],side=candidate['action'],
        units=candidate['units'],mark_usd=candidate['entry'],stop_usd=candidate['stop'],
        sector=classification['sector'],theme=classification['theme'],beta=classification['beta']))
    gross=net=stop_risk=beta_exposure=0.; sectors={}; themes={}; exposures=[]
    for p in positions:
        side=p['side']; sign=1 if side=='BUY' else -1 if side=='SHORT' else 0
        units=number(p,'units'); mark=number(p,'mark_usd'); stop=number(p,'stop_usd'); beta=number(p,'beta')
        if not sign or units<=0 or min(mark,stop)<=0 or not p['sector'] or not p['theme']:
            raise ValueError('Invalid position or missing classification')
        exposure=units*mark/equity
        gross+=exposure; net+=sign*exposure; beta_exposure+=sign*exposure*beta
        # Existing trailing stops beyond the mark have zero remaining stop loss.
        stop_risk+=max(sign*(mark-stop),0)*units/equity
        sectors[p['sector']]=sectors.get(p['sector'],0)+exposure
        themes[p['theme']]=themes.get(p['theme'],0)+exposure
        exposures.append((sign,exposure,beta))
    # Market scenarios permit hedge offsets; idiosyncratic stress does not.
    scenarios={'market_down_10pct':sum(s*e*b*(-.10) for s,e,b in exposures),
               'market_up_10pct':sum(s*e*b*.10 for s,e,b in exposures),
               'adverse_stock_gaps':-sum(e*(.30 if s<0 else .15) for s,e,b in exposures)}
    breaches=[]
    for condition,label in [(gross>.60+1e-9,'Gross exposure above 60%'),
        (abs(beta_exposure)>.60+1e-9,'Absolute beta exposure above 60%'),
        (max(sectors.values())>.30+1e-9,'Sector concentration above 30%'),
        (max(themes.values())>.30+1e-9,'Theme concentration above 30%'),
        (stop_risk>.03+1e-9,'Combined remaining stop risk above 3%'),
        (min(scenarios.values())<-.10-1e-9,'Scenario loss above 10%'),
        (1-equity/peak>=.12,'Drawdown at or above 12%'),
        (len(positions)>5,'More than five positions')]:
        if condition:breaches.append(label)
    return dict(passed=not breaches,breaches=breaches,gross_exposure=gross,net_exposure=net,
        beta_exposure=beta_exposure,stop_risk=stop_risk,sector_exposure=sectors,
        theme_exposure=themes,scenario_returns=scenarios,
        limitation='Fixed shocks are stress assumptions, not worst-case bounds; 15% drawdown cannot be guaranteed.')


def institutional_decision(bundle):
    # Reuse the tested macro strategy. Its existing ablation variants stay unchanged.
    account=bundle.get('portfolio',{})
    try:
        equity=number(account,'equity_usd'); peak=number(account,'peak_equity_usd')
        if equity<=0 or peak<equity:raise ValueError('Invalid account equity/high-water mark')
        result=decide(bundle,'macro',equity=equity,drawdown=1-equity/peak)
        result['variant']='institutional'; result['strategy_version']+='-institutional-v1'
        if result['decision']!='CANDIDATE':return result
        exp=expectations(bundle,result['action']); result['metrics']['expectations']=exp
        risk=portfolio_check(account,result,bundle['classification'],bundle['as_of'])
        result['metrics']['portfolio']=risk
        if not exp['passed'] or not risk['passed']:
            result['decision']='NO_TRADE'
            result['reasons']+= ([] if exp['passed'] else ['Guidance surprise or 30/90-day revisions do not support direction'])+risk['breaches']
        else:
            result['reasons']+=['Pre-release consensus and 30/90-day revisions support direction','Portfolio exposure and stress gates pass']
        result['warnings'] += [exp['limitation'],risk['limitation']]
        return result
    except (KeyError,ValueError,TypeError,ZeroDivisionError,OverflowError) as exc:
        return dict(symbol=bundle['symbol'],as_of=bundle['as_of'],strategy_version='growth-options-v1-institutional-v1',variant='institutional',decision='NO_TRADE',reasons=['Institutional data validation: '+str(exc)],warnings=[],metrics={},sample=bool(bundle.get('sample',False)))
