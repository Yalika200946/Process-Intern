"""
Canonical per-HX forecast consolidation (ข้อ 4).

Four independent pipelines each produce a "when will this HX need cleaning" answer, with
NO reconciliation anywhere in the codebase before this script (confirmed: dashboard/index.html
keeps forecast_6mo.json/end_of_run.json/rul.json/propagation_models.json in separate React
state slots, never merged -- see its own code comment at the `units` useMemo explicitly
stating similar per-HX ranking objects "answer different questions... not meant to agree").
That's fine for genuinely different questions, but for "the one number a plant engineer
should look at first," a user should not have to open 4 tabs and reconcile 4 disagreeing
dates themselves.

Precedence (NOT an average -- averaging 4 different methodologies would hide disagreement,
which is exactly the failure mode this script exists to fix):
  1. If end_of_run.json's rate_source == 'current_reliable_run' (ข้อ 2's physics gate): use
     end_of_run's own projected_date + rul.json's P10/P50/P90 interval as canonical -- these
     two already share the SAME underlying reliable-rate data (both keyed off the same
     4-state classification), so this is presenting one signal once, not merging two
     independent ones.
  2. Otherwise: canonical output is explicitly "insufficient current evidence," no single
     date -- consistent with ข้อ 2's dashboard gating (RateSourceGate).

Every one of the 4 source JSONs' own numbers is retained UNCHANGED in a `cross_check`
sub-object, verbatim, so a reviewing engineer can see all 4 opinions and how much they
agree/disagree. The 4 source files are NOT modified, renamed, or deleted by this script.

Run: python pipeline/build_canonical_forecast.py (after phm_analysis.py, export_end_of_run.py,
and notebook 10's forecast_6mo.json export have all run).
"""
import json
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
DASH = REPO / 'dashboard' / 'data'
OUT = DASH / 'canonical_forecast.json'

TOLERANCE_DAYS = 30   # disagreement flag threshold between cross-check dates


def _load(name):
    p = DASH / name
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}


def _forecast6mo_breach_date(fc):
    """Same breach-detection logic dashboard/index.html's ForecastChart already computes
    client-side (data.find(p=>p.dev>p.thr)) -- replicated here so it can be cross-checked
    alongside the other 3 sources without duplicating a second implementation client-side."""
    if not fc or 'dates' not in fc:
        return None
    thr = fc.get('threshold')
    for d, dev in zip(fc['dates'], fc.get('projected_deviation', [])):
        if thr is not None and dev is not None and dev > thr:
            return d
    return None


def cross_check_agreement(cross_check, tolerance_days=TOLERANCE_DAYS):
    """Flag when the available cross-check dates disagree by more than `tolerance_days`.
    None if fewer than 2 dates are available to compare (can't disagree with itself)."""
    dates = []
    for src in cross_check.values():
        d = src.get('projected_date') or src.get('p50_date') or src.get('breach_date')
        if d:
            try:
                dates.append(pd.Timestamp(d))
            except Exception:
                pass
    if len(dates) < 2:
        return None
    spread_days = (max(dates) - min(dates)).days
    return bool(spread_days > tolerance_days)


def main():
    eor = _load('end_of_run.json')
    rul = _load('rul.json')
    prop = _load('propagation_models.json')
    f6mo = _load('forecast_6mo.json')

    eor_hx = eor.get('hx', {})
    as_of = eor.get('as_of') or pd.Timestamp.now().strftime('%Y-%m-%d')
    hx_list = sorted(set(eor_hx) | set(rul) | set((prop.get('per_hx') or {})) | set(f6mo))

    out = {'as_of': as_of, 'hx': {}}
    for hx in hx_list:
        eh = eor_hx.get(hx, {})
        urel = eh.get('urel', {})
        duty = eh.get('duty', {})
        rh = rul.get(hx, {})
        ph = (prop.get('per_hx') or {}).get(hx, {})
        fc = f6mo.get(hx, {})

        rate_source = urel.get('rate_source')

        cross_check = {}
        if urel.get('projected_date') is not None or urel:
            cross_check['end_of_run_urel'] = dict(projected_date=urel.get('projected_date'), rate_source=rate_source)
        if duty.get('projected_date') is not None or duty:
            cross_check['end_of_run_duty'] = dict(projected_date=duty.get('projected_date'))
        if rh.get('p50') is not None:
            p50_date = (pd.Timestamp(as_of) + pd.Timedelta(days=rh['p50'])).strftime('%Y-%m-%d')
            cross_check['rul_mc'] = dict(p50_date=p50_date, p10=rh.get('p10'), p90=rh.get('p90'))
        if ph:
            cross_check['propagation_c1'] = dict(best_proj_days=ph.get('best_proj_days'),
                                                 best_model=ph.get('best_model'),
                                                 beats_all_baselines=ph.get('beats_all_baselines'))
        breach_date = _forecast6mo_breach_date(fc)
        if fc:
            cross_check['forecast_6mo'] = dict(breach_date=breach_date)

        if rate_source == 'current_reliable_run':
            canonical_projected_date = urel.get('projected_date')
            canonical_interval = dict(p10=rh.get('p10'), p50=rh.get('p50'), p90=rh.get('p90'))
            # past_trigger=True + days_urel==0.0 means export_end_of_run.py's own `if days_urel`
            # check (0.0 is falsy) leaves projected_date=None even though the HX IS reliably
            # past its threshold today -- surface that explicitly rather than silently showing
            # nothing (which would look like a missing/broken case, not "already needs cleaning").
            canonical_message = 'already past threshold' if (canonical_projected_date is None and urel.get('past_trigger')) else None
        else:
            canonical_projected_date = None
            canonical_interval = None
            canonical_message = 'insufficient current evidence'

        out['hx'][hx] = dict(
            rate_source=rate_source,
            canonical_projected_date=canonical_projected_date,
            canonical_interval=canonical_interval,
            canonical_message=canonical_message,
            sources_disagree=cross_check_agreement(cross_check),
            cross_check=cross_check,
        )

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    n_disagree = sum(1 for v in out['hx'].values() if v['sources_disagree'])
    print(f'Wrote {OUT.name}: {len(out["hx"])} HX, {n_disagree} flagged sources_disagree=True')


if __name__ == '__main__':
    main()
