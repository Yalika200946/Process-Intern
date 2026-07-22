"""One-command reproducible fast-track run; runtime artifacts remain gitignored."""
from pathlib import Path
import json,os,subprocess,sys,time
ROOT=Path(__file__).resolve().parents[1]
SCRIPTS=["run_mvp_real_data.py","build_mvp_coverage_outputs.py","explore_empirical_relative_performance.py","analyze_signal_inferred_cleaning.py","screen_hx_cit_relationships.py","assess_fast_track_network.py","analyze_f101_consequence.py","forecast_empirical_performance.py","build_fast_track_decision_support.py","run_critical_correction_batch.py"]
def main():
    started=time.time();steps=[]
    for name in SCRIPTS:
        result=subprocess.run([sys.executable,str(ROOT/"pipeline"/name)],cwd=ROOT);steps.append({"step":name,"exit_code":result.returncode,"status":"VALIDATED" if result.returncode==0 else "BLOCKED"})
        if result.returncode:raise SystemExit(result.returncode)
    env=os.environ.copy();env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"]="1";test=subprocess.run([sys.executable,"-m","pytest","-q"],cwd=ROOT,env=env);steps.append({"step":"full_tests","exit_code":test.returncode,"status":"VALIDATED" if test.returncode==0 else "BLOCKED"})
    if test.returncode:raise SystemExit(test.returncode)
    out=ROOT/"reports/tables/mvp_real_data/fast_track";out.mkdir(parents=True,exist_ok=True);(out/"test_results.json").write_text(json.dumps({"status":"VALIDATED","exit_code":test.returncode,"command":"python -m pytest -q"},indent=2),encoding="utf-8")
    subprocess.run([sys.executable,str(ROOT/"pipeline/build_fast_track_report.py")],cwd=ROOT,check=True);(out/"run_execution_status.json").write_text(json.dumps({"command":"python pipeline/run_fast_track_end_to_end.py","elapsed_seconds":time.time()-started,"steps":steps},indent=2),encoding="utf-8")
if __name__=="__main__":main()
