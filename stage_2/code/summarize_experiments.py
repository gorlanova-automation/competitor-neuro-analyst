"""Summarize saved experiments without additional API calls."""
from collections import Counter
from pathlib import Path
from collector import read_json, save_json, write_csv
from model_benchmark import estimate_base_cost

RATES = {
    'openai/gpt-6-luna': (30,150),
    'google/gemini-3.5-flash-lite': (91,758),
    'anthropic/claude-haiku-4-5': (295,1474),
}

def summarize(run_dir):
    run_dir=Path(run_dir)
    rows=[]; prices=[]
    for folder in sorted((run_dir/'experiments').iterdir()):
        if not (folder/'facts.json').exists():
            continue
        meta=read_json(folder/'experiment.json')
        facts=read_json(folder/'facts.json')
        responses=[read_json(p) for p in folder.glob('*_response.json')]
        complete=len(responses)==meta['chunks_attempted'] and all(r.get('usage') and all(k in r['usage'] for k in ('prompt_tokens','completion_tokens')) for r in responses)
        inputs=sum((r.get('usage') or {}).get('prompt_tokens',0) for r in responses)
        outputs=sum((r.get('usage') or {}).get('completion_tokens',0) for r in responses)
        rate=RATES.get(meta['model'])
        row={'experiment':folder.name,'model':meta['model'],'prompt_sha256':meta['prompt_sha256'],'accepted':len(facts),'fields':dict(Counter(f['field'] for f in facts)),'quarantined':meta['quarantined'],'failed_calls':meta['failures'],'prompt_tokens':inputs,'completion_tokens':outputs,'usage_complete':complete,'base_cost_estimate_rub':estimate_base_cost(inputs,outputs,*rate) if complete and rate else None,'rate_snapshot':'2026-10-22','semantic_precision':None}
        if (folder/'reference_comparison.json').exists():
            row['reference']=read_json(folder/'reference_comparison.json')['summary']
        rows.append(row)
        prices.extend({'experiment':folder.name,**f} for f in facts if f['field']=='price')
    result={'rows':rows,'winner':None,'limitation':'Base tariff estimates are not invoices. Quality requires semantic review; 8-price subset does not cover all fields.'}
    save_json(run_dir/'experiment_audit.json',result)
    write_csv(run_dir/'prices_for_review.csv',prices,['experiment','fact_id','company_id','offer_name','amount','currency','price_basis','kind','country','evidence','url'])
    return result

if __name__=='__main__':
    import argparse,json
    parser=argparse.ArgumentParser()
    parser.add_argument('run_dir')
    print(json.dumps(summarize(parser.parse_args().run_dir),ensure_ascii=False,indent=2))
