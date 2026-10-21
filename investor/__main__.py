import argparse
import json
import os
from pathlib import Path

parser = argparse.ArgumentParser(description='Research-only stock recommendation tools')
sub = parser.add_subparsers(dest='command',required=True)
p = sub.add_parser('fetch'); p.add_argument('symbol')
p = sub.add_parser('report'); p.add_argument('cards'); p.add_argument('--output',default='output/pdf/recommendations.pdf'); p.add_argument('--send',action='store_true')
p = sub.add_parser('backtest'); p.add_argument('bars'); p.add_argument('signals'); p.add_argument('--output',default='output/backtest.json'); p.add_argument('--holding-days',type=int,default=5)
p = sub.add_parser('select'); p.add_argument('bundles'); p.add_argument('--variant',choices=['baseline','options','confirmation','macro'],default='macro'); p.add_argument('--output',default='output/selection')
p = sub.add_parser('compare'); p.add_argument('bundles'); p.add_argument('bars'); p.add_argument('--output',default='output/comparison')
p = sub.add_parser('options'); p.add_argument('chain'); p.add_argument('--spot',type=float,required=True); p.add_argument('--date',required=True); p.add_argument('--multiplier',type=float); p.add_argument('--output',default='output/options.json')
p = sub.add_parser('fetch-options'); p.add_argument('symbol'); p.add_argument('date')
sub.add_parser('serve')
args = parser.parse_args()
if args.command == 'fetch':
    from .data import AlphaVantage
    print(AlphaVantage().snapshot(args.symbol))
elif args.command == 'report':
    from .approvals import create
    from .reports import pdf, send_report
    cards = json.loads(Path(args.cards).read_text())
    base = os.getenv('APPROVAL_BASE_URL','http://127.0.0.1:8080').rstrip('/')
    if args.send and not base.startswith('https://'):
        parser.error('Email requires a deployed HTTPS approval URL')
    links = [base+'/?token='+create(card) for card in cards]
    destination = pdf(cards,args.output,links)
    if args.send:
        send_report(destination,links)
    print('Report created:',destination)
elif args.command == 'serve':
    from .web import serve
    serve()
elif args.command == 'backtest':
    from .backtest import run
    result = run(args.bars,args.signals,args.holding_days)
    path=Path(args.output); path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,indent=2))
    print({k:v for k,v in result.items() if k not in ('trades','equity_curve')})

elif args.command == 'select':
    from .pipeline import evaluate
    print(evaluate(json.loads(Path(args.bundles).read_text()),args.output,args.variant))
elif args.command == 'compare':
    from .pipeline import compare
    print(json.dumps(compare(json.loads(Path(args.bundles).read_text()),args.bars,args.output),indent=2))
elif args.command == 'fetch-options':
    from .data import AlphaVantage
    print(AlphaVantage().historical_options(args.symbol,args.date))
elif args.command == 'options':
    from .options import analyse
    payload=json.loads(Path(args.chain).read_text())
    raw=payload
    while isinstance(raw,dict) and 'data' in raw:
        raw=raw['data']
    if not isinstance(raw,list):
        parser.error('Expected option chain list or Alpha Vantage data wrapper')
    if args.multiplier is not None:
        raw=[{**r,'multiplier':r.get('multiplier',args.multiplier)} for r in raw]
    result=analyse(raw,args.spot,args.date)
    if args.multiplier is not None:
        result['assumptions'].append('User-supplied fallback multiplier; verify all contracts are standard before relying on values')
    path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,indent=2))
    print('Options analysis saved:',path)
