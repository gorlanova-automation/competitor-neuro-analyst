"""Meaningful offline checks; fake API responses never enter the real database."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import collector as c


class CollectorTests(unittest.TestCase):
    def chunk(self):
        return {'chunk_id':'c1','source_id':'s1','company_id':'test_fixture','url':'https://example.org/','collected_at':'2026-10-21T00:00:00Z','start':100,'text':'Консультация по налогам стоит 150 EUR за час.'}

    def fact(self):
        return {'field':'price','value':'Консультация по налогам: 150 EUR за час','evidence':'Консультация по налогам стоит 150 EUR за час.','kind':'published_offer','country':None,'offer_name':'Консультация по налогам','amount':150,'currency':'EUR','price_basis':'за час'}

    def test_chunks_cover_all_characters(self):
        text = ('Строка данных.\n'*2000)
        chunks = c.split_chunks(text,1000,120)
        covered = set()
        for item in chunks:
            self.assertEqual(item['text'],text[item['start']:item['end']])
            self.assertLessEqual(len(item['text']),1000)
            covered.update(range(item['start'],item['end']))
        self.assertEqual(len(covered),len(text))

    def test_cleanup_preserves_card_price_relationship(self):
        page = c.clean_html('<script>bad()</script><p>NIF</p><p>150 EUR</p><p>Консультация</p><p>150 EUR</p><a href="/prices">Цены</a><a href="https://t.me/test">TG</a>','https://example.org/')
        self.assertNotIn('bad()',page['text'])
        self.assertEqual(page['text'].count('150 EUR'),2)
        self.assertEqual(page['links'][0]['url'],'https://example.org/prices')

    def test_evidence_and_offsets(self):
        good,bad = c.validate_extraction({'facts':[self.fact()]},self.chunk(),c.fact_schema())
        self.assertEqual(len(good),1)
        self.assertEqual(good[0]['evidence_start'],100)
        self.assertEqual(bad,[])

    def test_hallucinated_evidence_is_quarantined(self):
        fact = self.fact(); fact['evidence'] = 'Консультация стоит 99 EUR.'
        good,bad = c.validate_extraction({'facts':[fact]},self.chunk(),c.fact_schema())
        self.assertEqual(good,[])
        self.assertIn('quote_not_found_or_too_short',bad[0]['validation_errors'])

    def test_wrong_numeric_amount_is_quarantined(self):
        fact = self.fact(); fact['amount'] = 999
        self.assertIn('amount_not_present_in_quote',c.validate_extraction({'facts':[fact]},self.chunk(),c.fact_schema())[1][0]['validation_errors'])

    def test_unlinked_price_and_trust_are_quarantined(self):
        fact = self.fact(); fact['offer_name'] = None
        self.assertEqual(len(c.validate_extraction({'facts':[fact]},self.chunk(),c.fact_schema())[1]),1)
        fact = self.fact(); fact.update(field='trust',amount=None,kind='published_offer')
        self.assertIn('trust_must_remain_company_claim',c.validate_extraction({'facts':[fact]},self.chunk(),c.fact_schema())[1][0]['validation_errors'])

    def test_schema_rejects_extra_fields(self):
        fact = self.fact(); fact['invented'] = True
        with self.assertRaises(c.ValidationError):
            c.validate_extraction({'facts':[fact]},self.chunk(),c.fact_schema())

    def test_secret_not_sent_to_other_host(self):
        with self.assertRaises(ValueError):
            c.api_json('https://example.org/v1','/models','FAKE_TEST_VALUE')

    def test_confirmation_gate(self):
        with self.assertRaises(ValueError):
            c.start_collection({'profile_confirmed':False},[],'.')

    def test_profile_stage_cannot_collect_competitors(self):
        config={'purpose':'own_company_profile','selected_ids':['rival']}
        with self.assertRaises(ValueError):
            c.start_collection(config,[{'id':'rival','role':'confirmed_competitor'}],'.')

    def test_query_generation_requires_profile_approval(self):
        from discovery import propose_queries
        with self.assertRaises(ValueError):
            propose_queries({'confirmed':False},'FAKE','test','https://api.proxyapi.ru/v1','.', ['Португалия'])

    def test_csv_formula_protection(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'test.csv'
            c.write_csv(path,[{'value':'=1+1'}],['value'])
            self.assertIn("'=1+1",path.read_text(encoding='utf-8-sig'))

    def test_catalog_and_request_shape(self):
        with patch.object(c,'api_json',return_value={'data':[{'id':'vendor/test'}]}) as mock:
            self.assertEqual(c.list_models('https://api.proxyapi.ru/v1','FAKE_TEST_VALUE'),['vendor/test'])
            self.assertEqual(mock.call_args.args[1],'/models')


if __name__ == '__main__':
    unittest.main(verbosity=2)
