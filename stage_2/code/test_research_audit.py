"""Tamper checks use a temporary copy of real saved public research."""
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
from research_audit import audit

class ResearchAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        bundle=Path(__file__).resolve().parents[1]/'Этап_2_база_и_эксперименты.zip'
        with ZipFile(bundle) as z: z.extractall(self.root)

    def test_changed_request_is_detected(self):
        path=next((self.root/'runs/20261022T111451Z_0f8116/experiments').glob('*/*_request.json'))
        request=json.loads(path.read_text(encoding='utf-8'))
        content=json.loads(request['messages'][1]['content'])
        content['text']+=' modified'
        request['messages'][1]['content']=json.dumps(content,ensure_ascii=False)
        path.write_text(json.dumps(request,ensure_ascii=False),encoding='utf-8')
        result=audit(self.root)
        self.assertFalse(result['checks_passed'])
        self.assertIn('request_corpus_or_prompt',{e['check'] for e in result['integrity_errors']})

    def test_changed_raw_source_is_detected(self):
        path=next((self.root/'runs/20261022T111451Z_0f8116/raw').glob('*.html'))
        path.write_bytes(path.read_bytes()+b' modified')
        result=audit(self.root)
        self.assertFalse(result['checks_passed'])
        self.assertIn('source_hash',{e['check'] for e in result['integrity_errors']})

if __name__=='__main__': unittest.main()
