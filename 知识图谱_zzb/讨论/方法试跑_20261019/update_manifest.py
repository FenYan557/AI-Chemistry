"""Record local artifacts without secrets or claims of deterministic remote inference."""
from pathlib import Path
import hashlib,json,platform,sys
root=Path(__file__).resolve().parent
exclude={'execution_manifest.json'}
files={p.name:{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in root.iterdir() if p.is_file() and p.name not in exclude}
manifest={'date':'2026-10-19','python':sys.version,'platform':platform.platform(),'model_reported':'deepseek-flash','model_revision':None,'temperature':None,'seed':None,'executor':'Claude Code via existing Hub bridge','tool_access':'agent CLI; prompted local input-only, not a sandbox proof','domain_type_seed_provided':False,'manual_gold':False,'method_review_tasks':['task_4fee5b3c01324d62','task_a5219d304c7a4d27'],'candidate_task':'task_168fb7b8eae54231','induction_task':'task_571fe4bbccdc4cc0','tasks_status_means':'awaiting_review requires parent artifact acceptance; not scientific validation','raw_audit_expected_exit_code':1,'remote_bitwise_reproducible':False,'bert_training_run':False,'formal_benchmark_run':False,'v2_template_run':False,'files':files}
(root/'execution_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'files_hashed':len(files),'model':manifest['model_reported'],'exact_remote_reproduction':False},ensure_ascii=False))
