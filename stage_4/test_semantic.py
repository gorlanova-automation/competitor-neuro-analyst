import json
import tempfile
import unittest
from pathlib import Path
from stage_4.semantic import analyze,validate
from stage_4.workflow import WorkflowError,digest


class SemanticTests(unittest.TestCase):
    def setUp(self):
        self.text='Компания предлагает услуги релокации и оформление документов.'
        self.source={'url':'https://example.org/','status':'ok','text':self.text,'sha256_text':digest(self.text),'collected_at':'2026-11-07','method':'test_fixture'}
        self.value={'findings':[{'source_id':'s0','category':'assortment','summary':'Компания заявляет сопровождение релокации.','quote':self.text}],
                    'hypotheses':[{'action':'Проверить понятность описания сопровождения.','evidence_indexes':[0]}],'missing_evidence':['Визуал не получен.']}

    def test_one_call_persists_usage_without_key_and_marks_test_transport(self):
        calls=[]
        def transport(body):
            calls.append(body)
            return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(self.value)}}],'usage':{'total_tokens':300}}
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)/'experiment'
            result=analyze([{'url':'https://example.org/','role':'own','sources':[self.source]}],{},'test-key-do-not-save',out,transport=transport)
            self.assertEqual(len(calls),1);self.assertEqual(result['usage']['total_tokens'],300)
            self.assertEqual(result['new_llm_calls'],0)
            for path in out.glob('*.json'):self.assertNotIn('test-key-do-not-save',path.read_text(encoding='utf-8'))

    def test_invented_quote_unknown_source_and_bool_index_rejected(self):
        for mutate in ('quote','source_id','index'):
            value=json.loads(json.dumps(self.value))
            if mutate=='index':value['hypotheses'][0]['evidence_indexes']=[True]
            else:value['findings'][0][mutate]='invented text'
            with self.assertRaises(WorkflowError):validate(value,[{'source_id':'s0','text':self.text}])

    def test_truncation_is_quarantined_without_retry(self):
        calls=[]
        def transport(body):calls.append(body);return {'choices':[{'finish_reason':'length'}]}
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)/'experiment'
            with self.assertRaises(WorkflowError):analyze([{'url':'https://example.org/','role':'own','sources':[self.source]}],{},'test-key',out,transport=transport)
            self.assertEqual(len(calls),1);self.assertTrue((out/'failure.json').is_file())
            self.assertFalse((out/'analysis.json').exists())


if __name__=='__main__':unittest.main()
