"""Run meaningful regressions and save actual results, never expected counts."""
import hashlib
import io
import json
import sys
import unittest
from pathlib import Path
from datetime import datetime,timezone


def validate(project_root='.',destination='stage_4/results/validation.json'):
    root=Path(project_root).resolve();sys.path.insert(0,str(root));sys.path.insert(0,str(root/'stage_3/code'))
    suite=unittest.defaultTestLoader.discover(str(root/'stage_3/code'),pattern='test_*.py')
    for module in ['stage_4.test_workflow','stage_4.test_semantic','stage_4.test_review','app.test_api','app.test_workflow_api']:
        suite.addTests(unittest.defaultTestLoader.loadTestsFromName(module))
    stream=io.StringIO();result=unittest.TextTestRunner(verbosity=2,stream=stream).run(suite)
    release=root/'releases/stage_3_20261027'
    frozen=json.loads((release/'manifest.json').read_text(encoding='utf-8'))
    hashes=[{'file':r['file'],'matches':hashlib.sha256((release/r['file']).read_bytes()).hexdigest()==r['sha256']} for r in frozen['files']]
    value={'checked_at':datetime.now(timezone.utc).isoformat(),'tests_run':result.testsRun,'failures':len(result.failures),
           'errors':len(result.errors),'successful':result.wasSuccessful() and all(r['matches'] for r in hashes),
           'original_stage_3':hashes,'test_output':stream.getvalue(),'new_llm_calls':0,
           'limits':'Structural and regression tests; not a measurement of full semantic accuracy or website coverage.'}
    out=root/destination;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    print(stream.getvalue());print('Saved:',out)
    if not value['successful']:raise SystemExit(1)
    return value


if __name__=='__main__':validate()
