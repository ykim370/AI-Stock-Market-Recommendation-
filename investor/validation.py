"""Reproducible input audit. This does not certify predictive performance."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from .recommendations import utc
from .strategy import audit


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def audit_bundles(bundles):
    if not isinstance(bundles,list) or not bundles:raise ValueError('Nonempty bundle list required')
    required=('revenue','guidance','quality','options','macro','events','broker','consensus')
    counts={key:0 for key in required}; issues=[]; seen=set(); dates=[]
    for b in bundles:
        now=utc(b['as_of']); dates.append(now)
        key=(b['symbol'],now.isoformat())
        if key in seen:issues.append('Duplicate symbol/timestamp: '+str(key))
        seen.add(key)
        if not b.get('price_history_verified') or not b.get('price_source'):issues.append('Price provenance missing: '+str(key))
        for name in required:
            usable=[r for r in b.get(name,[]) if audit(r) and utc(r['available_at'])<=now]
            if usable:counts[name]+=1
        for name in ('portfolio','classification'):
            r=b.get(name,{})
            if not audit(r) or not r.get('available_at') or utc(r['available_at'])>now:
                issues.append(name+' provenance missing: '+str(key))
    coverage={k:v/len(bundles) for k,v in counts.items()}
    missing=[k for k,v in coverage.items() if v<1]
    if missing:issues.append('Incomplete dated evidence: '+', '.join(missing))
    synthetic=any(b.get('sample') for b in bundles)
    return {'label':'SYNTHETIC SOFTWARE CHECK' if synthetic else 'UNVALIDATED RESEARCH INPUTS',
        'bundle_count':len(bundles),'symbol_count':len({b['symbol'] for b in bundles}),
        'first_as_of':min(dates).isoformat(),'last_as_of':max(dates).isoformat(),
        'input_sha256':fingerprint(bundles),'dated_evidence_coverage':coverage,'issues':issues,
        'ready_for_live_trading':False,
        'limitations':['Source verification flags are supplied assertions, not independently verified by this audit.',
            'Coverage measures presence, not comparability, freshness, accuracy or licensing.',
            'No walk-forward or untouched holdout performance has been established.',
            'Historical universe/delistings, corporate actions and broker-specific execution still need validation.',
            'Institutional selection evaluates supplied account snapshots; it is not a dynamic portfolio backtest.']}


def save_audit(bundles, directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    report=audit_bundles(bundles)
    code={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(__file__).parent.glob('*.py'))}
    report['code_sha256']=fingerprint(code)
    report['created_at']=datetime.now(timezone.utc).isoformat()
    (directory/'validation.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    # Local append-only convention, not tamper-proof storage; no secrets/raw data.
    with (directory/'experiments.jsonl').open('a') as f:
        f.write(json.dumps({k:report[k] for k in ('created_at','input_sha256','code_sha256','label','bundle_count','symbol_count')})+'\n')
    return report
