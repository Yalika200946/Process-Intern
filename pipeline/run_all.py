"""
CPHT end-to-end pipeline orchestrator.

Recomputes every dashboard artifact from process data by executing the VALIDATED
notebooks in dependency order (reusing their logic rather than re-implementing
it), then re-applying the honest post-processing so the dashboard's model card
and forecast bands survive notebook 13's exports.

Design notes:
  * Runs each notebook headless with `nbconvert --execute` under **UTF-8 mode**
    (`PYTHONUTF8=1`) — several notebooks read CSVs without an explicit encoding
    and crash under Windows cp1252 otherwise; UTF-8 mode fixes them all at once.
  * A new raw Excel is STAGED at the path notebook 01 expects (after backing up
    the original), so no notebook needs editing to point at the upload.
  * Everything is backed up to Data/backup_<ts>/ and dashboard/data/backup_<ts>/
    first; `--rollback-on-fail` restores them if any notebook errors.
  * `--only 13` or `--from 06` run partial chains for debugging.

Usage:
  python pipeline/run_all.py                      # recompute in place
  python pipeline/run_all.py --input new.xlsx     # stage a new raw Excel first
  python pipeline/run_all.py --only 13            # just the terminal exporter
"""
import argparse, logging, os, shutil, subprocess, sys, time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
NB   = REPO / 'notebooks'
DATA = Path(r'C:\Desktop\Bangchak Internship 2026\Data')
DASH_DATA = REPO / 'dashboard' / 'data'
RAW_INPUT = DATA / 'Process information data (2024-2026).xlsx'   # notebook 1's FILEPATH
LOG_FILE = DATA / 'pipeline_run.log'

# Structured logging alongside (not replacing) the existing console prints -- previously the
# only record of a run was whatever terminal output happened to be visible at the time, or,
# via the dashboard's "run full pipeline" button, backend/server.py's raw subprocess stdout
# capture with no timestamps/levels at all. `log` below writes to LOG_FILE only (console
# already gets the print()-based step-status lines; a StreamHandler here would just duplicate
# them) with a timestamp + level, so a run triggered from the dashboard -- no one watching
# the terminal -- is still diagnosable afterward from Data/pipeline_run.log.
logging.basicConfig(
    level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler(LOG_FILE, encoding='utf-8')])
log = logging.getLogger('run_all')

# dependency-ordered chain that produces the dashboard artifacts.
# (00/00b EDA-only and 02b correlation/PCA excluded; 05 kept because 08 reads its
#  Q_CIT_Sensitivity.csv.)
CHAIN = [
    '01_data_cleaning.ipynb',
    '02_feature_engineering.ipynb',
    '03_operating_state_classification.ipynb',
    '04_fouling_rate_estimation.ipynb',
    '05_fouling_cit_sensitivity.ipynb',
    '06_fouling_rate_forecast.ipynb',
    '07_time_to_clean_prediction.ipynb',
    '08_cleaning_priority_ranking.ipynb',
    '09_cit_ranking_baseline.ipynb',
    '10_cit_model_benchmark.ipynb',
    '11_cit_shap_importance.ipynb',
    '12_economic_delta_cit.ipynb',
    '13_cit_forecast_export.ipynb',
]

# post-processors that MUST run after 13 (CIT forecast export) to keep honest artifacts
POST = [
    ('honest model_metrics.json', [sys.executable, str(REPO / 'pipeline' / 'gen_honest_metrics.py')]),
    ('engineering priority ranking (nb 08)', [sys.executable, str(REPO / 'pipeline' / 'export_engineering_priority.py')]),
    ('forecast prediction bands', [sys.executable, str(NB / 'add_forecast_intervals.py')]),
    ('P&ID topology + furnace',   [sys.executable, str(NB / 'build_dashboard_topology.py')]),
    ('PHM: RUL/reliability/drivers', [sys.executable, str(REPO / 'pipeline' / 'phm_analysis.py')]),
    ('per-HX time-series',           [sys.executable, str(REPO / 'pipeline' / 'export_hx_timeseries.py')]),
    ('End-of-Run duty forecast',     [sys.executable, str(REPO / 'pipeline' / 'export_end_of_run.py')]),
    ('cleaning audit history',       [sys.executable, str(REPO / 'pipeline' / 'export_cleaning_history.py')]),
    ('economics (CIT->฿)',           [sys.executable, str(REPO / 'pipeline' / 'export_economics.py')]),
    ('cleaning/bypass/TAM list',     [sys.executable, str(NB / 'cleaning_logistics.py')]),
    ('TAM deep analysis (nb 14)',    [sys.executable, '-m', 'nbconvert', '--to', 'notebook', '--execute',
                                      '--inplace', '--ExecutePreprocessor.timeout=900',
                                      str(NB / '14_tam_constraint_analysis.ipynb')]),
    ('cleaning schedule -> TAM2028', [sys.executable, str(REPO / 'pipeline' / 'cleaning_scheduler.py')]),
    ('cleaning schedule v2 (network)', [sys.executable, str(REPO / 'pipeline' / 'cleaning_scheduler_network.py')]),
    ('evidence & confidence surface', [sys.executable, str(REPO / 'pipeline' / 'export_evidence.py')]),
    ('integrated cleaning plan (nb 16)', [sys.executable, '-m', 'nbconvert', '--to', 'notebook', '--execute',
                                          '--inplace', '--ExecutePreprocessor.timeout=600',
                                          str(NB / '16_cleaning_plan_optimization.ipynb')]),
]

BACKUP_CSVS = ['Process_information_cleaned.csv', 'Process_information_with_crude.csv',
               'Feature_calculated.csv', 'Operating_State.csv', 'Feature_Q.csv',
               'Fouling_Rate_Ranking.csv', 'Fouling_Rate_By_Run.csv',
               'Q_Deviation_Signal.csv', 'Cold_Out_Deviation_Signal.csv',
               'Time_To_Clean_Prediction.csv', 'Q_CIT_Sensitivity.csv',
               'Cleaning_Priority_Ranking.csv', 'Engineering_Priority_Score.csv']


def run_nb(nb_name, timeout):
    env = {**os.environ, 'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8'}
    t0 = time.time()
    r = subprocess.run(
        [sys.executable, '-m', 'nbconvert', '--to', 'notebook', '--execute', '--inplace',
         f'--ExecutePreprocessor.timeout={timeout}', str(NB / nb_name)],
        capture_output=True, text=True, env=env)
    return r.returncode == 0, time.time() - t0, (r.stderr or '')[-1200:]


def backup(ts):
    for base, files in [(DATA, BACKUP_CSVS), (DASH_DATA, [p.name for p in DASH_DATA.glob('*.json')])]:
        bdir = base / f'backup_{ts}'; bdir.mkdir(exist_ok=True)
        for f in files:
            src = base / f
            if src.exists():
                shutil.copy2(src, bdir / f)
    return DATA / f'backup_{ts}', DASH_DATA / f'backup_{ts}'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', help='new raw process Excel to stage before running')
    ap.add_argument('--only', help='run a single notebook basename fragment (e.g. 13)')
    ap.add_argument('--from', dest='start', help='start the chain at this notebook fragment')
    ap.add_argument('--timeout', type=int, default=900, help='per-notebook timeout (s)')
    ap.add_argument('--rollback-on-fail', action='store_true')
    args = ap.parse_args()

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    print(f'== CPHT pipeline run {ts} ==')
    log.info(f'=== pipeline run {ts} started (args: {vars(args)}) ===')
    data_bk, dash_bk = backup(ts)
    print(f'backed up -> {data_bk.name}, {dash_bk.name}')

    if args.input:
        up = Path(args.input)
        if not up.exists():
            print(f'!! input not found: {up}'); sys.exit(2)
        shutil.copy2(RAW_INPUT, data_bk / RAW_INPUT.name) if RAW_INPUT.exists() else None
        shutil.copy2(up, RAW_INPUT)
        print(f'staged new raw input: {up.name} -> {RAW_INPUT.name}')

    chain = CHAIN
    if args.only:
        chain = [n for n in CHAIN if args.only in n]
    elif args.start:
        idx = next((i for i, n in enumerate(CHAIN) if args.start in n), 0)
        chain = CHAIN[idx:]

    results, failed = [], None
    for nb in chain:
        ok, dt, err = run_nb(nb, args.timeout)
        status = 'OK ' if ok else 'FAIL'
        print(f'  [{status}] {nb:48s} {dt:6.1f}s')
        log.info(f'CHAIN step {nb}: {"OK" if ok else "FAIL"} ({dt:.1f}s)')
        results.append((nb, ok, dt))
        if not ok:
            print('  --- stderr tail ---\n' + '\n'.join('    ' + l for l in err.splitlines()[-12:]))
            log.error(f'CHAIN step {nb} failed:\n{err}')
            failed = nb
            break
        # authoritative robust fouling rate needs Operating_State.csv (from 03) — run it
        # right after 03 so 04/08/06/07/exports downstream read the physical, reliable version.
        if '03_operating_state' in nb:
            env = {**os.environ, 'PYTHONUTF8': '1'}
            r = subprocess.run([sys.executable, str(REPO / 'pipeline' / 'compute_fouling_rate.py')],
                               capture_output=True, text=True, env=env)
            print(f'  [{"OK " if r.returncode == 0 else "FAIL"}] {"robust fouling rate (post-03)":48s}')
            log.info(f'compute_fouling_rate.py: {"OK" if r.returncode == 0 else "FAIL"}')
            if r.returncode != 0:
                print('    ' + (r.stderr or r.stdout or '')[-800:])
                log.error(f'compute_fouling_rate.py failed:\n{r.stderr or r.stdout}')
                failed = 'compute_fouling_rate.py'; break

    if failed and args.rollback_on_fail:
        print(f'rolling back from {data_bk.name} …')
        for f in data_bk.glob('*'): shutil.copy2(f, DATA / f.name)
        for f in dash_bk.glob('*'): shutil.copy2(f, DASH_DATA / f.name)
        print('rolled back.'); sys.exit(1)

    # post-processing (only if 13_cit_forecast_export ran, or --only wasn't a non-13 single step)
    ran_terminal = any('13_cit_forecast_export' in n and ok for n, ok, _ in results)
    post_failed = []   # (label,) of every POST step that failed -- previously untracked, so a
                        # failure here silently didn't affect the final exit code (see below).
    if ran_terminal or not args.only:
        print('post-processing (honest metrics / bands / topology):')
        for label, cmd in POST:
            env = {**os.environ, 'PYTHONUTF8': '1'}
            r = subprocess.run(cmd, capture_output=True, text=True, env=env)
            print(f'  [{"OK " if r.returncode==0 else "FAIL"}] {label}')
            log.info(f'POST step "{label}": {"OK" if r.returncode == 0 else "FAIL"}')
            if r.returncode != 0:
                print('    ' + (r.stderr or '')[-400:])
                log.error(f'POST step "{label}" failed:\n{r.stderr}')
                post_failed.append(label)

    if post_failed:
        # every POST step still runs regardless of an earlier one's failure (many are
        # logically independent, e.g. PHM/RUL doesn't need cleaning_scheduler_network's
        # output) -- but a failed step's OWN artifact, and anything reading it downstream in
        # this same POST list, is now STALE (still holds whatever it had from the previous
        # run, not this one). Surface that explicitly rather than letting it look identical
        # to a clean run in the console/log.
        msg = (f'{len(post_failed)} POST step(s) failed: {post_failed} -- their output files '
               'are STALE (unchanged from the previous run), not missing or corrupted, but '
               'the dashboard may now be serving a mix of fresh and stale artifacts.')
        print(f'!! {msg}')
        log.warning(msg)

    n_ok = sum(1 for _, ok, _ in results if ok)
    print(f'== done: {n_ok}/{len(results)} notebooks OK'
          + (f', {len(post_failed)} POST step(s) FAILED' if post_failed else '')
          + f'; backups in {data_bk.name} ==')
    exit_code = 1 if (failed or post_failed) else 0
    log.info(f'=== pipeline run {ts} finished, exit_code={exit_code} ===')
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
