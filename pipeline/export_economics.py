"""
Export dashboard/data/economics.json — the money model behind "CIT gain -> ฿" (v2).

v2 (2026-07-09): PRIMARY formula switched to the PLANT'S OWN Energy-Saving-Benefit
method (engineer's slide, 3E-113 example):

    Saving[THB/yr] = ΔCIT[°C] × STD_ENERGY × Feed[KBD] × NG_PRICE[THB/MMBTU]
                     × 360[D] × CIT_DECAY_FACTOR

    STD_ENERGY        = 0.74 MMBTU/D/KBD/°C   (F101 standard energy — plant value)
    CIT_DECAY_FACTOR  = 0.5   (post-clean CIT gain decays back over the run,
                               so the average benefit ≈ half the initial gain)
    Feed[KBD]         = charge[m³/h] × 24 / 158.987  (m³ -> bbl)

Slide check: ΔCIT=2°C, Feed=80 KBD, NG=390 → 8,311,680 THB/yr ✓ (reproduced in test).

ΔCIT per HX: prefer the MEASURED median recovery from cleaning_history.json (the
actual sawtooth jump audited against past cleans) -- but ONLY from type=='SWITCH'
events (an actual shell swap/online clean of just that HX). type=='TAM' events are
EXCLUDED from both measured_cit_gain() and event_study_calibration(): a turnaround
cleans the whole preheat train at once, so its CIT recovery can't be credited to any
one HX. Fixed 2026-07-15 after the plant engineer flagged that E105AB has never
actually been part of an online cleaning plan, yet its old "measured" ΔCIT was the
median of one TAM event (+7.3degC, whole-plant-confounded) and one genuine SWITCH
event (+0.3degC) -- the TAM number, not real online-clean history, was driving its
rank. For HX with no qualifying SWITCH event, fall back to the model value
(expected_CIT_gain_C) CORRECTED by an event-study calibration factor
(event_study_calibration()) — the model is known to over-estimate, and that "~3x"
figure used to come from a single TAM event; it's now the median measured/model
ratio across every real SWITCH-only clean event with both values, split by
terminal-vs-non-terminal train position since that split shows a real
difference in this data that a single pooled factor would wash out. See
METHODOLOGY.md and cit_gain_model_calibration in the export.
The legacy first-principles formula (charge·ρ·Cp/LHV/η) is kept as a
cross-check field.

Cleaning cost: per-HX table CLEANING_COST_BY_HX. Baseline set 2026-07-12 to match
the plant engineer's real-world range (~100k-500k THB/event, never higher) —
tiered by cleaning method (shell swap < online bundle pull < TAM-scope). Still
flagged COSTS_ASSUMED pending the plant's final quotes.

Run: python pipeline/export_economics.py
"""
import os, sys, json
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / 'dashboard' / 'data'
OUT  = DATA / 'economics.json'
RAW_DATA = Path(os.environ.get('CPHT_DATA_DIR', r'C:\Desktop\Bangchak Internship 2026\Data'))
MMBTU_TO_KJ = 1_055_055.85

M3_PER_BBL = 0.1589873

# --- plant economic constants (from engineer's Energy Saving Benefit slide) ---
PLANT = dict(
    STD_ENERGY=0.74,       # MMBTU/D/KBD/°C — F101 standard energy (plant value)
    NG_PRICE=390,          # THB/MMBTU (plant value from slide)
    DAYS_PER_YEAR=360,     # plant convention
    CIT_DECAY_FACTOR=0.5,  # average benefit = half the initial CIT gain (decays over run)
)

# --- legacy cross-check constants (first-principles furnace balance, assumed) ---
LEGACY = dict(CP_CRUDE=2.2, RHO_CRUDE=850, LHV_FG=48000, FURNACE_EFF=0.88,
              FG_PRICE=18000, CO2_FACTOR=2.75, HOURS_PER_DAY=24)

# --- per-HX cleaning cost [THB/event] — baseline reflects the plant engineer's
# real-world range (~100k-500k THB, never higher). Tiered guess: swap (spare
# shell, no crane job) < online bundle pull < TAM-scope. Still ASSUMED pending
# the plant's final quotes.
CLEANING_COST_BY_HX = {
    'E113A': 150000, 'E112C': 150000,                       # shell swap
    'E101AB': 300000, 'E102': 300000, 'E104': 300000,       # online bundle (bypass exists)
    'E105AB': 300000, 'E108AB': 300000, 'E110ABC': 300000,
    'E111': 300000, 'E112AB': 300000, 'E101EF': 300000, 'E101CD': 300000,
    'E103AB': 400000, 'E106AB': 400000, 'E107AB': 400000, 'E109AB': 400000,  # TAM-only
    'E101G': 400000,                                        # TAM-only (was missing -> silently
                                                             # fell back to the 300k online-bundle
                                                             # default despite having no bypass)
}
DEFAULT_CLEANING_COST = 300000
COSTS_ASSUMED = True


def resolve_cost_override(override, default_cost):
    """Resolve one HX's entry in cost_overrides.json (written by the dashboard's
    "คำนวณใหม่" form) to a single THB cost, choosing the cheapest cleaning METHOD
    when a formula is given rather than a single number.

    Two supported shapes, kept backward compatible with the original scalar form:
      - number (legacy): a flat THB override, used as-is.
      - {"methods": [{"label": str, "base_cost": THB,
                       "variable_cost_per_day": THB/day, "downtime_cost_per_day": THB/day,
                       "duration_days": days}, ...]}:
        each method's total cost = base_cost + (variable_cost_per_day +
        downtime_cost_per_day) * duration_days; the optimizer effectively picks
        the cleaning method by using min(total) across methods -- letting a
        cheaper-but-slower or pricier-but-faster method win on total cost instead
        of the dashboard operator having to pre-decide which method to cost out.

    Returns (cost_thb, meta) where meta is None for a plain-number override/no
    override, or a dict describing which method was chosen and why for formula
    overrides (surfaced in cleaning_plan.json so the choice isn't silent)."""
    if override is None:
        return default_cost, None
    if isinstance(override, (int, float)):
        return float(override), None
    if isinstance(override, dict) and override.get('methods'):
        priced = []
        for m in override['methods']:
            total = (float(m.get('base_cost', 0))
                     + (float(m.get('variable_cost_per_day', 0)) + float(m.get('downtime_cost_per_day', 0)))
                     * float(m.get('duration_days', 0)))
            priced.append((total, m))
        priced.sort(key=lambda t: t[0])
        best_cost, best_method = priced[0]
        return best_cost, dict(
            chosen_method=best_method.get('label', '?'), chosen_cost_thb=round(best_cost),
            all_methods=[dict(label=m.get('label', '?'), cost_thb=round(c)) for c, m in priced])
    return default_cost, None

BASIS = ('สูตรโรงงาน: Saving[฿/ปี] = ΔCIT × 0.74 MMBTU/D/KBD/°C × Feed[KBD] × NG[฿/MMBTU] × 360 × 0.5(decay) ; '
         'Feed[KBD] = charge[m³/h]×24/158.987 ; ΔCIT ใช้ค่าวัดจริงก่อน (median จาก audit history — '
         'เฉพาะเหตุการณ์สลับเชลล์/ล้าง online ของ HX นั้นเอง ไม่รวม TAM เพราะ TAM ล้างทั้งเทรนพร้อมกัน '
         'ล้อผลไม่ได้ว่าเป็นของ HX ไหน), '
         'fallback ค่าโมเดล คูณด้วย calibration factor จาก event-study (measured/model ratio จริงทุก clean event '
         'ที่ไม่ใช่ TAM แยกกลุ่ม terminal/non-terminal — ดู cit_gain_model_calibration) ; '
         'ค่าล้างต่อ HX เป็นค่าสมมติ ~100k-500k บาท (ตามช่วงจริงหน้างาน) รอราคาจริง')


def _load(name, default=None):
    p = DATA / name
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else default


def measured_cit_gain(chist, hx):
    """Median measured CIT recovery [°C] over audited cleans (only estimable, >0).

    EXCLUDES type=='TAM' events: a turnaround cleans the ENTIRE preheat train at once, so
    whatever CIT recovery is observed around a TAM cannot be attributed to this one HX --
    doing so let a whole-plant TAM recovery masquerade as "this HX's own online-clean
    value." Confirmed against real plant knowledge (2026-07-15): the engineer flagged that
    E105AB has never actually been part of an online cleaning plan, yet its 'measured'
    ΔCIT here was the median of one TAM event (+7.34degC) and one genuine online SWITCH
    event (+0.33degC) -- the TAM number was doing all the work. Checked project-wide: 4 of
    the 6 non-terminal HX with a 'measured' economics.json entry had ZERO or only one
    genuine (non-TAM) positive event backing that number (see git history for the audit).
    Only SWITCH-type events (an actual shell swap/online clean of just this HX) are trusted
    here; HX with no qualifying SWITCH event fall back to the calibrated model estimate
    (calibrated_model_gain), same as before."""
    h = (chist or {}).get('hx', {}).get(hx)
    if not h:
        return None
    vals = [c['cit_measured_C'] for c in h.get('cleans', [])
            if c.get('type') != 'TAM' and c.get('gain_estimable')
            and c.get('cit_measured_C') is not None and c['cit_measured_C'] > 0]
    return round(float(np.median(vals)), 2) if vals else None


CALIB_RATIO_CLIP = (0.15, 1.0)   # sane bounds on the correction factor: never inflate the
                                  # model estimate, never let a lone noisy event zero it out


def event_study_calibration(chist):
    """Empirical measured/model ΔCIT ratio from EVERY real cleaning event with both
    a measured and a model value (not just the single TAM event this correction used
    to be pinned to) -- the fix for the model fallback's documented ~3x over-estimate.

    Grouped by terminal-vs-non-terminal train position (cleaning_history.json's
    sensitivity.is_terminal_CIT, the cheapest available chain-position proxy) rather
    than pooled into one global number: terminal HX (E113A/E112C, right before the
    furnace) show a materially different ratio than mid-train HX in this data, so a
    single pooled factor would misrepresent both groups -- the same generalize-
    across-dissimilar-HX pitfall the 3a leave-HX-out CV already ran into (R^2~0.10).
    Falls back to the global ratio, then to no correction (1.0), if a group has too
    few events to trust its own median.

    EXCLUDES type=='TAM' events for the same reason measured_cit_gain() does: a TAM's CIT
    recovery reflects the WHOLE preheat train being cleaned at once, not this one HX, so
    letting those events into the measured/model ratio would bias the calibration factor
    applied to every model-fallback HX. Confirmed real-world (2026-07-15): 12 of the 32
    events previously used here were TAM events -- over a third of the calibration sample
    was whole-plant-confounded."""
    MIN_GROUP_N = 5
    by_group = {True: [], False: []}
    all_ratios = []
    for h, v in (chist or {}).get('hx', {}).items():
        term = bool((v.get('sensitivity') or {}).get('is_terminal_CIT'))
        for c in v.get('cleans', []):
            if c.get('type') == 'TAM':
                continue
            m, mdl = c.get('cit_measured_C'), c.get('cit_model_C')
            if c.get('gain_estimable') and m is not None and mdl and mdl > 0:
                ratio = m / mdl
                by_group[term].append(ratio)
                all_ratios.append(ratio)

    def _med(xs):
        return round(float(np.median(xs)), 3) if xs else None

    global_ratio = _med(all_ratios)
    group_ratio_raw = {'terminal': _med(by_group[True]), 'non_terminal': _med(by_group[False])}
    group_n = {'terminal': len(by_group[True]), 'non_terminal': len(by_group[False])}
    # a group with too few events falls back to the global (still-empirical) ratio
    # rather than trusting a median of a handful of noisy points
    group_ratio = {k: (v if v is not None and group_n[k] >= MIN_GROUP_N else global_ratio)
                   for k, v in group_ratio_raw.items()}
    return dict(n_events=len(all_ratios), global_ratio=global_ratio,
                group_ratio=group_ratio, group_ratio_own_group_only=group_ratio_raw,
                group_n=group_n, min_group_n=MIN_GROUP_N, clip=list(CALIB_RATIO_CLIP))


def calibrated_model_gain(model_C, is_terminal, calib):
    """Apply event_study_calibration()'s group ratio to a raw model estimate, clipped
    to CALIB_RATIO_CLIP. Returns (calibrated_value, factor_used)."""
    key = 'terminal' if is_terminal else 'non_terminal'
    factor = (calib or {}).get('group_ratio', {}).get(key) or (calib or {}).get('global_ratio') or 1.0
    factor = min(max(factor, CALIB_RATIO_CLIP[0]), CALIB_RATIO_CLIP[1])
    return model_C * factor, round(factor, 3)


def fg_flow_cross_check(chist, feed_kbd, window_days=7):
    """Cross-check the two ΔCIT->fuel-gas formulas (plant STD_ENERGY vs legacy LHV/eta) against
    the ACTUAL measured 1FI028.pv (FG flow) response around real audited cleaning events, using
    Process_information_cleaned.csv (daily). Does NOT change either formula -- this is an
    honesty check surfaced for the engineer, same spirit as the Evidence tab's validation
    scorecard: report the real ratio, don't assume either formula is exactly right.

    Restricted to TERMINAL HX events (E113A/E112C, whose cold_out IS the CIT tag) because for
    non-terminal HX the FG-flow response to one HX's clean is confounded by every other HX in
    the train changing CIT at the same time -- terminal HX are the cleanest single-cause window
    available in this data (same reasoning export_economics already uses for the terminal/
    non-terminal calibration split, see event_study_calibration). Also excludes type=='TAM'
    events for the identical reason: a turnaround cleans the whole train at once, so the
    FG-flow response can't be credited to the terminal HX's clean specifically either
    (same fix as measured_cit_gain()/event_study_calibration(), 2026-07-15).

    Returns None (not an empty dict) if the raw process CSV isn't available (e.g. a stripped
    demo dataset with no dashboard/data raw tags) -- callers must not read a missing check as
    "formulas agree", only as "not checked"."""
    csv_path = RAW_DATA / 'Process_information_cleaned.csv'
    if not csv_path.exists():
        return None
    try:
        proc = pd.read_csv(csv_path, usecols=['Timestamp', '1FI028.pv'], parse_dates=['Timestamp']).set_index('Timestamp').sort_index()
    except (ValueError, OSError):
        return None
    fg = proc['1FI028.pv']

    def _window_mean(center, before):
        lo, hi = (center - pd.Timedelta(days=window_days), center) if before else (center, center + pd.Timedelta(days=window_days))
        vals = fg.loc[lo:hi]
        return float(vals.mean()) if len(vals) else None

    rows = []
    for hx, h in (chist or {}).get('hx', {}).items():
        if not (h.get('sensitivity') or {}).get('is_terminal_CIT'):
            continue
        for c in h.get('cleans', []):
            if c.get('type') == 'TAM':
                continue
            dC = c.get('cit_measured_C')
            if not c.get('gain_estimable') or dC is None or dC <= 0:
                continue
            d = pd.Timestamp(c['date'])
            before, after = _window_mean(d, True), _window_mean(d, False)
            if before is None or after is None:
                continue
            measured_drop_tph = before - after   # FG should DROP after a clean recovers CIT
            plant_mmbtu_day = dC * PLANT['STD_ENERGY'] * feed_kbd
            plant_drop_tph = plant_mmbtu_day * MMBTU_TO_KJ / LEGACY['LHV_FG'] / 24 / 1000
            charge = (feed_kbd * 1000) * 0.1589873 / 24   # KBD -> m3/h, inverse of main()'s feed_kbd calc
            legacy_drop_tph = charge * LEGACY['RHO_CRUDE'] * LEGACY['CP_CRUDE'] * dC / (LEGACY['LHV_FG'] * LEGACY['FURNACE_EFF']) / 1000
            rows.append(dict(HX=hx, date=c['date'], cit_measured_C=dC,
                             fg_measured_drop_tph=round(measured_drop_tph, 3),
                             fg_plant_formula_drop_tph=round(plant_drop_tph, 3),
                             fg_legacy_formula_drop_tph=round(legacy_drop_tph, 3),
                             ratio_measured_vs_plant=(round(measured_drop_tph / plant_drop_tph, 2) if plant_drop_tph else None),
                             ratio_measured_vs_legacy=(round(measured_drop_tph / legacy_drop_tph, 2) if legacy_drop_tph else None)))

    if not rows:
        return dict(available=True, n_events=0, rows=[],
                    note='ไม่มีเหตุการณ์ล้าง terminal HX ที่มีทั้ง cit_measured_C และข้อมูล FG flow รอบวันนั้นให้เทียบ')
    ratios_plant = [r['ratio_measured_vs_plant'] for r in rows if r['ratio_measured_vs_plant'] is not None]
    ratios_legacy = [r['ratio_measured_vs_legacy'] for r in rows if r['ratio_measured_vs_legacy'] is not None]
    return dict(
        available=True, n_events=len(rows), window_days=window_days, rows=rows,
        median_ratio_measured_vs_plant=(round(float(np.median(ratios_plant)), 2) if ratios_plant else None),
        median_ratio_measured_vs_legacy=(round(float(np.median(ratios_legacy)), 2) if ratios_legacy else None),
        note=('ratio ~1.0 = สูตรทำนาย FG-flow ที่ลดลงจริงได้ตรง · ratio<1 = สูตรทำนายสูงเกินจริง · ratio>1 = ทำนายต่ำไป · '
              'ค่าจริงมี noise สูง (FG flow ขึ้นกับปัจจัยอื่นด้วย เช่น O2/charge rate/crude grade ไม่ใช่แค่ CIT — '
              'n เล็ก อย่าตีความเป็นการ validate สูตรที่แม่นยำ เป็นเพียง sanity-check ทิศทาง)')
    )


def main():
    ranking = _load('hx_ranking.json', [])
    topo = _load('pfd_topology.json', {})
    chist = _load('cleaning_history.json')

    charge = (topo.get('nodes', {}).get('E113A', {}).get('cold_flow_val')
              or next((f['value'] for f in topo.get('furnace', []) if f.get('key') == 'CHARGE'), None)
              or 525.0)
    feed_kbd = charge * 24 / M3_PER_BBL / 1000   # m³/h -> bbl/day -> KBD (thousand bbl/day)

    def plant_saving_yr(dC):   # THB/year (plant formula)
        return dC * PLANT['STD_ENERGY'] * feed_kbd * PLANT['NG_PRICE'] * \
               PLANT['DAYS_PER_YEAR'] * PLANT['CIT_DECAY_FACTOR']

    def legacy_fg_ton_h(dC):   # tonnes/hr fuel-gas reduction (first-principles energy balance)
        kgph = charge * LEGACY['RHO_CRUDE'] * LEGACY['CP_CRUDE'] * dC / (LEGACY['LHV_FG'] * LEGACY['FURNACE_EFF'])
        return kgph / 1000

    def legacy_baht_day(dC):   # THB/day (first-principles cross-check)
        return legacy_fg_ton_h(dC) * LEGACY['HOURS_PER_DAY'] * LEGACY['FG_PRICE']

    def legacy_co2_ton_day(dC):   # tonnes CO2/day avoided, same fuel-gas-reduction basis
        return legacy_fg_ton_h(dC) * LEGACY['HOURS_PER_DAY'] * LEGACY['CO2_FACTOR']

    calib = event_study_calibration(chist)

    cand = []
    for r in ranking:
        meas = measured_cit_gain(chist, r['HX'])
        model = r.get('expected_CIT_gain_C')
        is_term = bool(((chist or {}).get('hx', {}).get(r['HX'], {}).get('sensitivity') or {}).get('is_terminal_CIT'))
        if meas is not None:
            dC, src, calib_factor = meas, 'measured', None
        elif model and model > 0:
            dC, calib_factor = calibrated_model_gain(model, is_term, calib)
            src = 'model_calibrated'
        else:
            continue
        if dC is None or dC <= 0:
            continue
        cand.append((r, dC, src, calib_factor))
    cand.sort(key=lambda t: t[0].get('priority_score', 0), reverse=True)

    per_hx, cum_cit, cum_yr, cum_co2 = [], 0.0, 0.0, 0.0
    for i, (r, dC, src, calib_factor) in enumerate(cand, 1):
        yr = plant_saving_yr(dC)
        day = yr / PLANT['DAYS_PER_YEAR']
        cost = CLEANING_COST_BY_HX.get(r['HX'], DEFAULT_CLEANING_COST)
        co2_ton_day = legacy_co2_ton_day(dC)   # legacy first-principles basis (see fg_ton_h)
        cum_cit += dC
        cum_yr += yr
        cum_co2 += co2_ton_day
        per_hx.append(dict(
            HX=r['HX'], rank=i,
            cit_gain_C=round(dC, 2), cit_gain_source=src,
            cit_gain_model_C=(round(float(r['expected_CIT_gain_C']), 2)
                              if r.get('expected_CIT_gain_C') else None),
            cit_gain_calibration_factor=calib_factor,
            saving_thb_yr=round(yr), baht_day=round(day),
            cleaning_cost=cost, cleaning_cost_assumed=COSTS_ASSUMED,
            payback_days=(round(cost / day, 1) if day > 0 else None),
            legacy_baht_day=round(legacy_baht_day(dC)),   # cross-check (LHV/η formula)
            legacy_fg_reduction_ton_h=round(legacy_fg_ton_h(dC), 3),
            legacy_co2_reduction_ton_day=round(co2_ton_day, 3),
            cum_cit_C=round(cum_cit, 2), cum_saving_thb_yr=round(cum_yr),
            cum_baht_day=round(cum_yr / PLANT['DAYS_PER_YEAR']),
            cum_co2_reduction_ton_day=round(cum_co2, 3),
        ))

    totals = dict(n_hx=len(per_hx), cum_cit_C=round(cum_cit, 2),
                  saving_thb_yr=round(cum_yr),
                  baht_day=round(cum_yr / PLANT['DAYS_PER_YEAR']),
                  co2_reduction_ton_day=round(cum_co2, 3),
                  independence_caveat=(
                      'ผลรวมนี้บวก ΔCIT ของแต่ละ HX ตรงๆ โดยสมมติว่าเป็นอิสระต่อกัน แต่ในเทรน '
                      'preheat แบบอนุกรม การล้าง HX ตัวหนึ่งจะเปลี่ยน ΔT ที่ HX ถัดไปในเทรนได้รับ '
                      'จริง — ตัวเลขนี้จึงเป็นค่าประมาณขอบบน (upper bound) ไม่ใช่ผลลัพธ์ที่ผ่านการ '
                      'จัดลำดับ/จำลองปฏิสัมพันธ์ระหว่าง HX จริง ซึ่งเป็นหน้าที่ของ '
                      '16_cleaning_plan_optimization.ipynb'))

    # slide reproduction check (E113A: ΔCIT=2, Feed=80, NG=390 -> 8,311,680)
    check = 2 * PLANT['STD_ENERGY'] * 80 * PLANT['NG_PRICE'] * 360 * 0.5

    fg_check = fg_flow_cross_check(chist, feed_kbd)

    out = dict(formula='plant', plant_constants=PLANT, legacy_constants=LEGACY,
               m3_per_bbl=M3_PER_BBL,
               charge_m3h=round(float(charge), 1), feed_kbd=round(feed_kbd, 1),
               slide_check_thb_yr=round(check),
               cleaning_costs_assumed=COSTS_ASSUMED, basis=BASIS,
               cit_gain_model_calibration=calib,
               fg_flow_cross_check=fg_check,
               per_hx=per_hx, totals=totals)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    n_calibrated = sum(1 for p in per_hx if p['cit_gain_source'] == 'model_calibrated')
    print(f'Wrote {OUT.name}: {len(per_hx)} HX, feed {feed_kbd:.1f} KBD, '
          f'slide check {check:,.0f} THB/yr (expect 8,311,680), '
          f'total {totals["saving_thb_yr"]:,} THB/yr')
    print(f'dCIT model calibration: {calib["n_events"]} events, global ratio={calib["global_ratio"]}, '
          f'group ratio={calib["group_ratio"]} -> applied to {n_calibrated}/{len(per_hx)} HX with no measured history')


if __name__ == '__main__':
    main()
