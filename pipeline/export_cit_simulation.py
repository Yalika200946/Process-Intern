"""
CIT sawtooth simulation for a chosen target CIT — powers the cleaning-plan wizard's
Step 1 ("เลือกอุณหภูมิเป้าหมาย"). Deliberately NOT a new model: it reuses
cleaning_scheduler_network.compute_schedule() (the same SLSQP moving-window network
optimizer that produces cleaning_schedule_v2.json / cleaning_plan.json) by passing the
chosen target through as the SAME max_cit_deficit_C hard ceiling the dashboard's
existing "CIT floor" override already uses (see backend/server.py's
cit_floor_override.json). So the sawtooth this exports is the trajectory that would
actually be realized if the target were adopted, not a cosmetic overlay on top of a
different, unconnected model.

target_cit_C (absolute °C) is converted to a deficit ceiling via
max_deficit = current_cit - target_cit_C, because compute_schedule (and the existing
cit_floor_override.json convention) works in deficit-below-clean space, not absolute
CIT. The absolute-CIT line shown to the engineer is current_cit - deficit(t).

Per-HX contribution lines are NOT re-optimized — they're reconstructed by replaying
the optimizer's own committed clean dates (per_hx[i].next_dates) through the identical
reset-then-grow recurrence documented in cleaning_scheduler_network._deviation_trajectory
(dev(t)=0 if cleaned else dev(t-1)+r*PERIOD_DAYS). This exactly reproduces
cit_deficit_trajectory_C when summed (risk_mult only biases the optimizer's own
crew-slot choice, it is not applied to the reported deficit — see
realized_deficit_trajectory), so the per-HX breakdown is consistent with the network
total, not a second independent estimate.

Run: python pipeline/export_cit_simulation.py [--target-cit 250]
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / 'dashboard' / 'data'
OUT = DATA / 'cit_simulation.json'
sys.path.append(str(REPO / 'pipeline'))
import cleaning_scheduler_network as NS  # noqa: E402


def _load(name, default=None):
    p = DATA / name
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else default


def post_tam_ceiling_C(tam_analysis):
    """Highest CIT (SOR) ever measured immediately after a TAM cleaning event — the
    ceiling the sawtooth should never exceed, since online cleans only ever recover
    PART of what a full TAM turnaround does (see the plan's "ไม่ได้สูงเท่าตอนหลัง TAM"
    requirement)."""
    cycles = (tam_analysis or {}).get('cycles') or []
    tam_dates = set((tam_analysis or {}).get('tam_dates') or [])
    post_tam_sors = [c['SOR'] for i, c in enumerate(cycles)
                      if c.get('SOR') is not None
                      and (c['start'] in tam_dates or (i > 0 and cycles[i - 1].get('event_at_end') == 'TAM'))]
    if post_tam_sors:
        return max(post_tam_sors)
    all_sors = [c['SOR'] for c in cycles if c.get('SOR') is not None]
    return max(all_sors) if all_sors else None


def build_simulation(target_cit_C=None, tam_dates=None, tam_years=None):
    """`target_cit_C`: floor CIT to maintain throughout the horizon (converted to a
    max_cit_deficit_C ceiling on compute_schedule, same as the dashboard's existing CIT-floor
    override) — NOT "only at the TAM date"; the optimizer keeps CIT at/above this the whole
    cycle, which is what the real historical sawtooth (repeated partial online cleans between
    TAMs, not one long decline) already shows is achievable. `tam_years`: cycle length in years
    from the next confirmed TAM (cleaning_scheduler_network.NEXT_TAM) — lets the engineer compare
    "same floor, 3-year cycle" vs "same floor, 4-year cycle" (reuses the identical machinery as
    compare_tam_cycles's 3yr-vs-4yr comparison, just for one horizon at a time). Ignored if
    `tam_dates` is passed explicitly."""
    econ = _load('economics.json', {})
    chist = _load('cleaning_history.json', {'hx': {}})
    logi = _load('cleaning_logistics.json', {'hx': []})
    topo = _load('pfd_topology.json', {})
    eng_priority = _load('engineering_priority.json', [])
    tam_analysis = _load('tam_analysis.json', {})

    current_cit = next((x['value'] for x in (topo.get('furnace') or []) if x.get('key') == 'CIT'), None)
    if current_cit is None:
        raise RuntimeError('pfd_topology.json has no furnace CIT value — '
                            'run src/reporting/dashboard_topology.py first')

    if tam_dates is None and tam_years is not None:
        tam_dates = [NS.NEXT_TAM, NS.NEXT_TAM + pd.DateOffset(years=tam_years)]

    ceiling = post_tam_ceiling_C(tam_analysis)
    max_deficit = max(0.0, current_cit - target_cit_C) if target_cit_C is not None else None

    sched = NS.compute_schedule(econ, chist, logi, tam_dates=tam_dates,
                                 max_cit_deficit_C=max_deficit, topo=topo, eng_priority=eng_priority)

    as_of = pd.Timestamp(sched['as_of'])
    n_periods = len(sched['cit_deficit_trajectory_C'])
    dates = [str((as_of + pd.Timedelta(days=(t + 1) * NS.PERIOD_DAYS)).date()) for t in range(n_periods)]
    cit_trajectory = [round(current_cit - d, 2) for d in sched['cit_deficit_trajectory_C']]

    per_hx_deviation = {}
    for p in sched['per_hx']:
        if not p.get('online'):
            continue
        r = p['r_C_per_day']
        clean_set = set(p.get('next_dates') or [])
        dev, series = 0.0, []
        for dt in dates:
            dev = 0.0 if dt in clean_set else dev + r * NS.PERIOD_DAYS
            series.append(round(dev, 4))
        per_hx_deviation[p['HX']] = series

    clean_events = [dict(HX=t['HX'], date=t['date']) for t in sched['timeline'] if t['kind'] == 'ONLINE_V2']

    return dict(
        as_of=sched['as_of'],
        current_cit_C=round(current_cit, 2),
        target_cit_C=(round(target_cit_C, 2) if target_cit_C is not None else None),
        max_deficit_C_applied=max_deficit,
        post_tam_ceiling_C=(round(ceiling, 2) if ceiling is not None else None),
        tam_dates=sched['tam_dates'],
        tam_years_applied=tam_years,
        dates=dates,
        cit_trajectory_C=cit_trajectory,
        deficit_trajectory_C=sched['cit_deficit_trajectory_C'],
        per_hx_deviation_C=per_hx_deviation,
        clean_events=clean_events,
        constraint_satisfied=sched['constraint_satisfied'],
        max_realized_deficit_C=sched['max_realized_deficit_C'],
        max_cleans_per_year_per_hx=sched['max_cleans_per_year_per_hx'],
        method=("Absolute-CIT sawtooth = current_cit − network CIT-deficit trajectory from "
                "pipeline/cleaning_scheduler_network.compute_schedule() (same SLSQP moving-window "
                "optimizer as cleaning_schedule_v2.json / cleaning_plan.json, not a separate model). "
                "target_cit_C is passed through as max_cit_deficit_C=(current_cit−target_cit_C), the "
                "same deficit-ceiling convention as the dashboard's existing CIT-floor override "
                "(cit_floor_override.json), so this is the schedule that would actually be committed "
                "if the target were adopted. Per-HX lines replay the optimizer's own committed clean "
                "dates + measured rate r_C_per_day through the identical reset-then-grow recurrence "
                "it uses internally."),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--target-cit', type=float, default=None,
                     help='Target CIT (degC) to simulate toward; omit for unconstrained')
    ap.add_argument('--tam-years', type=int, default=None,
                     help='TAM cycle length in years from the next confirmed TAM (e.g. 3 or 4)')
    args = ap.parse_args()
    out = build_simulation(target_cit_C=args.target_cit, tam_years=args.tam_years)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'Wrote {OUT.name}: current={out["current_cit_C"]} target={out["target_cit_C"]} '
          f'ceiling={out["post_tam_ceiling_C"]} periods={len(out["dates"])} '
          f'constraint_satisfied={out["constraint_satisfied"]}')


if __name__ == '__main__':
    main()
