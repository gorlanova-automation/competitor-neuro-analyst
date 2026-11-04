import copy
import json
from pathlib import Path
import tempfile
import unittest
from analyst import compare, read, verify_inputs, validate_fact, run
from llm_report import validate_narration, generate

ROOT=Path(__file__).resolve().parents[1]


class AnalystTests(unittest.TestCase):
    def setUp(self):
        self.cfg=read(ROOT/'config.json')
        self.result=compare(ROOT,self.cfg)

    def test_conflict_is_retained_and_price_ranking_blocked(self):
        row=next(c for c in self.result['criteria'] if c['id']=='tax_consultation')
        own=next(c for c in row['cells'] if c['company_id']=='immigration_relocator')
        self.assertEqual(own['amounts_eur'],[170,350])
        self.assertEqual(own['status'],'conflicting_published_prices')
        self.assertEqual(row['numeric_comparison'],'blocked_unverified_scope_or_terms')

    def test_missing_competitors_not_misrepresented_as_absent_services(self):
        self.assertEqual(sum(bool(c['facts_in_demo']) for c in self.result['coverage']),6)
        self.assertEqual(len(self.result['coverage']),12)
        self.assertTrue(all(h['status']=='hypothesis_requires_owner_review' for h in self.result['recommendations']))
        subset=compare(ROOT,{**self.cfg,'competitors':['migran']})
        self.assertEqual([h['id'] for h in subset['recommendations']],['H1'])

    def test_spain_produces_no_portugal_claims(self):
        cfg={**self.cfg,'country':'Spain'}
        result=compare(ROOT,cfg)
        self.assertEqual((result['criteria'],result['evidence'],result['recommendations']),([],[],[]))

    def test_user_additions_are_not_script_discoveries_or_duplicates(self):
        companies=read(ROOT/'input/companies.json')
        self.assertEqual(len({c['id'] for c in companies}),len(companies))
        for cid in ['portugaldom','movetocascais','monolite','okno']:
            company=next(c for c in companies if c['id']==cid)
            self.assertEqual(company['added_by'],'user')
            self.assertEqual(company['discovery_method'],'user_supplied')
            self.assertTrue(any(e['company_id']==cid for e in self.result['evidence']))
        self.assertEqual(len(self.result['evidence']),30)

    def test_service_without_price_is_not_zero_or_absence(self):
        criterion=next(c for c in self.result['criteria'] if c['id']=='nif')
        cell=next(c for c in criterion['cells'] if c['company_id']=='monolite')
        self.assertEqual(cell['amounts_eur'],[])
        self.assertEqual(cell['status'],'service_mentioned_price_not_observed')
        package=next(c for c in self.result['criteria'] if c['id']=='assistance')
        self.assertEqual(next(c for c in package['cells'] if c['company_id']=='portugaldom')['amounts_eur'],[2500])
        self.assertEqual(package['numeric_comparison'],'blocked_unverified_scope_or_terms')

    def test_unconfirmed_company_is_rejected(self):
        cfg={**self.cfg,'competitors':['invented']}
        with self.assertRaises(ValueError): compare(ROOT,cfg)

    def test_forged_quote_company_and_number_are_rejected(self):
        f=copy.deepcopy(self.result['evidence'][0]); f['evidence']='FORGED'; f['company_id']='migrun'; f['amount']=999999
        chunks={c['chunk_id']:c for c in read(ROOT/'input/chunks.json')}
        sources={s['source_id']:s for s in read(ROOT/'input/sources.json')}
        errors=validate_fact(f,chunks,sources,ROOT)
        self.assertTrue({'quote_mismatch','company_mismatch','amount_not_in_quote'} <= set(errors))

    def test_unknown_llm_reference_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_narration({'hypotheses':[{'title':'x','action':'y','evidence_ids':['invented']}]},set())

    def test_actual_model_is_not_called_in_report_and_html_is_escaped(self):
        with tempfile.TemporaryDirectory() as temp:
            result=run(ROOT,out=temp)
            self.assertEqual(read(Path(temp)/'run.json')['new_llm_calls'],0)
            self.assertTrue((Path(temp)/'report.html').is_file())
            from reporting import write_report
            result['limits'].append('<script>alert(1)</script>')
            write_report(result,Path(temp))
            self.assertNotIn('<script>',(Path(temp)/'report.html').read_text(encoding='utf-8'))

    def test_transport_error_saves_safe_failure_without_secret(self):
        with tempfile.TemporaryDirectory() as temp:
            def broken(body): raise ValueError('demo-test-secret')
            with self.assertRaises(RuntimeError): generate(self.result,'demo-test-secret',temp,transport=broken)
            self.assertNotIn('demo-test-secret',(Path(temp)/'failure.json').read_text())
            self.assertEqual(read(Path(temp)/'failure.json')['attempts'],1)

    def test_manifest_tamper_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            r=Path(temp); (r/'input').mkdir()
            (r/'input/data.json').write_text('tampered')
            (r/'input/manifest.json').write_text(json.dumps([{'path':'input/data.json','sha256':'wrong'}]))
            with self.assertRaises(ValueError): verify_inputs(r)


if __name__=='__main__': unittest.main()
