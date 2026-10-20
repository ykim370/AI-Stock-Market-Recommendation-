import argparse
import json
import os
from pathlib import Path

parser = argparse.ArgumentParser(description='Research-only stock recommendation tools')
sub = parser.add_subparsers(dest='command',required=True)
p = sub.add_parser('fetch'); p.add_argument('symbol')
p = sub.add_parser('report'); p.add_argument('cards'); p.add_argument('--output',default='output/pdf/recommendations.pdf'); p.add_argument('--send',action='store_true')
p = sub.add_parser('backtest'); p.add_argument('bars'); p.add_argument('signals'); p.add_argument('--output',default='output/backtest.json'); p.add_argument('--holding-days',type=int,default=5)
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
