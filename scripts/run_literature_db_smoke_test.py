from __future__ import annotations

import argparse, json
from sleep_ai_scientist.literature_db.smoke_test import run_smoke_test

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--config",default="configs/literature_database_test.yaml");parser.add_argument("--reset-database",action="store_true");parser.add_argument("--per-provider-limit",type=int,default=10);parser.add_argument("--target-journal-limit",type=int,default=1);parser.add_argument("--max-journals-to-try",type=int,default=20);args=parser.parse_args()
    result=run_smoke_test(args.config,reset_database=args.reset_database,per_provider_limit=args.per_provider_limit,target_journal_limit=args.target_journal_limit,max_journals_to_try=args.max_journals_to_try);print(json.dumps(result,ensure_ascii=False,indent=2));return {"PASS":0,"PARTIAL_PASS":2,"FAIL":1}.get(result["overall_result"],1)

if __name__=="__main__":raise SystemExit(main())
