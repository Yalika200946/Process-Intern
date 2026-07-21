"""
Authoritative per-run fouling-rate computation (robust, physically-constrained).

WHY THIS IS A SEPARATE STEP (not in notebook 02): a trustworthy fouling rate needs the
per-HX OPERATING STATE (`Operating_State.csv`) to drop periods when the HX isn't actually
transferring heat (OFF / SUBSTITUTED / BYPASS / mid-clean). That file is produced by
`03_operating_state_classification.ipynb`, which runs AFTER notebook 02 — so the rate is
computed here, right after 03, and OVERWRITES the rough `Fouling_Rate_By_Run.csv` that
notebook 02 wrote as an interactive first pass. All downstream consumers (04, 08, 06/07,
exports) run after this and read the robust file.

Method — `nb_audit.robust_fouling_rate` per HX per run (see METHODOLOGY §3.5):
  in-service mask (NORMAL/SUBSTITUTE_ACTIVE/PARALLEL) · winsorize U_relative to 1.10 ·
  AIC-race curve fit (linear vs Kern-Seaton asymptote vs power-law) directly on Rf, Theil-Sen slope
  + 95% CI · U_relative cross-check (dU_rel/dt≤0) · recent-60d "current" rate ·
  intra-run recovery split · reliability gate → `reliable` + `rate_flag`.

PRIMARY metric is Rf (fouling resistance), not U_relative — changed 2026-07-19 to match
the mechanistic fouling literature (Kern-Seaton, Ebert-Panchal), which is formulated in
Rf(t), not the U_relative "cleanliness factor" convention. See nb_audit.robust_fouling_rate's
docstring for the full rationale.

Physical invariant enforced & asserted: no `reliable` run has dRf_per_day ≤ 0.

BEFORE the rate regression, this also fixes the same in-service blind spot in the
baseline itself: notebook 02's `U_clean_run` (median of the first CLEAN_WINDOW_DAYS of a
run) only applies the physical operating mask (ΔT/flow), because `Operating_State.csv`
doesn't exist yet at that point in the pipeline. If a shell spends part of its "clean
window" outside a valid operating state,
that baseline — and every `Rf_run`/`U_relative` value derived from it for the whole run
— is biased. `_recompute_clean_baseline` redoes the median using only in-service points and
overwrites `{hx}_U_clean_run`/`_U_relative`/`_Rf_run` in Feature_calculated.csv in place,
so both the exported features and the rate regression below use the corrected baseline.

Run: python pipeline/compute_fouling_rate.py
"""
import os, sys
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
NB   = REPO / 'notebooks'
DATA = Path(os.environ.get('CPHT_DATA_DIR', r'C:\Desktop\Bangchak Internship 2026\Data'))
OUT  = DATA / 'Fouling_Rate_By_Run.csv'
SUBOUT = DATA / 'Fouling_Rate_By_Subrun.csv'
FEAT = DATA / 'Feature_calculated.csv'
sys.path.append(str(REPO))
from src.validation import nb_audit as A
from src.domain.config import HX_CONFIG
from src.models.clean_baseline import calculate_clean_baseline

CLEAN_WINDOW_DAYS = 30   # must match notebook 02 §3.4 (first N days of a run = clean baseline)


def _recompute_clean_baseline(feat, ost, hx_config):
    """Redo U_clean_run/U_relative/Rf_run per run using the in-service state mask.

    Same approved-window median logic as notebook 02 §3.4, restricted to timestamps
    where the shell is actually NORMAL/SUBSTITUTE_ACTIVE/PARALLEL (not OFF/BYPASS and
    not mid-clean) — Operating_State.csv wasn't available when notebook 02 first
    computed these columns. An insufficient clean window is invalidated; records later
    in the run are never used as a fallback. Mutates `feat` in place and returns the
    list of HX actually redone.
    """
    redone = []
    for hx in hx_config:
        u_col, rid_col, dod_col = f'{hx}_U', f'{hx}_run_id', f'{hx}_days_on_duty'
        ucr_col, urel_col, rf_col = f'{hx}_U_clean_run', f'{hx}_U_relative', f'{hx}_Rf_run'
        if u_col not in feat or rid_col not in feat or dod_col not in feat:
            continue

        u, rid, dod = feat[u_col], feat[rid_col], feat[dod_col]
        in_service = (ost[hx].isin(A.INSERVICE_STATES) if hx in ost.columns
                      else pd.Series(True, index=feat.index))

        u_clean_run = pd.Series(np.nan, index=feat.index)
        for run in sorted(rid[rid > 0].unique()):
            m = (rid == run).values
            run_index = feat.index[m]
            start = run_index.min()
            end = min(run_index.max(), start + pd.Timedelta(days=CLEAN_WINDOW_DAYS))
            baseline = calculate_clean_baseline(
                u, feat.index, start, end,
                operating_valid=m & in_service.values,
                method="median", min_valid_records=5,
            )
            val = baseline["clean_ua"] if baseline["quality"]["is_valid"] else np.nan
            u_clean_run[m] = val

        feat[ucr_col] = u_clean_run
        feat[urel_col] = (u / u_clean_run).clip(lower=0.0, upper=2.0)
        feat[rf_col] = (1.0 / u) - (1.0 / u_clean_run)
        redone.append(hx)
    return redone


def _label_fouling_phases(feat, hx_config):
    """Write `{hx}_fouling_phase` (INITIATION/AFTER_INITIATION) per HX using
    nb_audit.label_fouling_phase -- the SAME INITIATION_LAG_DAYS boundary
    robust_fouling_rate already uses internally to exclude early-run points, made an
    explicit, visible column instead of a silent regression-input filter. See
    label_fouling_phase's docstring for why this doesn't change the rate fit itself.
    Mutates `feat` in place; returns the list of HX actually labeled."""
    labeled = []
    for hx in hx_config:
        dod_col = f'{hx}_days_on_duty'
        if dod_col not in feat:
            continue
        feat[f'{hx}_fouling_phase'] = A.label_fouling_phase(feat[dod_col])
        labeled.append(hx)
    return labeled


def main():
    feat = pd.read_csv(FEAT, parse_dates=['Timestamp']).set_index('Timestamp')
    ost_path = DATA / 'Operating_State.csv'
    ost = (pd.read_csv(ost_path, parse_dates=['Timestamp']).set_index('Timestamp')
           if ost_path.exists() else None)
    if ost is None:
        print('WARNING: Operating_State.csv missing — falling back to no state mask '
              '(rates and baseline will be less reliable; run 2a first).')
        phase_labeled = _label_fouling_phases(feat, HX_CONFIG)
        # fouling_baseline_corrected stays False (as notebook 02 left it) -- the
        # in-service-masked correction below did NOT run, so U_clean_run/U_relative/
        # Rf_run are still the physical-mask-only version.
        feat.to_csv(FEAT)
        print(f'Labeled INITIATION/AFTER_INITIATION phase for {len(phase_labeled)}/{len(HX_CONFIG)} HX '
              f'-> overwrote {FEAT.name} (fouling_baseline_corrected=False, no state mask applied)')
    else:
        redone = _recompute_clean_baseline(feat, ost, HX_CONFIG)
        phase_labeled = _label_fouling_phases(feat, HX_CONFIG)
        feat['fouling_baseline_corrected'] = True
        feat.to_csv(FEAT)
        print(f'Recomputed in-service-masked U_clean_run/U_relative/Rf_run for '
              f'{len(redone)}/{len(HX_CONFIG)} HX; labeled fouling phase for '
              f'{len(phase_labeled)}/{len(HX_CONFIG)} HX -> overwrote {FEAT.name} '
              f'(fouling_baseline_corrected=True)')

    rows = []
    for hx in HX_CONFIG:
        rid_c, dod_c, ur_c = f'{hx}_run_id', f'{hx}_days_on_duty', f'{hx}_U_relative'
        if rid_c not in feat or ur_c not in feat:
            continue
        rid = feat[rid_c]; dod = feat[dod_c]; ur = feat[ur_c]
        rf = feat.get(f'{hx}_Rf_run'); ucr = feat.get(f'{hx}_U_clean_run')
        evt = feat.get(f'{hx}_event_type')
        state = ost[hx] if (ost is not None and hx in ost.columns) else None

        for run in sorted(rid.dropna().unique()):
            m = (rid == run).values
            res = A.robust_fouling_rate(
                dod[m], ur[m],
                rf_run=(rf[m] if rf is not None else None),
                state=(state[m] if state is not None else None))
            # back-compat metadata columns (kept so existing consumers don't break)
            idx = feat.index[m]
            run_start = idx.min()
            dur = int((dod[m].dropna().max() if dod[m].notna().any() else 0))
            start_evt = None
            if evt is not None and evt[m].notna().any():
                start_evt = str(evt[m].dropna().iloc[0])
            # keep the raw robust slope for transparency, but NULL the primary rate columns
            # for runs that fail the physics/reliability gate — so every downstream consumer
            # that does `dropna(subset=['dRf_per_month'])` (e.g. 2d) auto-excludes them
            # without any notebook edit, and no unphysical number ever reaches ranking.
            raw_rf = res['dRf_per_day']
            reliable = bool(res['reliable'])
            primary_rf = raw_rf if reliable else None
            # dUrel_per_month: kept for consumers not yet migrated off the old primary metric
            # (export_cleaning_history.py, export_hx_timeseries.py, _build_cleaning_plan_notebook.py,
            # the dashboard) — now derived from the SECONDARY Theil-Sen U_relative cross-check
            # (res['dUrel_per_day']), gated by the same Rf-based `reliable` flag, not its own fit.
            raw_urel = res['dUrel_per_day']
            primary_urel = raw_urel if reliable else None
            res.update(
                HX=hx, Run=int(run),
                Start_event=start_evt,
                Run_start=str(run_start.date()),
                Duration_days=dur,
                U_clean_run=(round(float(ucr[m].dropna().iloc[0]), 2)
                             if ucr is not None and ucr[m].notna().any() else None),
                dRf_per_day_raw=raw_rf,
                dRf_per_day=primary_rf,
                dRf_per_month=(round(primary_rf * 30, 6) if primary_rf is not None else None),
                dUrel_per_day=primary_urel,
                dUrel_per_month=(round(primary_urel * 30, 4) if primary_urel is not None else None),
                p_value=None,  # Theil-Sen: use CI (dRf_ci_lo/hi) instead of a p-value
            )
            rows.append(res)

    cols = ['HX', 'Run', 'Start_event', 'Run_start', 'Duration_days', 'U_clean_run',
            'dRf_per_day', 'intercept', 'dRf_per_month', 'dRf_per_day_raw', 'dRf_ci_lo', 'dRf_ci_hi',
            'dRf_per_day_recent', 'dUrel_per_day', 'dUrel_per_month', 'R2', 'p_value', 'N_regression_pts',
            'span_days', 'normal_frac', 'n_winsorized', 'split_after_day',
            # curve-fit diagnostics (curve_models.py AIC race on Rf -- linear/asymptotic/power,
            # see nb_audit.robust_fouling_rate):
            # dRf_per_day (above) IS dRf_per_day_tail — kept as one column so existing
            # consumers don't need to change; dRf_per_day_wholerun is the whole-run single-line
            # Theil-Sen estimate, kept as a secondary cross-check. dUrel_per_day_tail/_wholerun
            # are now just the plain Theil-Sen U_relative slope (secondary sign cross-check only).
            'model_selected', 'dRf_per_day_tail', 'dRf_per_day_wholerun',
            'dUrel_per_day_tail', 'dUrel_per_day_wholerun',
            'tau_days', 'A_asymp', 'Rf_inf_asymp', 'asymp_aic', 'linear_aic', 'power_aic', 'R2_model',
            'sign_change_rate', 'last_day_on_duty',
            'reliable', 'rate_flag']
    df = pd.DataFrame(rows).reindex(columns=cols)
    df.to_csv(OUT, index=False)

    # Diagnostic-only sidecar: every intra-run sub-segment (split at EVERY minor-clean
    # recovery jump, not just the last one) for visualization/QA in notebook 02. This does
    # NOT feed ranking/RUL/dashboard -- the authoritative per-run rate above (last segment
    # only) is unaffected; nothing else currently reads this file.
    sub_rows = []
    for hx in HX_CONFIG:
        rid_c, dod_c, ur_c = f'{hx}_run_id', f'{hx}_days_on_duty', f'{hx}_U_relative'
        if rid_c not in feat or ur_c not in feat:
            continue
        rid = feat[rid_c]; dod = feat[dod_c]; ur = feat[ur_c]
        rf = feat.get(f'{hx}_Rf_run')
        state = ost[hx] if (ost is not None and hx in ost.columns) else None
        if rf is None:
            continue
        for run in sorted(rid.dropna().unique()):
            m = (rid == run).values
            idx = feat.index[m]
            run_start = idx.min()
            segs = A.segment_fouling_rates(
                dod[m], ur[m], rf[m],
                state=(state[m] if state is not None else None))
            for seg in segs:
                seg.update(HX=hx, Run=int(run), Run_start=str(run_start.date()))
                sub_rows.append(seg)

    sub_cols = ['HX', 'Run', 'seg_index', 'Run_start', 'seg_start_day', 'seg_end_day',
                'N_regression_pts', 'dRf_per_day', 'dRf_per_day_tail', 'dRf_per_day_wholerun',
                'model_selected', 'tau_days', 'A_asymp', 'Rf_inf_asymp', 'R2_model',
                'sign_change_rate', 'last_day_on_duty', 'reliable', 'rate_flag']
    sub_df = pd.DataFrame(sub_rows).reindex(columns=sub_cols)
    sub_df.to_csv(SUBOUT, index=False)

    rel = df[df['reliable'] == True]  # noqa: E712
    n_bad = int((rel['dRf_per_day'] <= 0).sum())
    assert n_bad == 0, f'PHYSICAL INVARIANT VIOLATED: {n_bad} reliable run(s) with dRf_per_day <= 0'
    miss = sorted(set(df['HX']) - set(rel['HX']))
    print(f'Wrote {OUT.name}: {len(df)} runs, {len(rel)} reliable (dRf/dt>0, physical), '
          f'{len(df) - len(rel)} flagged')
    print(f'Wrote {SUBOUT.name}: {len(sub_df)} sub-segments (diagnostic only, splits at every '
          f'minor-clean recovery jump; not read by any ranking/RUL/dashboard consumer)')
    print('  flags:', df['rate_flag'].value_counts().to_dict())
    if miss:
        print(f'  HX with no reliable run (rate falls back to partner/None downstream): {miss}')
    print('  physical invariant OK: 0 reliable runs with dRf_per_day <= 0')

    try:
        _hot_cold_balance_diagnostic()
    except Exception as e:
        print(f'  (hot/cold energy-balance diagnostic skipped: {e})')


def _hot_cold_balance_diagnostic():
    """Diagnostic-only, NOT a gate: duty (Q) throughout this pipeline is computed from the
    crude/cold side only (see notebooks/02_feature_engineering.ipynb, cpht_features.py) —
    there is no cross-check against the hot/residue side, so a bad hot-side flow tag or an
    unstated heat-loss/vaporization assumption would never be caught. This reports the
    median |Q_hot - Q_cold| / Q_cold discrepancy per HX where both sides have flow tags
    (cpht_features.HX_CONFIG has hot-side tags; the notebook-02 config used for the main
    feature file does not). Residue-side Cp/density are approximated with the same crude
    correlation (crude_properties.py) for lack of a residue-specific one, so this is a rough
    plausibility check, not a precise energy balance — never used to filter/gate any run."""
    import sys as _sys
    _sys.path.append(str(REPO))
    from src.features import heat_duty as F
    from src.features import crude_properties as CProp
    proc = pd.read_csv(DATA / 'Process_information_cleaned.csv', parse_dates=['Timestamp']).set_index('Timestamp')
    crude = pd.read_csv(DATA / 'Crude_property_profiled.csv', parse_dates=['Date']).set_index('Date')
    sg = (crude['SG_15_6C'].reindex(proc.index).ffill().bfill()
          if 'SG_15_6C' in crude.columns else pd.Series(0.92, index=proc.index))

    rows = []
    for hx, cfg in F.HX_CONFIG.items():
        s = F.parse_hx(cfg)
        need = ('cold_flow', 'cold_in', 'cold_out', 'hot_flow', 'hot_in', 'hot_out')
        if not all(s.get(k) for k in need) or not all(s[k] in proc.columns for k in need):
            continue
        t_cold = (proc[s['cold_in']] + proc[s['cold_out']]) / 2
        cp_c, rho_c = CProp.cp_rho_crude(t_cold, sg)
        Q_cold = rho_c * proc[s['cold_flow']] * cp_c * (proc[s['cold_out']] - proc[s['cold_in']]) / 3600
        t_hot = (proc[s['hot_in']] + proc[s['hot_out']]) / 2
        cp_h, rho_h = CProp.cp_rho_crude(t_hot, sg)
        Q_hot = rho_h * proc[s['hot_flow']] * cp_h * (proc[s['hot_in']] - proc[s['hot_out']]) / 3600
        m = Q_cold.abs() > 50   # ignore near-zero/idle rows (division blows up the % metric)
        if m.sum() < 30:
            continue
        disc = float(((Q_hot[m] - Q_cold[m]).abs() / Q_cold[m].abs()).median() * 100)
        rows.append((hx, round(disc, 1), int(m.sum())))

    if rows:
        print('  hot/cold energy-balance check (diagnostic only, NOT a gate; residue-side '
              'Cp/rho approximated with the crude correlation -> plausibility check, not precise):')
        for hx, disc, n in sorted(rows, key=lambda r: -r[1]):
            print(f'    {hx}: median |Q_hot-Q_cold|/Q_cold = {disc}% (n={n})' + (' [!]' if disc > 30 else ''))


if __name__ == '__main__':
    main()
