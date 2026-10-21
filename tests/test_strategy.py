import copy
import tempfile
import unittest
from math import isclose
from pathlib import Path
from investor.options import bs_gamma,analyse,crossing_levels,max_pain
from investor.strategy import decide,guidance_change,revenue_growth
from investor.pipeline import evaluate,card_from_decision
from investor.recommendations import blockers
from investor.indicators import features
from examples.build_fixture import make_bundle,generate

class OptionsTests(unittest.TestCase):
    def test_known_gamma_and_units(self):
        self.assertAlmostEqual(bs_gamma(100,100,1,.2),.019847627,places=7)
        rows=[dict(type='call',expiration='2025-01-20',strike=110,open_interest=10,multiplier=100,gamma=.02,implied_volatility=.3)]
        result=analyse(rows,100,'2025-01-01')['buckets']['8_30']
        self.assertEqual(result['call_wall'],110)
        self.assertEqual(result['call_concentrations'][0][1],2000)
        self.assertIsNone(result['put_wall'])
        self.assertEqual(result['gamma_scenarios']['dealers_short_both']['flip_levels'],[])
    def test_max_pain_ties_and_expiry_separation(self):
        rows=[dict(type='call',strike=90,expiration='A',open_interest=10,multiplier=100),dict(type='put',strike=110,expiration='A',open_interest=10,multiplier=100),dict(type='call',strike=200,expiration='B',open_interest=1,multiplier=100)]
        self.assertEqual(max_pain(rows)['A']['strikes'],[90,110])
        self.assertEqual(max_pain(rows)['B']['strikes'],[200])
    def test_multiple_and_absent_flips(self):
        self.assertEqual(crossing_levels([(1,1),(2,-1),(3,1)]),[1.5,2.5])
        self.assertEqual(crossing_levels([(1,0),(2,0)]),[])
    def test_invalid_contracts_excluded(self):
        with self.assertRaises(ValueError):analyse([{'gamma':float('nan')}],100,'2025-01-01')

class StrategyTests(unittest.TestCase):
    def test_long_and_short_candidates(self):
        for side in ('BUY','SHORT'):
            b=make_bundle(side)
            for variant in ('baseline','options','confirmation','macro'):
                r=decide(b,variant)
                self.assertEqual(r['decision'],'CANDIDATE',r)
                self.assertEqual(r['action'],side)
                self.assertLessEqual(r['planned_stop_risk']+r['estimated_cost'],50)
                self.assertLessEqual(r['entry']*r['units'],1500)
    def test_future_prices_cannot_change_past_features(self):
        b=make_bundle();original=features(b['bars']['stock'],b['as_of'])
        b['bars']['stock'][-1]['close']=1_000_000
        self.assertEqual(original,features(b['bars']['stock'],b['as_of']))
    def test_future_restatement_cannot_change_past_growth(self):
        b=make_bundle();old=revenue_growth(b['revenue'],b['as_of'])[0]
        revised=copy.deepcopy(b['revenue'][-1]);revised.update(revenue=1,available_at='2030-01-01T00:00:00Z')
        b['revenue'].append(revised)
        self.assertEqual(old,revenue_growth(b['revenue'],b['as_of'])[0])
    def test_guidance_requires_same_period_and_basis(self):
        b=make_bundle();b['guidance'][-1]['fiscal_period']='FY2026'
        self.assertEqual(decide(b)['decision'],'NO_TRADE')
        b=make_bundle();b['guidance'][-1]['basis']='organic'
        self.assertEqual(decide(b)['decision'],'NO_TRADE')
    def test_missing_evidence_is_not_bullish(self):
        for key in ('guidance','quality','broker','options','macro','events'):
            b=make_bundle();b[key]=[]
            self.assertEqual(decide(b)['decision'],'NO_TRADE',key)
    def test_missing_prices_or_future_macro_consensus(self):
        b=make_bundle();b['bars']['sector']=[]
        self.assertEqual(decide(b)['decision'],'NO_TRADE')
        b=make_bundle();b['macro'][0]['consensus_recorded_at']='2030-01-01T00:00:00Z'
        self.assertEqual(decide(b)['decision'],'NO_TRADE')
    def test_wall_can_remove_reward_and_cpi_blocks_sensitive_long(self):
        b=make_bundle();b['options'][0]['contracts'][0]['strike']=b['bars']['stock'][79]['close']+.1
        self.assertEqual(decide(b)['decision'],'NO_TRADE')
        b=make_bundle();b['quality'][0]['rate_sensitivity']='high';b['macro'][0].update(core_actual_mom_pct=.4,treasury_2y_change_bps=10)
        self.assertEqual(decide(b)['decision'],'NO_TRADE')
    def test_unverified_prices_block_selection(self):
        b=make_bundle();b['price_history_verified']=False
        self.assertEqual(decide(b)['decision'],'NO_TRADE')

    def test_drawdown_and_expiry(self):
        self.assertEqual(decide(make_bundle(),drawdown=.15)['decision'],'NO_TRADE')
        b=make_bundle();b['options'][0]['oi_date']='2020-01-01'
        self.assertEqual(decide(b)['decision'],'NO_TRADE')
    def test_research_cards_can_never_be_approved(self):
        b=make_bundle();r=decide(b)
        card=card_from_decision(r,b)
        self.assertTrue(any('Research-only' in x for x in blockers(card)))
    def test_complete_comparison_runs(self):
        import json
        from investor.pipeline import compare
        with tempfile.TemporaryDirectory() as d:
            generate(d)
            summaries=compare(json.loads((Path(d)/'bundles.json').read_text()),Path(d)/'bars.csv',Path(d)/'comparison')
            self.assertEqual(len(summaries),4)
            self.assertTrue(all(x['candidates']>0 for x in summaries))
            self.assertTrue(all(x['label']=='SYNTHETIC SOFTWARE CHECK' for x in summaries))
            self.assertTrue(all(len(json.loads((Path(d)/'comparison'/v/'backtest.json').read_text())['trades'])>0 for v in ('baseline','options','confirmation','macro')))

if __name__=='__main__':unittest.main()
