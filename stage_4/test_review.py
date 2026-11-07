import copy
import unittest
from stage_4.review import apply_review,audit_semantics,numeric_tokens
from stage_4.workflow import digest,WorkflowError


class ReviewTests(unittest.TestCase):
    def setUp(self):
        text='Компания предлагает бесплатную консультацию на 30 минут.'
        self.source={'status':'ok','text':text,'sha256_text':digest(text)}
        self.result={'run_id':'original-run','semantic':{'findings':[
            {'source_id':'s0','category':'pricing','summary':'Консультация 30 минут и услуга за 150 EUR.','quote':text}],
            'hypotheses':[{'action':'Проверить описание консультации.','evidence_indexes':[0]}],
            'sources':[{'source_id':'s0','company_url':'https://example.org/','sha256_text':digest(text)}]}}
        self.companies=[{'sources':[self.source]}]
        self.review={'source_run_id':'original-run','report_sha256':'hash','reviewer':'Assistant QA, not user acceptance',
            'findings':{'0':{'decision':'revise','summary':'Компания заявляет бесплатную консультацию на 30 минут.'}},
            'hypotheses':{'0':{'decision':'accept'}}}

    def test_numeric_overclaim_is_flagged_and_must_be_corrected(self):
        audit=audit_semantics(self.result['semantic'])
        self.assertEqual(audit['finding_flags'][0]['values'],['150'])
        invalid=copy.deepcopy(self.review);invalid['findings']['0']={'decision':'accept'}
        with self.assertRaises(WorkflowError):apply_review(self.result,invalid,'hash',self.companies)
        final=apply_review(self.result,self.review,'hash',self.companies)
        self.assertEqual(final['semantic']['accepted_findings'],1)
        self.assertEqual(final['semantic']['status'],'human_review_recorded')
        self.assertIn('150',self.result['semantic']['findings'][0]['summary'])
        self.assertNotIn('150',final['semantic']['findings'][0]['summary'])

    def test_review_is_bound_to_report_and_rejected_finding_cannot_support_hypothesis(self):
        for field,value in [('source_run_id','other'),('report_sha256','other')]:
            invalid={**self.review,field:value}
            with self.assertRaises(WorkflowError):apply_review(self.result,invalid,'hash',self.companies)
        invalid=copy.deepcopy(self.review);invalid['findings']['0']={'decision':'reject'}
        with self.assertRaises(WorkflowError):apply_review(self.result,invalid,'hash',self.companies)
        invalid['hypotheses']['0']={'decision':'reject'}
        result=apply_review(self.result,invalid,'hash',self.companies)
        self.assertEqual(result['semantic']['accepted_findings'],0)

    def test_forged_or_tampered_source_is_rejected(self):
        invalid=copy.deepcopy(self.review);invalid['findings']['0']['quote']='Invented quotation with no source.'
        with self.assertRaises(WorkflowError):apply_review(self.result,invalid,'hash',self.companies)
        companies=copy.deepcopy(self.companies);companies[0]['sources'][0]['text']='changed'
        with self.assertRaises(WorkflowError):apply_review(self.result,self.review,'hash',companies)
        self.assertEqual(numeric_tokens('1 000,50 EUR'),numeric_tokens('1000.50 EUR'))


if __name__=='__main__':unittest.main()
