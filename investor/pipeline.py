"""Evaluate audited historical bundles; export signal CSV, cards and diagnostics."""
import csv
import json
from pathlib import Path
from .strategy import decide, VARIANTS, visible, audit
from .recommendations import utc


def card_from_decision(result, bundle):
    """Explanation adapter. Always research-only even with verified inputs."""
    now=result['as_of']; metrics=result['metrics']; tech=metrics.get('technicals',{})
    chosen=lambda key: next(iter(reversed([r for r in visible(bundle.get(key,[]),now) if audit(r)])),{})
    def ev(text, source_record):
        return {'summary':text,'source':source_record.get('source','Unavailable'),
                'published_at':source_record.get('available_at',now), 'verified':audit(source_record)}
    price_source={'source':bundle.get('price_source','Supplied audited OHLCV bundle'), 'available_at':tech.get('available_at',now),
                  'point_in_time_verified':bool(bundle.get('price_history_verified'))}
    quality=chosen('quality'); options=metrics.get('options'); options_text='Options disabled for baseline comparison.'
    if options:
        summaries=[]
        for bucket,data in options['buckets'].items():
            if bucket != '8_30':
                continue
            flips=[round(x,2) for x in data['gamma_scenarios']['calls_positive_puts_negative']['flip_levels']]
            pain={e:p['strikes'] for e,p in data['max_pain_by_expiry'].items()}
            summaries.append(f"{bucket} DTE: call concentration {data['call_wall']}; put concentration {data['put_wall']}; scenario flip(s) {flips or 'none in range'}; max-pain strikes {pain}.")
        options_text=' '.join(summaries)+' Dealer signs are assumptions; levels are not guaranteed barriers.'
    evidence={
        'revenue_growth_yoy':ev('Latest four YoY revenue growth rates: '+', '.join(f'{x:.1%}' for x in metrics.get('revenue_growth_yoy',[])),chosen('revenue')),
        'guidance_change':ev('Comparable revenue guidance change: '+('withdrawn' if metrics.get('guidance_withdrawn') else (f"{metrics['guidance_change']:+.1%}" if metrics.get('guidance_change') is not None else 'unavailable')),chosen('guidance')),
        'profitability_cash_debt':ev(f"FCF TTM {quality.get('free_cash_flow_ttm',0):,.0f}; cash runway {quality.get('cash_runway_months','N/A')} months; net debt/revenue {quality.get('net_debt_to_revenue','N/A')}; operating-margin change {quality.get('operating_margin_change_pp','N/A')} pp.",quality),
        'valuation':ev(f"EV/sales relative to peer median: {quality.get('ev_sales_to_peer_median','N/A')}x.",quality),
        'market_sector_trend':ev(f"Strategy {result['variant']}; 20-session stock-minus-sector return {metrics.get('relative_strength_20d',0):+.1%}. Decision reasons: "+'; '.join(result['reasons']),price_source),
        'cpi_rate_sensitivity':ev((f"Core CPI surprise {metrics['macro']['core_surprise_pp']:+.2f} pp; 2-year yield change {metrics['macro']['yield_change_bps']:+.1f} bps; rate sensitivity {metrics['macro']['sensitivity']}; position-risk multiplier {metrics['macro']['risk_multiplier']:g}." if 'macro' in metrics else 'CPI overlay not applied in this research variant.'),chosen('macro')),
        'price_performance':ev('Returns by sessions: '+', '.join(f'{n}: {v:.1%}' for n,v in tech.get('returns',{}).items())+f"; ATR14 {tech.get('atr14',0):.2f}; relative volume {tech.get('relative_volume',0):.2f}x; daily anchored VWAP {tech.get('anchored_vwap',0):.2f}.",price_source),
        'catalysts_risks':ev('Next earnings: '+chosen('events').get('next_earnings_at','Unknown')+'. '+ '; '.join(result.get('warnings',[])),chosen('events')),
        'broker_costs_availability':ev(f"Round-trip spread/slippage estimate {chosen('broker').get('roundtrip_cost_bps','N/A')} bps; annual financing {chosen('broker').get('annual_financing_rate',0):.1%}; minimum size {chosen('broker').get('minimum_size','N/A')}; shortable {chosen('broker').get('shortable','N/A')}.",chosen('broker')),
        'options_positioning':ev(options_text,chosen('options'))}
    return {'symbol':result['symbol'],'action':result.get('action','NO_TRADE') if result['decision']=='CANDIDATE' else 'NO_TRADE',
            'thesis':result['decision']+' | '+'; '.join(result['reasons']),
            'created_at':now,'quote_at':tech.get('available_at',now),'expires_at':result.get('expires_at',now),
            'entry':result.get('entry',0),'stop':result.get('stop',0),'target':result.get('target',0),
            'units':result.get('units',0),'evidence':evidence,'sample':result['sample'],
            'broker_verified':audit(chosen('broker')),'research_only':True,
            'research_decision':result['decision'],'strategy_version':result['strategy_version']}


def evaluate(bundles, directory, variant='macro'):
    if not isinstance(bundles,list) or not bundles:
        raise ValueError('Expected nonempty list of bundles')
    directory=Path(directory); directory.mkdir(parents=True,exist_ok=True)
    decisions=[]; cards=[]; signals=[]; seen=set()
    for bundle in sorted(bundles,key=lambda b:(utc(b['as_of']),b['symbol'])):
        key=(bundle['symbol'],bundle['as_of'])
        if key in seen:
            raise ValueError('Duplicate decision snapshot')
        seen.add(key)
        result=decide(bundle,variant)
        decisions.append(result); cards.append(card_from_decision(result,bundle))
        if result['decision']=='CANDIDATE':
            signals.append({'date':result['metrics']['technicals']['last_date'],'symbol':result['symbol'],
                'side':result['action'],'known_at':result['as_of'],'verified':'true',
                'planned_entry':result['entry'],'stop':result['stop'],'target':result['target'],
                'risk_multiplier':result['metrics'].get('macro',{}).get('risk_multiplier',1.),
                'sample':'true' if result['sample'] else 'false',
                'size_increment':result['broker_terms']['size_increment'],'minimum_size':result['broker_terms']['minimum_size'],
                'annual_financing_rate':result['broker_terms']['annual_financing_rate'],
                'cost_bps_per_side':float(result['broker_terms']['roundtrip_cost_bps'])/2,
                'max_units':result['units']})
    (directory/'decisions.json').write_text(json.dumps(decisions,indent=2,allow_nan=False))
    (directory/'cards.json').write_text(json.dumps(cards,indent=2,allow_nan=False))
    with (directory/'signals.csv').open('w') as f:
        fields=['date','symbol','side','known_at','verified','planned_entry','stop','target','risk_multiplier','sample','size_increment','minimum_size','annual_financing_rate','cost_bps_per_side','max_units']
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(signals)
    return {'variant':variant,'evaluated':len(decisions),'candidates':len(signals),
            'blocked':len(decisions)-len(signals),'synthetic':any(b.get('sample') for b in bundles)}


def compare(bundles, bars_path, directory):
    from .backtest import run
    directory=Path(directory); directory.mkdir(parents=True,exist_ok=True)
    summaries=[]
    for variant in VARIANTS:
        folder=directory/variant
        selection=evaluate(bundles,folder,variant)
        simulation=run(bars_path,folder/'signals.csv')
        if selection['synthetic']:
            simulation['label']='SYNTHETIC SOFTWARE CHECK'
        (folder/'backtest.json').write_text(json.dumps(simulation,indent=2))
        summaries.append({**selection,**{k:v for k,v in simulation.items() if k not in ('trades','equity_curve')}})
    (directory/'comparison.json').write_text(json.dumps(summaries,indent=2))
    return summaries
