"""
CPHT end-to-end pipeline orchestrator.

Recomputes every dashboard artifact from process data by executing the VALIDATED
notebooks in dependency order (reusing their logic rather than re-implementing
it), then re-applying the honest post-processing so the dashboard's model card
and forecast bands survive production/10_economic_evaluation_forecast_export.ipynb Part 2's exports.

Design notes:
  * Runs each notebook headless with `nbconvert --execute` under **UTF-8 mode**
    (`PYTHONUTF8=1`) — several notebooks read CSVs without an explicit encoding
    and crash under Windows cp1252 otherwise; UTF-8 mode fixes them all at once.
  * A new raw Excel is STAGED at the path notebook 01 expects (after backing up
    the original), so no notebook needs editing to point at the upload.
  * Everything is backed up to Data/backup_<ts>/ and dashboard/data/backup_<ts>/
    first; `--rollback-on-fail` restores them if any notebook errors.
  * `--only cit_forecast_export` or `--from clean_baseline` run partial chains
    for debugging (matches on any unique fragment of the CHAIN path).

Usage:
  python pipeline/run_all.py                      # recompute in place
  python pipeline/run_all.py --input new.xlsx     # stage a new raw Excel first
  python pipeline/run_all.py --only cit_forecast_export   # just the terminal exporter
"""
import argparse, logging, os, shutil, subprocess, sys, time
from datetime import datetime
from pathlib import Path

# This script's own console output includes Thai text (POST step labels like "economics
# (CIT->฿)"), but Windows' default console codepage (cp1252) can't encode it -- print()
# then raises UnicodeEncodeError and kills the run before the remaining POST steps (e.g.
# export_economics.py) ever execute. Reconfigure stdout/stderr to UTF-8 unconditionally so
# this script's own prints can never crash the run, independent of the console's codepage.
# (Distinct from the existing PYTHONUTF8 env var below, which only affects the *subprocess*
# notebooks/scripts this script launches, not this process's own stdout.)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

REPO = Path(__file__).resolve().parent.parent
NB   = REPO / 'notebooks'
SRC  = REPO / 'src'
DATA = Path(os.environ.get('CPHT_DATA_DIR', r'C:\Desktop\Bangchak Internship 2026\Data'))
DASH_DATA = REPO / 'dashboard' / 'data'
EXECUTED_NB = REPO / 'reports' / 'executed_notebooks'
DATA.mkdir(parents=True, exist_ok=True)
DASH_DATA.mkdir(parents=True, exist_ok=True)
EXECUTED_NB.mkdir(parents=True, exist_ok=True)
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
# (notebooks/eda/process_control_exploration.ipynb, crude_assay_exploration.ipynb,
#  correlation_and_pca.ipynb -- moved into notebooks/eda/ 2026-07-17, originally
#  00_data_prep_process_control/00_data_prep_crude_assay/02b_correlation_and_pca -- are
#  EDA-only and excluded.)
#
# Renamed into notebooks/production/ 2026-07-17 (see docs/archive/MIGRATION_MAP.md for the full
# old->new table). NOTE: the new filenames' leading numbers follow the TARGET_PIPELINE.md
# conceptual stage order (data quality -> operating modes -> hx performance -> ...), which
# is NOT the same as this list's actual execution order below.
#
# 2026-07-19 consolidation (two rounds) reduced notebook count from 17 to 11 by merging
# notebooks that ran back-to-back in this CHAIN with no other script in between (safe merge --
# no intermediate writer like compute_fouling_rate.py sits between the merged parts), grouped
# by shared real purpose rather than old filename:
#   - 03_hx_performance.ipynb + 02_operating_modes.ipynb -> production/02_hx_performance_operating_modes.ipynb
#     (in that cell order -- hx_performance genuinely runs first).
#   - 14_cit_model_feature_matrix.ipynb + 15_cit_model_benchmark.ipynb + 16_cit_shap_importance.ipynb
#     -> production/14_cit_model_feature_matrix.ipynb (single file, 3 parts). These three were
#     already documented as "reference, not canonical" (15's own finding: ML loses to a
#     persistence baseline) but still produce files 12_cit_forecast_export.ipynb (now merged
#     into 10, see below) and gen_honest_metrics.py read, so the merged file stays in CHAIN.
#   - 09_cit_furnace_impact.ipynb + 04_clean_baseline.ipynb + 07_forecasting.ipynb ->
#     production/04_fouling_cit_impact_forecast.ipynb (3 parts, in that cell order -- same
#     real CHAIN order as before: CIT sensitivity -> clean-baseline fouling-rate forecast ->
#     time-to-clean prediction; 07's input is literally 04's output).
#   - 10_economic_evaluation.ipynb + 12_cit_forecast_export.ipynb ->
#     production/10_economic_evaluation_forecast_export.ipynb (2 parts) -- the two notebooks
#     that closed out the main CHAIN back-to-back with nothing in between.
# The old long-standing filename/run-order mismatch these merges also happened to resolve is
# NOT the reason for merging -- see docs/archive/MIGRATION_MAP.md for that separate history.
CHAIN = [
    'production/01_data_quality.ipynb',
    'production/02_hx_performance_operating_modes.ipynb',
    'production/05_fouling_analysis.ipynb',
    'production/04_fouling_cit_impact_forecast.ipynb',
    'production/08_cleaning_priority.ipynb',
    'production/14_cit_model_feature_matrix.ipynb',
    'production/10_economic_evaluation_forecast_export.ipynb',
]

# post-processors that MUST run after the terminal 10_economic_evaluation_forecast_export.ipynb notebook to keep honest artifacts
POST = [
    ('honest model_metrics.json', [sys.executable, str(REPO / 'pipeline' / 'gen_honest_metrics.py')]),
    ('engineering priority ranking (nb 08)', [sys.executable, str(REPO / 'pipeline' / 'export_engineering_priority.py')]),
    # forecast prediction bands: folded into production/10_economic_evaluation_forecast_export.ipynb
    # Part 2's own export cell (section 2b) so forecast_6mo.json has exactly one writer with the
    # complete schema from the start -- add_forecast_intervals.py is superseded, not deleted
    # (see its own module docstring), and no longer invoked here.
    ('P&ID topology + furnace',   [sys.executable, str(SRC / 'reporting' / 'dashboard_topology.py')]),
    ('PHM: RUL/reliability/drivers', [sys.executable, str(REPO / 'pipeline' / 'phm_analysis.py')]),
    ('per-HX time-series',           [sys.executable, str(REPO / 'pipeline' / 'export_hx_timeseries.py')]),
    ('End-of-Run duty forecast',     [sys.executable, str(REPO / 'pipeline' / 'export_end_of_run.py')]),
    ('cleaning audit history',       [sys.executable, str(REPO / 'pipeline' / 'export_cleaning_history.py')]),
    ('economics (CIT->฿)',           [sys.executable, str(REPO / 'pipeline' / 'export_economics.py')]),
    ('cleaning/bypass/TAM list',     [sys.executable, str(SRC / 'optimization' / 'cleaning_logistics.py')]),
    ('TAM deep analysis (production/17)', [sys.executable, '-m', 'nbconvert', '--to', 'notebook', '--execute',
                                      f'--output-dir={EXECUTED_NB}', '--ExecutePreprocessor.timeout=900',
                                      str(NB / 'production' / '17_tam_constraint_analysis.ipynb')]),
    ('cleaning schedule -> TAM2028', [sys.executable, str(REPO / 'pipeline' / 'cleaning_scheduler.py')]),
    ('cleaning schedule v2 (network)', [sys.executable, str(REPO / 'pipeline' / 'cleaning_scheduler_network.py')]),
    ('evidence & confidence surface', [sys.executable, str(REPO / 'pipeline' / 'export_evidence.py')]),
    ('integrated cleaning plan (production/13)', [sys.executable, '-m', 'nbconvert', '--to', 'notebook', '--execute',
                                          f'--output-dir={EXECUTED_NB}', '--ExecutePreprocessor.timeout=600',
                                          str(NB / 'production' / '13_cleaning_plan_optimization.ipynb')]),
]

BACKUP_CSVS = ['Process_information_cleaned.csv', 'Process_information_with_crude.csv',
               'Feature_calculated.csv', 'Operating_State.csv', 'Feature_Q.csv',
               'Fouling_Rate_Ranking.csv', 'Fouling_Rate_By_Run.csv',
               'Cleaning_Event_Validation.csv',
               'Q_Deviation_Signal.csv',
               'Time_To_Clean_Prediction.csv', 'Q_CIT_Sensitivity.csv',
               'Cleaning_Priority_Ranking.csv', 'Engineering_Priority_Score.csv']


def subprocess_env():
    """Environment shared by notebooks and post-processors.

    Every notebook now imports directly from the ``src`` package (the old
    ``notebooks/*.py`` compatibility shims were removed 2026-07-19), so only the
    repository root and ``pipeline/`` need to be on PYTHONPATH.
    """
    inherited = os.environ.get('PYTHONPATH', '')
    pythonpath = os.pathsep.join(
        p for p in (str(REPO), str(REPO / 'pipeline'), inherited) if p
    )
    return {**os.environ, 'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8',
            'PYTHONPATH': pythonpath, 'CPHT_DATA_DIR': str(DATA)}


def run_nb(nb_name, timeout):
    env = subprocess_env()
    t0 = time.time()
    r = subprocess.run(
        [sys.executable, '-m', 'nbconvert', '--to', 'notebook', '--execute',
         f'--output-dir={EXECUTED_NB}',
         f'--ExecutePreprocessor.timeout={timeout}', str(NB / nb_name)],
        capture_output=True, text=True, env=env)
    return r.returncode == 0, time.time() - t0, (r.stderr or '')[-1200:]


def select_chain(only=None, start=None):
    """Resolve CLI selectors and reject typos or ambiguous fragments."""
    if only:
        matches = [name for name in CHAIN if only in name]
        if not matches:
            raise ValueError(f'--only {only!r} does not match any production notebook')
        if len(matches) > 1:
            raise ValueError(f'--only {only!r} is ambiguous: {matches}')
        return matches
    if start:
        matches = [i for i, name in enumerate(CHAIN) if start in name]
        if not matches:
            raise ValueError(f'--from {start!r} does not match any production notebook')
        if len(matches) > 1:
            names = [CHAIN[i] for i in matches]
            raise ValueError(f'--from {start!r} is ambiguous: {names}')
        return CHAIN[matches[0]:]
    return list(CHAIN)


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
    ap.add_argument('--only', help='run a single notebook path fragment (e.g. cit_forecast_export)')
    ap.add_argument('--from', dest='start', help='start the chain at this notebook fragment')
    ap.add_argument('--timeout', type=int, default=900, help='per-notebook timeout (s)')
    rollback = ap.add_mutually_exclusive_group()
    rollback.add_argument('--rollback-on-fail', dest='rollback_on_fail', action='store_true', default=True,
                          help='restore backed-up artifacts when a chain step fails (default)')
    rollback.add_argument('--no-rollback-on-fail', dest='rollback_on_fail', action='store_false',
                          help='keep partial outputs for debugging')
    args = ap.parse_args()

    # Validate all CLI choices before creating backup directories or staging input.
    try:
        chain = select_chain(args.only, args.start)
    except ValueError as exc:
        ap.error(str(exc))
    up = Path(args.input) if args.input else None
    if up is not None and not up.exists():
        ap.error(f'input not found: {up}')

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    print(f'== CPHT pipeline run {ts} ==')
    log.info(f'=== pipeline run {ts} started (args: {vars(args)}) ===')
    data_bk, dash_bk = backup(ts)
    print(f'backed up -> {data_bk.name}, {dash_bk.name}')

    if up is not None:
        shutil.copy2(RAW_INPUT, data_bk / RAW_INPUT.name) if RAW_INPUT.exists() else None
        shutil.copy2(up, RAW_INPUT)
        print(f'staged new raw input: {up.name} -> {RAW_INPUT.name}')

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
        # authoritative robust fouling rate needs Operating_State.csv (from operating_modes) —
        # run it right after operating_modes so fouling_analysis/cleaning_priority/
        # clean_baseline/forecasting downstream read the physical, reliable version.
        if 'operating_modes' in nb:
            env = subprocess_env()
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

    # Post-processing is valid only after the terminal cit_forecast_export notebook completed
    # in this same successful chain. Running it after an upstream failure would publish a
    # mixture of fresh and stale artifacts from different snapshots.
    ran_terminal = any('cit_forecast_export' in n and ok for n, ok, _ in results)
    post_failed = []   # (label,) of every POST step that failed -- previously untracked, so a
                        # failure here silently didn't affect the final exit code (see below).
    if not failed and ran_terminal:
        print('post-processing (honest metrics / bands / topology):')
        for label, cmd in POST:
            env = subprocess_env()
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
        if args.rollback_on_fail:
            print(f'rolling back complete snapshot from {data_bk.name} after POST failure ...')
            for f in data_bk.glob('*'):
                shutil.copy2(f, DATA / f.name)
            for f in dash_bk.glob('*'):
                shutil.copy2(f, DASH_DATA / f.name)
            print('rolled back.'); sys.exit(1)

    n_ok = sum(1 for _, ok, _ in results if ok)
    print(f'== done: {n_ok}/{len(results)} notebooks OK'
          + (f', {len(post_failed)} POST step(s) FAILED' if post_failed else '')
          + f'; backups in {data_bk.name} ==')
    exit_code = 1 if (failed or post_failed) else 0
    log.info(f'=== pipeline run {ts} finished, exit_code={exit_code} ===')
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
