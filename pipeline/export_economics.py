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
actual sawtooth jump audited against past cleans); fall back to the model value
(expected_CIT_gain_C, known to over-estimate ~3x vs the plant's observed 2°C for
E113A) with a flag. The legacy first-principles formula (charge·ρ·Cp/LHV/η) is
kept as a cross-check field.

Cleaning cost: per-HX table CLEANING_COST_BY_HX. Baseline set 2026-07-12 to match
the plant engineer's real-world range (~100k-500k THB/event, never higher) —
tiered by cleaning method (shell swap < online bundle pull < TAM-scope). Still
flagged COSTS_ASSUMED pending the plant's final quotes.

Run: python pipeline/export_economics.py
"""
import os, sys, json
from pathlib import Path
import numpy as np

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / 'dashboard' / 'data'
OUT  = DATA / 'economics.json'

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
}
DEFAULT_CLEANING_COST = 300000
COSTS_ASSUMED = True

BASIS = ('สูตรโรงงาน: Saving[฿/ปี] = ΔCIT × 0.74 MMBTU/D/KBD/°C × Feed[KBD] × NG[฿/MMBTU] × 360 × 0.5(decay) ; '
         'Feed[KBD] = charge[m³/h]×24/158.987 ; ΔCIT ใช้ค่าวัดจริง (median จาก audit history) ก่อน, '
         'fallback ค่าโมเดล (ระวัง over-estimate) ; ค่าล้างต่อ HX เป็นค่าสมมติ ~100k-500k บาท (ตามช่วงจริงหน้างาน) รอราคาจริง')


def _load(name, default=None):
    p = DATA / name
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else default


def measured_cit_gain(chist, hx):
    """Median measured CIT recovery [°C] over audited cleans (only estimable, >0)."""
    h = (chist or {}).get('hx', {}).get(hx)
    if not h:
        return None
    vals = [c['cit_measured_C'] for c in h.get('cleans', [])
            if c.get('gain_estimable') and c.get('cit_measured_C') is not None and c['cit_measured_C'] > 0]
    return round(float(np.median(vals)), 2) if vals else None


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

    def legacy_baht_day(dC):   # THB/day (first-principles cross-check)
        kgph = charge * LEGACY['RHO_CRUDE'] * LEGACY['CP_CRUDE'] * dC / (LEGACY['LHV_FG'] * LEGACY['FURNACE_EFF'])
        return kgph / 1000 * LEGACY['HOURS_PER_DAY'] * LEGACY['FG_PRICE']

    cand = []
    for r in ranking:
        meas = measured_cit_gain(chist, r['HX'])
        model = r.get('expected_CIT_gain_C')
        dC = meas if meas is not None else (model if model and model > 0 else None)
        if dC is None or dC <= 0:
            continue
        cand.append((r, dC, 'measured' if meas is not None else 'model'))
    cand.sort(key=lambda t: t[0].get('priority_score', 0), reverse=True)

    per_hx, cum_cit, cum_yr = [], 0.0, 0.0
    for i, (r, dC, src) in enumerate(cand, 1):
        yr = plant_saving_yr(dC)
        day = yr / PLANT['DAYS_PER_YEAR']
        cost = CLEANING_COST_BY_HX.get(r['HX'], DEFAULT_CLEANING_COST)
        cum_cit += dC
        cum_yr += yr
        per_hx.append(dict(
            HX=r['HX'], rank=i,
            cit_gain_C=round(dC, 2), cit_gain_source=src,
            cit_gain_model_C=(round(float(r['expected_CIT_gain_C']), 2)
                              if r.get('expected_CIT_gain_C') else None),
            saving_thb_yr=round(yr), baht_day=round(day),
            cleaning_cost=cost, cleaning_cost_assumed=COSTS_ASSUMED,
            payback_days=(round(cost / day, 1) if day > 0 else None),
            legacy_baht_day=round(legacy_baht_day(dC)),   # cross-check (LHV/η formula)
            cum_cit_C=round(cum_cit, 2), cum_saving_thb_yr=round(cum_yr),
            cum_baht_day=round(cum_yr / PLANT['DAYS_PER_YEAR']),
        ))

    totals = dict(n_hx=len(per_hx), cum_cit_C=round(cum_cit, 2),
                  saving_thb_yr=round(cum_yr),
                  baht_day=round(cum_yr / PLANT['DAYS_PER_YEAR']))

    # slide reproduction check (E113A: ΔCIT=2, Feed=80, NG=390 -> 8,311,680)
    check = 2 * PLANT['STD_ENERGY'] * 80 * PLANT['NG_PRICE'] * 360 * 0.5

    out = dict(formula='plant', plant_constants=PLANT, legacy_constants=LEGACY,
               charge_m3h=round(float(charge), 1), feed_kbd=round(feed_kbd, 1),
               slide_check_thb_yr=round(check),
               cleaning_costs_assumed=COSTS_ASSUMED, basis=BASIS,
               per_hx=per_hx, totals=totals)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'Wrote {OUT.name}: {len(per_hx)} HX, feed {feed_kbd:.1f} KBD, '
          f'slide check {check:,.0f} THB/yr (expect 8,311,680), '
          f'total {totals["saving_thb_yr"]:,} THB/yr')


if __name__ == '__main__':
    main()
