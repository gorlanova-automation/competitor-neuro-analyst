"""Product release regression evidence; preserves stage 4 validation snapshot."""
import hashlib
import io
import json
import sys
import unittest
from datetime import datetime,timezone
from pathlib import Path

root=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(root),str(root/'stage_3/code')]
suite=unittest.defaultTestLoader.discover(str(root/'stage_3/code'),pattern='test_*.py')
for module in ['stage_4.test_workflow','stage_4.test_semantic','stage_4.test_review','app.test_api','app.test_workflow_api','app.test_product','app.test_search','app.test_ai_analysis']:
    suite.addTests(unittest.defaultTestLoader.loadTestsFromName(module))
stream=io.StringIO();result=unittest.TextTestRunner(verbosity=2,stream=stream).run(suite)
release=root/'releases/stage_3_20261027';manifest=json.loads((release/'manifest.json').read_text(encoding='utf-8'))
hashes=[{'file':r['file'],'matches':hashlib.sha256((release/r['file']).read_bytes()).hexdigest()==r['sha256']} for r in manifest['files']]
value={'checked_at':datetime.now(timezone.utc).isoformat(),'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
       'successful':result.wasSuccessful() and all(r['matches'] for r in hashes),'original_stage_3':hashes,'test_output':stream.getvalue(),
       'limits':'Technical tests use explicit saved text and mocked search errors; live browser research is recorded separately. No semantic accuracy percentage measured.'}
out=root/'stage_6/results/validation.json';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
print(stream.getvalue());print('Saved',out)
if not value['successful']:raise SystemExit(1)
