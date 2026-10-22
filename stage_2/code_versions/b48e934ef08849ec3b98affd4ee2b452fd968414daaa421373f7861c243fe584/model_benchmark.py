"""Fixed-corpus cross-provider benchmark. No automatic winner without review."""
from pathlib import Path
from collector import extract_run, read_json, save_json, utc_now
from evaluation import compare_reference


def benchmark_models(run_dir, api_key, models, settings, prompt, reference, max_calls=2):
    """Use one prompt and identical chunks. Each model consumes API credits."""
    rows=[]
    for model in models:
        experiment=extract_run(run_dir,api_key,model,settings,prompt,max_calls)
        summary=compare_reference(run_dir,experiment,reference)
        usage={'prompt_tokens':0,'completion_tokens':0,'total_tokens':0}
        usage_complete=True
        for path in Path(experiment).glob('*_response.json'):
            data=read_json(path).get('usage')
            if not data:
                usage_complete=False
                continue
            for key in usage:
                if key not in data:
                    usage_complete=False
                usage[key]+=data.get(key,0)
        rows.append({**summary,'experiment_dir':str(experiment),'usage':usage,'usage_complete':usage_complete,'selection_status':'pending_semantic_review','estimated_cost_rub':None})
    save_json(Path(run_dir)/'model_benchmark.json',{'at':utc_now(),'rows':rows,'winner':None,'reason':'Semantic review and tariff verification required before selection.'})
    return rows


def estimate_base_cost(prompt_tokens, completion_tokens, input_per_million, output_per_million):
    """Base estimate only; excludes special modes/cache/tool fees and retries."""
    values=[prompt_tokens,completion_tokens,input_per_million,output_per_million]
    if any(value is None or value<0 for value in values):
        raise ValueError('Нужны неотрицательные токены и подтверждённые ставки')
    return (prompt_tokens*input_per_million+completion_tokens*output_per_million)/1_000_000
