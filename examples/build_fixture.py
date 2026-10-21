"""Generate clearly synthetic integration data. Never a performance demonstration."""
import csv
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


def make_bundle(side='BUY', index=79):
    dates=[]; d=date(2025,1,2)
    while len(dates)<90:
        if d.weekday()<5: dates.append(d.isoformat())
        d+=timedelta(days=1)
    def stamp(i):return dates[i]+'T21:00:00+00:00'
    source={'source':'SYNTHETIC TEST FIXTURE','point_in_time_verified':True}
    bars={}
    for name,start,slope in [('stock',100,.6),('market',100,.12),('sector',50,.04)]:
        rows=[]
        for i,d in enumerate(dates):
            px=start+slope*i*(1 if side=='BUY' else -1)
            if name=='stock' and i in (64,69,74,79,84):px+=2 if side=='BUY' else -2
            rows.append(dict(date=d,available_at=stamp(i),open=px-.2 if side=='BUY' else px+.2,high=px+.5,low=px-.5,close=px,volume=2_000_000 if name=='stock' and i in (64,69,74,79,84) else 1_000_000))
        bars[name]=rows
    asof=dates[index]+'T22:00:00+00:00'
    revenue=[]
    for year in (2023,2024):
        for quarter in (1,2,3,4):
            import calendar
            month=quarter*3; end=date(year,month,calendar.monthrange(year,month)[1])
            available=(end+timedelta(days=35)).isoformat()+'T21:00:00+00:00'
            revenue.append(dict(**source,available_at=available,fiscal_year=year,fiscal_quarter=quarter,period_end=end.isoformat(),currency='USD',revenue=100_000_000 if year==2023 else 125_000_000 if side=='BUY' else 90_000_000))
    guidance=[dict(**source,available_at=stamp(40+j*5),metric='revenue',fiscal_period='FY2025',currency='USD',basis='reported',low=low,high=low+20_000_000,status='active') for j,low in enumerate((500_000_000,550_000_000 if side=='BUY' else 450_000_000))]
    quality=[dict(**source,available_at=stamp(45),operating_margin_change_pp=1 if side=='BUY' else -3,free_cash_flow_ttm=10_000_000 if side=='BUY' else -10_000_000,cash_runway_months=36,net_debt_to_revenue=.2,ev_sales_to_peer_median=1.1,rate_sensitivity='medium')]
    price=bars['stock'][index]['close']
    expiry=(date.fromisoformat(dates[index])+timedelta(days=20)).isoformat()
    contracts=[dict(type=t,expiration=expiry,strike=price+offset,open_interest=1000,multiplier=100,gamma=.02,implied_volatility=.3) for t,offset in [('call',20),('put',-20)]]
    return dict(symbol='EXAMPLE',sample=True,as_of=asof,price_source='SYNTHETIC TEST FIXTURE',price_history_verified=True,bars=bars,revenue=revenue,guidance=guidance,quality=quality,
        options=[dict(**source,available_at=stamp(index),date=dates[index],oi_date=dates[index-1],spot=price,contracts=contracts)],
        macro=[dict(**source,available_at=stamp(60),consensus_recorded_at=dates[60]+'T11:00:00+00:00',release_at=dates[60]+'T12:30:00+00:00',core_actual_mom_pct=.2,core_consensus_mom_pct=.2,treasury_2y_change_bps=0)],
        events=[dict(**source,available_at=stamp(40),next_earnings_at='2025-07-01T20:00:00+00:00')],
        broker=[dict(**source,available_at=stamp(index),tradable=True,shortable=True,roundtrip_cost_bps=10,annual_financing_rate=.1,size_increment=1,minimum_size=1)])


def generate(directory='output/fixture'):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    bundles=[make_bundle(index=i) for i in (64,69,74,79,84)]
    (directory/'bundles.json').write_text(json.dumps(bundles,indent=2))
    with (directory/'bars.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=['date','symbol','open','high','low','close'])
        writer.writeheader()
        for name,symbol in [('stock','EXAMPLE'),('market','SPY')]:
            for row in bundles[0]['bars'][name]:
                writer.writerow({k:row[k] for k in ['date','open','high','low','close']}|{'symbol':symbol})
    print('Synthetic fixtures written to',directory)

if __name__=='__main__':generate()
