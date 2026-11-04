"""Validate human checkpoints; never infer acceptance from a saved draft."""
import hashlib
import json
from pathlib import Path


def analyze_case(case_dir, review=None):
    root=Path(case_dir)
    source=json.loads((root/'own_source.json').read_text(encoding='utf-8'))
    profile=json.loads((root/'profile.json').read_text(encoding='utf-8'))
    candidates=json.loads((root/'candidate_sources.json').read_text(encoding='utf-8'))
    actual=hashlib.sha256(source['text'].encode()).hexdigest()
    if actual != profile['source_sha256']: raise ValueError('Source changed; profile needs review')
    if not review or review.get('profile_confirmed') is not True:
        return {'case_id':root.name,'status':'needs_user_review','next_action':'Подтвердить профиль и выбрать конкурентов',
                'new_llm_calls':0,'hypotheses':[]}
    if review.get('case_id') != root.name or review.get('source_sha256') != actual:
        raise ValueError('Review belongs to another case or source snapshot')
    if not isinstance(review.get('market_scope'),str) or not review['market_scope'].strip():
        raise ValueError('Confirm market geography and audience')
    selected=review.get('competitor_urls')
    allowed={s['requested_url']:s for s in candidates if s.get('sha256_text')}
    if not isinstance(selected,list) or not selected or len(set(selected)) != len(selected) or any(u not in allowed for u in selected):
        raise ValueError('Select at least one successfully collected candidate; new URLs require collection first')
    rows=[]
    for url in selected:
        s=allowed[url]
        if hashlib.sha256(s['text'].encode()).hexdigest() != s['sha256_text']:
            raise ValueError('Candidate source changed')
        rows.append({'url':url,'name':s['title'],'published_summary':s['description'],
                     'collected_at':s['collected_at'],'source_sha256':s['sha256_text'],
                     'verification':'published_claim_only_not_product_test'})
    approved_profile={**profile,'company_name':review.get('company_name') or profile['company_name'],
                      'summary':review.get('summary') or profile['summary'],
                      'review_status':'user_confirmed_for_selected_snapshot'}
    return {'case_id':root.name,'status':'descriptive_comparison_after_user_review',
            'profile':approved_profile,'market_scope':review['market_scope'],'competitors':rows,
            'new_llm_calls':0,'new_api_cost':0,'hypotheses':[],
            'limits':['Сопоставлены описания публичных страниц; качество продуктов не тестировалось.',
                      'Сравнение тарифов и эффективности требует отдельной разметки состава и условий.']}


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--case',required=True)
    parser.add_argument('--review')
    args=parser.parse_args()
    review=json.loads(Path(args.review).read_text(encoding='utf-8')) if args.review else None
    result=analyze_case(args.case,review)
    Path(args.case,'analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
