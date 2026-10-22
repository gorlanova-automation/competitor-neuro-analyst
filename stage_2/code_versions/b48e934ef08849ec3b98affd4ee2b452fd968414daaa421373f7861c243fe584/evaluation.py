"""Compare LLM extraction to a manually prepared reference subset.

Subset recall is not full-corpus recall. Exact quote tests are not semantic precision.
"""
from pathlib import Path
import re
from collector import read_json, save_json, write_csv, utc_now


def compare_reference(run_dir, experiment_dir, reference):
    run_dir, experiment_dir = Path(run_dir), Path(experiment_dir)
    chunks = {c['chunk_id']:c for c in read_json(run_dir/'chunks.json')}
    facts = read_json(experiment_dir/'facts.json')
    meta = read_json(experiment_dir/'experiment.json')
    input_ids = {p.name.removesuffix('_request.json') for p in experiment_dir.glob('*_request.json')}
    rows = []
    for gold in reference:
        chunk = chunks.get(gold['chunk_id'])
        if not chunk or gold['evidence'] not in chunk['text']:
            status, matches = 'reference_not_present_in_snapshot', []
        elif gold['chunk_id'] not in input_ids:
            status, matches = 'chunk_not_sent_to_model', []
        else:
            candidates = [f for f in facts if f['chunk_id']==gold['chunk_id'] and f['field']==gold['field']]
            matches = [f for f in candidates if f['amount']==gold.get('amount') and f['kind']==gold['kind'] and all(re.search(token, (f['offer_name'] or '')+' '+f['value'],re.I) for token in gold['match_tokens'])]
            status = 'matched_rule_requires_semantic_review' if matches else 'not_matched_requires_semantic_review'
        rows.append({**gold,'status':status,'candidate_fact_ids':[f['fact_id'] for f in matches]})
    eligible = [r for r in rows if r['status'] not in ('reference_not_present_in_snapshot','chunk_not_sent_to_model')]
    matched = sum(r['status']=='matched_rule_requires_semantic_review' for r in eligible)
    summary = {'at':utc_now(),'model':meta['model'],'prompt_sha256':meta['prompt_sha256'],'reference_total':len(rows),'reference_in_tested_chunks':len(eligible),'matched_by_rules':matched,'subset_recall_rule':matched/len(eligible) if eligible else None,'accepted_facts':len(facts),'quarantined':meta['quarantined'],'failed_calls':meta['failures'],'semantic_precision':None,'semantic_precision_status':'pending_manual_review_of_accepted_facts','limitation':'Rule match is an aid to manual review, not proof of semantic correctness or full-corpus recall.'}
    save_json(experiment_dir/'reference_comparison.json',{'summary':summary,'rows':rows})
    write_csv(experiment_dir/'reference_comparison.csv',rows,['reference_id','company_id','field','amount','evidence','status','candidate_fact_ids'])
    return summary
