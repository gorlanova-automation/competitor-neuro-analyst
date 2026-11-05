"""Evidence checks for the broad research, not tests that declare marketing truth."""
import hashlib
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
RESEARCH=ROOT/'research/market_20261105'


class MarketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.market=json.loads((RESEARCH/'market.json').read_text(encoding='utf-8'))

    def test_all_companies_and_access_failures_are_visible(self):
        catalog=json.loads((ROOT/'input/companies.json').read_text(encoding='utf-8'))
        self.assertEqual({c['id'] for c in catalog},{c['company_id'] for c in self.market['companies']})
        for c in self.market['companies']:
            if not c['pages_ok']:
                self.assertEqual(c['assortment'],[])
                self.assertEqual(c['visual']['status'],'unavailable')

    def test_assortment_and_tone_quotes_exist_in_saved_sources(self):
        for c in self.market['companies']:
            pages=json.loads((RESEARCH/(c['company_id']+'_sources.json')).read_text(encoding='utf-8'))
            sources={p['final_url']:p for p in pages if p['status']=='ok'}
            for p in sources.values():
                self.assertEqual(hashlib.sha256(p['text'].encode()).hexdigest(),p['sha256_text'])
            for item in c['assortment']+c['tone_signals']+c['conversion_paths']:
                self.assertIn(item['quote'],sources[item['source_url']]['text'])
            for link in c['channels']:
                self.assertIn(link['url'],[l['url'] for l in sources[link['found_on']]['links']])

    def test_publications_are_deduplicated_and_have_provenance(self):
        posts=[p for c in self.market['companies'] for p in c['posts']]
        self.assertEqual(len(posts),len({p['post_url'] for p in posts}))
        self.assertGreaterEqual(len({p['company_id'] for p in posts}),3)
        for p in posts:
            self.assertTrue(p['published_at'] and p['source_url'] and p['collected_at'])
            self.assertEqual(hashlib.sha256(p['text'].encode()).hexdigest(),p['sha256_text'])

    def test_summary_matches_actual_coverage(self):
        s=self.market['summary'];companies=self.market['companies']
        self.assertEqual(s['companies_total'],len(companies))
        self.assertEqual(s['telegram_posts'],sum(len(c['posts']) for c in companies))
        self.assertEqual(s['companies_with_telegram_posts'],sum(bool(c['posts']) for c in companies))
        self.assertEqual(s['pages_ok'],sum(c['pages_ok'] for c in companies))

    def test_visual_method_and_sampling_limits_are_explicit(self):
        for c in self.market['companies']:
            self.assertEqual(c['visual']['method'],'assistant_manual_browser_screenshot_review')
            self.assertTrue(c['visual']['limitation'])
            self.assertEqual(c['publication_summary']['frequency'],'not_estimated_incomplete_sample')
            for ch in c['channels']:
                if ch.get('purpose')=='contact_invite_or_bot':self.assertFalse(ch['posts'])


if __name__=='__main__':unittest.main()
