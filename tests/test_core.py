import csv
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from investor.approvals import create, decide, get
from investor.recommendations import EVIDENCE, blockers
from investor.backtest import run


def card():
    now=datetime.now(timezone.utc)
    return dict(symbol='TEST', action='BUY', thesis='Test only', created_at=now.isoformat(),
        quote_at=now.isoformat(), expires_at=(now+timedelta(minutes=15)).isoformat(),
        entry=100,stop=95,target=110,units=5,broker_verified=True,
        evidence={k:dict(verified=True,summary='Test evidence',source='fixture',published_at=now.isoformat()) for k in EVIDENCE})

class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.old=os.environ.get('APPROVAL_DB')
        os.environ['APPROVAL_DB']=self.temp.name+'/test.sqlite'
    def tearDown(self):
        if self.old is None: os.environ.pop('APPROVAL_DB',None)
        else: os.environ['APPROVAL_DB']=self.old
        self.temp.cleanup()
    def test_one_use_and_get_is_read_only(self):
        token=create(card())
        self.assertEqual(get(token)[1],'PENDING')
        self.assertEqual(get(token)[1],'PENDING')
        self.assertEqual(decide(token,'ACCEPT'),'ACCEPTED_RESEARCH_ONLY')
        with self.assertRaises(ValueError): decide(token,'ACCEPT')
    def test_unknown_missing_expired_and_sample_blocked(self):
        with self.assertRaises(ValueError): decide('not-a-token','ACCEPT')
        for change in ({'sample':True},{'evidence':{}},{'expires_at':'2000-01-01T00:00:00Z'},{'units':float('nan')},{'broker_verified':False}):
            c=card();c.update(change)
            token=create(c)
            with self.assertRaises(ValueError): decide(token,'ACCEPT')
            self.assertEqual(decide(token,'REJECT'),'REJECTED')
    def test_next_day_entry_and_gap_stop(self):
        root=Path(self.temp.name); bars=root/'bars.csv'; signals=root/'signals.csv'
        start=datetime(2020,1,1)
        dates=[(start+timedelta(days=i)).date().isoformat() for i in range(53)]
        with bars.open('w') as f:
            w=csv.writer(f);w.writerow(['date','symbol','open','high','low','close'])
            for i,d in enumerate(dates):
                spy=100+i
                w.writerow([d,'SPY',spy,spy+1,spy-1,spy])
                px=80 if i>=51 else 100
                w.writerow([d,'TEST',px,px+1,px-1,px])
        with signals.open('w') as f:
            w=csv.writer(f);w.writerow(['date','symbol','side','known_at','verified'])
            w.writerow([dates[49],'TEST','BUY',dates[49],'true'])
        result=run(bars,signals)
        self.assertEqual(result['trades'][0]['opened'],dates[50])
        self.assertEqual(result['trades'][0]['closed'],dates[51])
        self.assertEqual(result['trades'][0]['exit_price'],80)
        self.assertLess(result['trades'][0]['pnl_after_costs'],-150)
        signals.write_text('date,symbol,side,known_at,verified\n'+f'{dates[49]},TEST,BUY,{dates[50]},true\n')
        with self.assertRaises(ValueError):run(bars,signals)

if __name__=='__main__':unittest.main()
