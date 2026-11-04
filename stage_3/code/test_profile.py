import json
import tempfile
import unittest
from pathlib import Path
from profile_site import draft_profile
from review_case import analyze_case

ROOT=Path(__file__).resolve().parents[1]


class ProfileTests(unittest.TestCase):
    def test_other_domain_has_no_immigration_settings(self):
        source=json.loads((ROOT/'cases/shift/own_source.json').read_text(encoding='utf-8'))
        profile=draft_profile(source)
        self.assertEqual(profile['company_name'],'SHIFT')
        self.assertIn('video',profile['market_terms'])
        self.assertNotIn('Portugal',str(profile))
        self.assertEqual(profile['review_status'],'pending_user_confirmation')

    def test_no_approval_blocks_comparison(self):
        result=analyze_case(ROOT/'cases/shift')
        self.assertEqual(result['status'],'needs_user_review')
        self.assertEqual(result['hypotheses'],[])

    def test_review_is_bound_to_snapshot_and_case(self):
        profile=json.loads((ROOT/'cases/shift/profile.json').read_text(encoding='utf-8'))
        sources=json.loads((ROOT/'cases/shift/candidate_sources.json').read_text(encoding='utf-8'))
        urls=[s['requested_url'] for s in sources if s.get('sha256_text')]
        self.assertTrue(urls,'At least one real candidate capture required')
        review={'case_id':'shift','source_sha256':profile['source_sha256'],
                'profile_confirmed':True,'market_scope':'Synthetic test scope, not user approval','competitor_urls':urls[:1]}
        result=analyze_case(ROOT/'cases/shift',review)
        self.assertEqual(len(result['competitors']),1)
        for invalid in ({**review,'source_sha256':'wrong'}, {**review,'competitor_urls':['https://invented.test/']},
                        {**review,'market_scope':''}, {**review,'case_id':'immigration'}):
            with self.assertRaises(ValueError): analyze_case(ROOT/'cases/shift',invalid)
