"""
Network-level cleaning schedule (v2) — moving-window joint optimization across all
online-capable HX, adapted from:

  Dekebo, S.B.; Oh, G.-T.; Lee, M.-W. "Cleaning Schedule Optimization of Heat
  Exchanger Network Using Moving Window Decision-Making Algorithm."
  Appl. Sci. 2023, 13, 604. https://doi.org/10.3390/app13010604
  (itself an extension of Al Ismaili, Lee, Wilson, Vassiliadis, Comput. Chem.
  Eng. 2018, 111, 1-15 — the multi-period optimal-control-problem framework.)

WHY v1 (pipeline/cleaning_scheduler.py) isn't enough: it optimizes each HX's
cleaning interval independently (T* = sqrt(2C/kr)), ignoring that cleaning one
HX changes downstream inlet temperatures and hence the marginal value of
cleaning others. The paper's moving-window OCP schedules the whole network
jointly and — critically — solves a SMALL sliding window at each step instead
of the full horizon at once, because (their Table 2) a fixed-horizon solve
stops converging to a bang-bang (0/1) cleaning decision once the horizon
exceeds ~30 months.

HORIZON now spans BOTH confirmed TAM cycles (2028-06-01, then ~2032-06-01,
~4yr apart — see `_parse_tam_dates`), not just the near one: a schedule that
only looked as far as 2028 had no way to see whether it was spending its
online-cleaning budget in a way that left a sane cadence for 2028-2032. This
pushes the total horizon well past the paper's ~30-month convergence-risk
threshold for a FIXED-horizon solve, but the moving-window approach is immune
to that by construction — it only ever solves WINDOW_CANDIDATES-sized windows
and rolls forward, so a longer total horizon doesn't reintroduce the
convergence problem; it's the reason this module (not v1, not a single
fixed-horizon MINLP) was the right fit for a multi-cycle horizon at all.

WHERE THIS DEVIATES FROM THE PAPER (documented, not hidden): the paper builds a
full dynamic epsilon-NTU thermal network (their Eq. 1-9: alpha=UA/(Fh*Cph),
each HX's outlet feeds the next HX's inlet) requiring per-HX design UA/area.
Nameplate UA/area DOES exist for this plant (Data Sheet Heat Exchanger.xlsx)
but reflects DESIGN conditions, not the current fouled/measured state -- this
project has repeatedly found real U_clean differs from nameplate (see
Fouling_Rate_By_Run.csv's per-run U_clean_run, always fit from data, never
nameplate). Simulating a whole thermal DAE network off unvalidated nameplate
UA would be a large, silent assumption. Instead this module uses REDUCED-FORM
coupling: each HX's CIT-equivalent deviation grows at its own MEASURED rate
r_hx [degC/day] (identical r to v1, from cleaning_history.json's audited
sawtooth recoveries), and the network's total CIT deficit is simply their sum
-- these r values were fit directly against real CIT, so whatever cross-HX
thermal coupling exists in reality is already baked into them empirically.
This is a deliberate simplification, not an oversight; see METHODOLOGY.md.

Objective per window (paper Eq. 10, CE/eta_f replaced by the plant's own
Energy-Saving-Benefit rate k = STD_ENERGY x Feed_KBD x NG_PRICE, same k v1
uses):

    Obj = sum_t [ k * 30 * CIT_deficit_total(t) ]  +  sum_hx sum_t Ccost_hx * y[hx,t]

    CIT_deficit_total(t) = sum_hx deviation_hx(t)               [degC]
    deviation_hx(t) = 0                      if y[hx,t] = 1 (cleaned this period)
                     = deviation_hx(t-1) + r_hx*30   otherwise

y[hx,t] relaxed to continuous [0,1] (1=clean) and solved with SLSQP per window;
cleaning enters the state update in a way that (per the paper) tends to a
bang-bang solution, so committing round(y) for only the first period of each
window is a reasonable, auditable rounding rule when convergence isn't exact.

Run: python pipeline/cleaning_scheduler_network.py
"""
import os, sys, json, math
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import minimize

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / 'dashboard' / 'data'
OUT = DATA / 'cleaning_schedule_v2.json'
sys.path.append(str(REPO / 'pipeline'))
from export_economics import CLEANING_COST_BY_HX, DEFAULT_CLEANING_COST

def _parse_tam_dates():
    """TAM dates, confirmed by the plant: the near TAM is 2028-06-01; the plant's TAM
    cycle is ~4 years, so the following TAM (~2032-06-01) is also included so the
    scheduler's horizon — and hence its annual cleaning-frequency cap — spans BOTH
    cycles. Without this, a moving-window solve whose horizon stops at 2028 has no
    visibility into 2028-2032 at all, which risks front-loading online cleans before
    2028 with nothing informing whether that leaves a sensible cadence for the next
    cycle. Override with CPHT_TAM_DATES='YYYY-MM-DD,YYYY-MM-DD,...' (chronological);
    CPHT_NEXT_TAM (single date, legacy) is still honoured as the first date if
    CPHT_TAM_DATES isn't set."""
    raw = os.environ.get('CPHT_TAM_DATES')
    if raw:
        dates = sorted(pd.Timestamp(d.strip()) for d in raw.split(',') if d.strip())
    else:
        dates = [pd.Timestamp(os.environ.get('CPHT_NEXT_TAM', '2028-06-01')),
                  pd.Timestamp('2032-06-01')]
    return dates


TAM_DATES = _parse_tam_dates()
NEXT_TAM = TAM_DATES[0]                # kept for backward compatibility (near-term TAM)
PERIOD_DAYS = 30                       # one "month" period, same discretization as the paper
MIN_RATE = 1e-4                        # degC/day below this -> HX excluded from the coupled model
WINDOW_CANDIDATES = [2, 3, 4, 5, 6]    # moving-window sizes to sweep (paper Fig.3/Table 2)
MAX_ONLINE_CLEANS_PER_PERIOD = int(os.environ.get('CPHT_MAX_CLEANS_PER_PERIOD', 2))  # ASSUMED — รอวิศวกร (crew capacity)
MAX_CLEANS_PER_YEAR = 4                # hard cap per HX — real-world logistics ceiling (4/yr only in an emergency)
PERIODS_PER_YEAR = round(365 / PERIOD_DAYS)


def _load(name, default=None):
    p = DATA / name
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else default


def build_hx_state(econ, chist, logi):
    """Per-HX: online-capable?, cleaning cost, measured rate r [degC/day], current deviation [degC]."""
    econ_by = {r['HX']: r for r in econ.get('per_hx', [])}
    logi_by = {r['HX']: r for r in logi.get('hx', [])}
    hx_all = sorted(set(logi_by) | set(econ_by))
    out = {}
    for hx in hx_all:
        lg = logi_by.get(hx, {})
        online = bool(lg.get('bypass')) or bool(lg.get('swap_capable'))
        e = econ_by.get(hx)
        dC_full = e['cit_gain_C'] if e else None
        # ONLINE_PARTIAL: only some shells bypassable -> online clean recovers a fraction
        duty_frac = lg.get('duty_fraction', 1.0) if lg.get('duty_fraction') is not None else 1.0
        dC = (dC_full * duty_frac) if dC_full else dC_full
        cost = (e.get('cleaning_cost') if e else None) or CLEANING_COST_BY_HX.get(hx, DEFAULT_CLEANING_COST)

        h = chist.get('hx', {}).get(hx, {})
        durs = [c['run_ended']['duration_days'] for c in h.get('cleans', [])
                if c.get('run_ended') and c['run_ended'].get('duration_days')]
        if durs and dC:
            r = dC / float(np.median(durs))
        else:
            r = 0.0
        out[hx] = dict(online=online, cost=cost, r=max(0.0, r),
                       deviation0=max(0.0, dC) if dC else 0.0)
    return out


OBJ_SCALE = 1e-6   # THB -> million-THB, purely for the SLSQP solve (see window_objective docstring)


def window_objective(y_flat, dev0, r, cost, k_per_day, n_hx, n_t):
    """Returns the objective in MILLION THB, not raw THB. SLSQP's default finite-
    difference gradient step is a small RELATIVE step (~1.5e-8 x scale of x, which
    is O(1) here since y in [0,1]) -- against a raw-THB objective of order 1e8 the
    resulting delta-f is right at the double-precision noise floor, so SLSQP was
    silently reporting "converged" at the untouched y=0 starting point without ever
    detecting the (very real, ~10x) improvement available by cleaning. Rescaling the
    objective to O(1-100) magnitude fixes the finite-difference gradient without
    changing where the optimum is; realized_cost() below still reports true THB."""
    y = y_flat.reshape(n_hx, n_t)
    dev = np.zeros((n_hx, n_t + 1))
    dev[:, 0] = dev0
    for t in range(n_t):
        dev[:, t + 1] = (dev[:, t] + r * PERIOD_DAYS) * (1 - y[:, t])
    cit_deficit_total = dev[:, 1:].sum(axis=0)                 # per period, after that period's action
    fuel = float(np.sum(k_per_day * PERIOD_DAYS * cit_deficit_total))
    clean = float(np.sum(cost[:, None] * y))
    return (fuel + clean) * OBJ_SCALE


def solve_window(dev0, r, cost, k_per_day, n_t):
    n_hx = len(dev0)
    if n_hx == 0 or n_t == 0:
        return np.zeros((n_hx, max(n_t, 0)))
    x0 = np.zeros(n_hx * n_t)
    bounds = [(0.0, 1.0)] * (n_hx * n_t)
    cons = []
    if MAX_ONLINE_CLEANS_PER_PERIOD and n_hx > 1:
        # sum over hx of y[:,t] <= cap, for each period t in the window.
        # SLSQP (unlike trust-constr) only accepts the OLD dict-style constraint
        # format {'type':'ineq','fun':...} -- a LinearConstraint object is silently
        # not enforced by SLSQP, which was letting every HX get cleaned at once.
        # 'ineq' means fun(x) >= 0, so encode cap - sum(y[:,t]) >= 0 per period t.
        for t in range(n_t):
            idx = np.arange(n_hx) * n_t + t
            cons.append({'type': 'ineq',
                        'fun': (lambda x, idx=idx: MAX_ONLINE_CLEANS_PER_PERIOD - x[idx].sum())})
    res = minimize(window_objective, x0, args=(dev0, r, cost, k_per_day, n_hx, n_t),
                   method='SLSQP', bounds=bounds, constraints=cons,
                   options=dict(maxiter=200, ftol=1e-6))
    return res.x.reshape(n_hx, n_t)


def run_schedule(hx_ids, dev0, r, cost, k_per_day, n_periods, window, tam_reset_periods=()):
    """Full moving-window schedule: solve window, commit period 0, roll forward.

    `tam_reset_periods`: period indices at which a TAM turnaround happens (cleans
    every HX, online-capable or not, back to fresh state) — an interior TAM boundary
    when the horizon spans more than one TAM cycle. This is a MANDATORY reset applied
    after the period's online-cleaning decision, not something the SLSQP window
    objective chooses; it does NOT count against MAX_CLEANS_PER_YEAR (a TAM turnaround
    is a different maintenance event from an online/crew-scheduled clean)."""
    n_hx = len(hx_ids)
    dev = np.array(dev0, dtype=float).copy()
    y_committed = np.zeros((n_hx, n_periods))
    for p in range(n_periods):
        w = min(window, n_periods - p)
        y_win = solve_window(dev, r, cost, k_per_day, w)
        frac = np.clip(y_win[:, 0], 0, 1)
        y0 = np.round(frac)                              # bang-bang rounding for the committed period

        # per-HX annual cap: block a clean this period for any HX that already hit
        # MAX_CLEANS_PER_YEAR within the trailing 12-month (PERIODS_PER_YEAR) window --
        # a real-world logistics ceiling, not something the SLSQP objective knows about.
        if MAX_CLEANS_PER_YEAR:
            lookback = max(0, p - PERIODS_PER_YEAR + 1)
            trailing_count = y_committed[:, lookback:p].sum(axis=1)
            over_cap = trailing_count >= MAX_CLEANS_PER_YEAR
            y0[over_cap] = 0

        # hard safety clamp: SLSQP's bang-bang convergence isn't exact, so independent
        # per-HX rounding can occasionally push the committed count 1 over the crew-
        # capacity cap even when the continuous solution respected it -- keep only the
        # highest-fraction HX up to the cap rather than silently violate a hard constraint.
        if MAX_ONLINE_CLEANS_PER_PERIOD and y0.sum() > MAX_ONLINE_CLEANS_PER_PERIOD:
            keep = np.argsort(-np.where(y0 > 0, frac, -1))[:MAX_ONLINE_CLEANS_PER_PERIOD]
            y0 = np.zeros_like(y0); y0[keep] = 1
        y_committed[:, p] = y0
        dev = (dev + r * PERIOD_DAYS) * (1 - y0)
        if p in tam_reset_periods:
            dev[:] = 0.0
    return y_committed


def realized_cost(dev0, r, cost, k_per_day, y_committed, tam_reset_periods=()):
    n_hx, n_t = y_committed.shape
    dev = np.array(dev0, dtype=float).copy()
    fuel, clean = 0.0, 0.0
    for t in range(n_t):
        dev = (dev + r * PERIOD_DAYS) * (1 - y_committed[:, t])
        if t in tam_reset_periods:
            dev[:] = 0.0
        fuel += float(np.sum(k_per_day * PERIOD_DAYS * dev))
        clean += float(np.sum(cost * y_committed[:, t]))
    return fuel + clean, fuel, clean


def v1_schedule_matrix(hx_ids, r, cost, dev0, n_periods, sched_v1):
    """Rebuild v1's committed y[hx,t] (0/1) from cleaning_schedule.json's per-HX dates,
    so it can be scored under the EXACT same objective as v2 (honest apples-to-apples)."""
    n_hx = len(hx_ids)
    y = np.zeros((n_hx, n_periods))
    if not sched_v1:
        return y
    as_of = pd.Timestamp(sched_v1['as_of'])
    by_hx = {p['HX']: p for p in sched_v1.get('per_hx', [])}
    for i, hx in enumerate(hx_ids):
        p = by_hx.get(hx)
        if not p:
            continue
        for d in (p.get('next_dates') or []):
            period = int((pd.Timestamp(d) - as_of).days // PERIOD_DAYS)
            if 0 <= period < n_periods:
                y[i, period] = 1
    return y


def compute_schedule(econ, chist, logi, sched_v1=None, tam_dates=None):
    """Core computation, reusable in-memory (e.g. by notebook 16 with cost overrides
    applied to `econ` before calling) as well as by `main()` below which writes the
    static dashboard/data/cleaning_schedule_v2.json. Returns the `out` dict.

    Horizon spans ALL of `tam_dates` (default TAM_DATES = [2028-06-01, 2032-06-01]),
    not just the first one — see `_parse_tam_dates` docstring for why. Every TAM date
    except the last is a mandatory reset (a turnaround cleans everything, online-
    capable or not) baked into `run_schedule`/`realized_cost` via `tam_reset_periods`."""
    tam_dates = sorted(tam_dates or TAM_DATES)
    last_tam = tam_dates[-1]

    pc = econ.get('plant_constants', {})
    feed_kbd = econ.get('feed_kbd') or 79.3
    k_per_day = pc.get('STD_ENERGY', 0.74) * feed_kbd * pc.get('NG_PRICE', 390)

    as_of = pd.Timestamp((chist.get('as_of')) or pd.Timestamp.now().strftime('%Y-%m-%d'))
    days_to_horizon_end = max(1, (last_tam - as_of).days)
    n_periods = max(1, math.ceil(days_to_horizon_end / PERIOD_DAYS))

    # interior TAM boundaries (all but the last, which is the horizon end) -> the period
    # index during which each one falls; run_schedule/realized_cost zero the deviation
    # right after that period since a TAM turnaround cleans every HX.
    tam_reset_periods = sorted({min(n_periods - 1, (d - as_of).days // PERIOD_DAYS)
                                 for d in tam_dates[:-1]})

    state = build_hx_state(econ, chist, logi)
    online_ids = sorted([hx for hx, s in state.items() if s['online'] and s['r'] >= MIN_RATE])
    tam_only_ids = sorted([hx for hx, s in state.items() if not s['online']])

    r = np.array([state[hx]['r'] for hx in online_ids])
    cost = np.array([state[hx]['cost'] for hx in online_ids])
    dev0 = np.array([state[hx]['deviation0'] for hx in online_ids])

    # --- window-size sweep (paper Fig. 3 / Table 2 methodology): pick SMW minimizing realized cost ---
    sweep = []
    best = None
    for w in WINDOW_CANDIDATES:
        y = run_schedule(online_ids, dev0, r, cost, k_per_day, n_periods, w, tam_reset_periods)
        total, fuel, clean = realized_cost(dev0, r, cost, k_per_day, y, tam_reset_periods)
        n_clean_actions = int(y.sum())
        sweep.append(dict(window_months=w, objective_thb=round(total), fuel_thb=round(fuel),
                          cleaning_thb=round(clean), n_cleaning_actions=n_clean_actions))
        if best is None or total < best[0]:
            best = (total, w, y)
    best_total, best_window, y_best = best

    # --- per-TAM-cycle breakdown (make the cross-cycle balance visible, not just implicit
    #     in the annual cap): count online-clean actions/cost per cycle boundary. ---
    cycle_bounds = [0] + [p + 1 for p in tam_reset_periods] + [n_periods]
    cycle_labels = [str(d.date()) for d in tam_dates]
    per_cycle = []
    for c, (lo, hi) in enumerate(zip(cycle_bounds[:-1], cycle_bounds[1:])):
        seg = y_best[:, lo:hi]
        per_cycle.append(dict(cycle_ends=cycle_labels[c], n_online_cleans=int(seg.sum()),
                              n_periods=hi - lo))

    # --- honest comparison vs v1 (independent T*), scored under the SAME objective ---
    # `cleaning_schedule.json` (v1) was only ever built out to the FIRST TAM date -- it has
    # no online-clean dates beyond that, not because v1's policy stops but because that's
    # the horizon it was generated for. Scoring it against the full multi-cycle horizon
    # would read those missing dates as "v1 stops cleaning after 2028", letting deviation
    # grow unbounded for years and making v1 look catastrophically worse than it really is
    # -- an artifact of an unfair comparison, not a real result. So the v1-vs-v2 comparison
    # is restricted to the horizon v1 actually covers (cycle 1); the full-horizon v2 total
    # is still reported, just without a v1 baseline for the part v1 was never asked to plan.
    n_periods_cycle1 = cycle_bounds[1]
    y_v1_full = v1_schedule_matrix(online_ids, r, cost, dev0, n_periods, sched_v1)
    y_v1_c1, y_best_c1 = y_v1_full[:, :n_periods_cycle1], y_best[:, :n_periods_cycle1]
    v1_total, v1_fuel, v1_clean = realized_cost(dev0, r, cost, k_per_day, y_v1_c1)
    v2_c1_total, v2_c1_fuel, v2_c1_clean = realized_cost(dev0, r, cost, k_per_day, y_best_c1)
    pct_improvement = round((v1_total - v2_c1_total) / v1_total * 100, 1) if v1_total > 0 else None

    # --- per-HX schedule dates for the dashboard Gantt ---
    per_hx, timeline = [], []
    for i, hx in enumerate(online_ids):
        dates = []
        for t in range(n_periods):
            if y_best[i, t] >= 0.5:
                d = as_of + pd.Timedelta(days=(t + 1) * PERIOD_DAYS)
                dates.append(str(d.date()))
                timeline.append(dict(HX=hx, date=str(d.date()), kind='ONLINE_V2'))
        for d in tam_dates:
            timeline.append(dict(HX=hx, date=str(d.date()), kind='TAM'))
        per_hx.append(dict(HX=hx, online=True, r_C_per_day=round(float(r[i]), 5),
                           cleaning_cost=int(cost[i]), n_cleans_to_tam=len(dates),
                           next_dates=dates))
    for hx in tam_only_ids:
        per_hx.append(dict(HX=hx, online=False, r_C_per_day=round(state[hx]['r'], 5),
                           cleaning_cost=state[hx]['cost'], n_cleans_to_tam=0,
                           next_dates=[str(d.date()) for d in tam_dates],
                           rationale=f'ไม่มี bypass (list โรงงาน) — ล้างได้เฉพาะ TAM ({", ".join(str(d.date()) for d in tam_dates)})'))
        for d in tam_dates:
            timeline.append(dict(HX=hx, date=str(d.date()), kind='TAM'))
    per_hx.sort(key=lambda p: -(p.get('n_cleans_to_tam') or 0))

    out = dict(
        as_of=str(as_of.date()), next_tam=str(NEXT_TAM.date()), next_tam_assumed=False,
        tam_dates=[str(d.date()) for d in tam_dates], tam_dates_confirmed=[True] + [False] * (len(tam_dates) - 1),
        per_cycle_summary=per_cycle,
        method=('Moving-window joint optimal-control schedule across all online-capable HX '
                '(Dekebo, Oh & Lee, Appl. Sci. 2023, 13, 604; framework: Al Ismaili et al., '
                'Comput. Chem. Eng. 2018) — reduced-form network coupling: ผลรวม deviation '
                'ที่วัดจริงต่อ HX (ไม่ใช่ full epsilon-NTU DAE เพราะ UA nameplate ไม่ผ่านการ validate '
                'กับสภาพจริง) · แก้ปัญหาต่อหน้าต่างเลื่อนด้วย SLSQP แล้ว commit เฉพาะงวดแรก · '
                f'เพดานความถี่ {MAX_CLEANS_PER_YEAR} ครั้ง/ปีต่อ HX (ข้อจำกัดหน้างานจริง)'),
        max_online_cleans_per_period=MAX_ONLINE_CLEANS_PER_PERIOD, max_online_cleans_assumed=True,
        max_cleans_per_year_per_hx=MAX_CLEANS_PER_YEAR,
        k_baht_per_C_day=round(k_per_day), feed_kbd=feed_kbd,
        window_size_sweep=sweep, optimal_window_months=best_window,
        comparison_vs_v1=dict(
            scope=f'ถึง TAM แรก ({cycle_labels[0]}) เท่านั้น — v1 ไม่เคยถูกวางแผนเลยจุดนี้',
            v1_total_cost_thb=round(v1_total), v1_fuel_thb=round(v1_fuel), v1_cleaning_thb=round(v1_clean),
            v2_total_cost_thb=round(v2_c1_total), v2_fuel_thb=round(v2_c1_fuel), v2_cleaning_thb=round(v2_c1_clean),
            pct_improvement=pct_improvement,
            note=('เปรียบเทียบภายใต้ objective เดียวกัน (ต้นทุนพลังงาน CIT-deficit สะสม + ค่าล้าง) '
                  'จำกัดขอบเขตถึง TAM รอบแรกเท่านั้น เพราะ v1 (cleaning_schedule.json) ไม่มีวันที่ล้างเกินรอบนั้น '
                  '— ถ้าเทียบทั้ง horizon จะเห็น v1 "หยุดล้าง" หลัง TAM แรกซึ่งไม่ใช่พฤติกรรมจริงของ v1 '
                  'แค่ export ไม่ได้ครอบคลุมช่วงนั้น การเทียบแบบนั้นจะไม่ยุติธรรมกับ v1 '
                  '— ทั้งสองแผนถูกจำลองด้วยฟังก์ชันเดียวกัน ถ้า v2 ไม่ดีกว่า v1 จะรายงานตรงตามจริง')),
        v2_full_horizon=dict(
            total_cost_thb=round(best_total),
            note=f'v2 ตลอด horizon ถึง TAM สุดท้าย ({cycle_labels[-1]}) — ไม่มี v1 baseline เทียบเพราะ v1 ไม่เคยวางแผนไกลขนาดนี้'),
        per_hx=per_hx, timeline=sorted(timeline, key=lambda t: t['date']),
        totals=dict(online_hx=len(online_ids), tam_only=len(tam_only_ids)))
    return out


def main():
    econ = _load('economics.json', {})
    chist = _load('cleaning_history.json', {'hx': {}})
    logi = _load('cleaning_logistics.json', {'hx': []})
    sched_v1 = _load('cleaning_schedule.json')

    out = compute_schedule(econ, chist, logi, sched_v1)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')

    best_window = out['optimal_window_months']
    online_ids = [p['HX'] for p in out['per_hx'] if p['online']]
    tam_only_ids = [p['HX'] for p in out['per_hx'] if not p['online']]
    sweep = out['window_size_sweep']
    cmp = out['comparison_vs_v1']
    print(f"Wrote {OUT.name}: {len(online_ids)} online HX, {len(tam_only_ids)} TAM-only, "
          f"optimal window={best_window} months, horizon to {out['tam_dates'][-1]} "
          f"(TAM cycles: {', '.join(out['tam_dates'])})")
    print('window-size sweep:')
    for s in sweep:
        print(f"  SMW={s['window_months']}mo  Obj={s['objective_thb']:,} THB  "
              f"(fuel {s['fuel_thb']:,} + clean {s['cleaning_thb']:,})  n_actions={s['n_cleaning_actions']}")
    print(f"v1 total: {cmp['v1_total_cost_thb']:,} THB | v2 total: {cmp['v2_total_cost_thb']:,} THB | "
          f"improvement: {cmp['pct_improvement']}%")
    print('per-TAM-cycle online-clean count (checking the schedule is not front-loaded before 2028):')
    for c in out['per_cycle_summary']:
        print(f"  through {c['cycle_ends']}: {c['n_online_cleans']} online cleans over {c['n_periods']} periods")


if __name__ == '__main__':
    main()
