import copy
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from examples.build_fixture import make_institutional_bundle
from investor.recommendations import utc
from investor.institutional import expectations, portfolio_check, institutional_decision
from investor.pipeline import evaluate
from investor.validation import audit_bundles, save_audit




class InstitutionalTests(unittest.TestCase):
    def test_long_short_gates_and_report(self):
        from investor.pipeline import card_from_decision
        for side in ('BUY','SHORT'):
            b=make_institutional_bundle(side); r=institutional_decision(b)
            self.assertEqual(r['decision'],'CANDIDATE',r)
            card=card_from_decision(r,b)
            self.assertTrue(card['research_only'])
            self.assertIn('expectations',card['evidence'])
            self.assertIn('portfolio_risk',card['evidence'])
    def test_future_consensus_cannot_change_result(self):
        b=make_institutional_bundle();original=expectations(b,'BUY')
        row=copy.deepcopy(b['consensus'][-1]);row.update(mean=1,available_at='2030-01-01T00:00:00Z',recorded_at='2030-01-01T00:00:00Z')
        b['consensus'].append(row)
        self.assertEqual(original,expectations(b,'BUY'))
    def test_post_release_consensus_cannot_replace_pre_release(self):
        b=make_institutional_bundle(); b['consensus'][-1]['available_at']=b['guidance'][-1]['release_at']
        with self.assertRaisesRegex(ValueError,'Pre-announcement'):expectations(b,'BUY')
    def test_same_period_and_basis_required(self):
        for field in ('basis','fiscal_period','currency'):
            b=make_institutional_bundle()
            for row in b['consensus']:row[field]='OTHER'
            self.assertEqual(institutional_decision(b)['decision'],'NO_TRADE')
    def test_bad_revisions_block_even_when_guidance_beats(self):
        b=make_institutional_bundle()
        for r in b['consensus']:
            if r['metric']=='eps' and utc(r['available_at']).date()==utc(b['as_of']).date():r['mean']=1
        self.assertEqual(institutional_decision(b)['decision'],'NO_TRADE')
    def test_missing_stale_and_nonfinite_inputs_fail_closed(self):
        for key in ('portfolio','classification','consensus'):
            b=make_institutional_bundle();del b[key]
            self.assertEqual(institutional_decision(b)['decision'],'NO_TRADE')
        b=make_institutional_bundle();b['portfolio']['available_at']='2020-01-01T00:00:00Z'
        self.assertEqual(institutional_decision(b)['decision'],'NO_TRADE')
        b=make_institutional_bundle();b['classification']['beta']=float('nan')
        self.assertEqual(institutional_decision(b)['decision'],'NO_TRADE')
    def test_short_signed_exposure_and_squeeze_loss(self):
        b=make_institutional_bundle('SHORT');r=institutional_decision(b);risk=r['metrics']['portfolio']
        self.assertLess(risk['net_exposure'],0)
        self.assertGreater(risk['scenario_returns']['market_down_10pct'],0)
        self.assertLess(risk['scenario_returns']['market_up_10pct'],0)
        self.assertAlmostEqual(risk['scenario_returns']['adverse_stock_gaps'],-.30*risk['gross_exposure'])
    def test_sector_concentration_and_duplicate_position_block(self):
        b=make_institutional_bundle();p=dict(symbol='OTHER',side='BUY',units=20,mark_usd=100,stop_usd=95,sector='Technology',theme='Software',beta=1)
        b['portfolio']['positions']=[p]
        r=institutional_decision(b)
        self.assertEqual(r['decision'],'NO_TRADE')
        self.assertIn('Sector concentration above 30%',r['reasons'])
        p['symbol']=b['symbol']
        self.assertIn('pyramiding',institutional_decision(b)['reasons'][0])
    def test_high_water_drawdown_blocks(self):
        b=make_institutional_bundle();b['portfolio']['equity_usd']=8500
        self.assertEqual(institutional_decision(b)['decision'],'NO_TRADE')
    def test_audit_never_claims_validation(self):
        b=make_institutional_bundle();r=audit_bundles([b])
        self.assertEqual(r['label'],'SYNTHETIC SOFTWARE CHECK')
        self.assertFalse(r['ready_for_live_trading'])
        self.assertTrue(audit_bundles([b,b])['issues'])
        b['sample']=False
        self.assertEqual(audit_bundles([b])['label'],'UNVALIDATED RESEARCH INPUTS')
    def test_pipeline_audit_and_registry_reproducible(self):
        b=make_institutional_bundle()
        with tempfile.TemporaryDirectory() as d:
            result=evaluate([b],d,'institutional')
            self.assertEqual(result['candidates'],1)
            first=save_audit([b],d);second=save_audit([b],d)
            self.assertEqual(first['input_sha256'],second['input_sha256'])
            self.assertEqual(first['code_sha256'],second['code_sha256'])
            self.assertEqual(len((Path(d)/'experiments.jsonl').read_text().splitlines()),3)

if __name__=='__main__':unittest.main()
