"""
Export dashboard/data/evidence.json — the "หลักฐาน & ความเชื่อมั่น" (Evidence &
Confidence) surface for the live engineering demo.

Purpose: make the analysis's rigour VISIBLE and TRACEABLE in one place, so an
engineer watching the dashboard can see at a glance —
  * data provenance (span, #days, #HX, #runs, #audited cleaning events)
  * validation scorecard (CIT persistence-vs-ML CV, fouling generalization,
    degradation-driver CV) with the honest "does it beat baseline?" verdict
  * a measured / modeled / assumed register for every key quantity
  * the standing caveats (from METHODOLOGY §3-4)
  * LIVE honesty flags computed from the current data (e.g. HX whose fouling
    rate is from a previous completed run — surfaced, not hidden)

Design rule: numbers are COMPUTED from source artifacts wherever possible so this
file auto-updates on every `run_all` and can never silently drift from the data.
The few documented-but-not-exported findings (e.g. 3a leave-HX-out CV R²) are
included as clearly-sourced constants, tagged with the notebook they come from.

Run: python pipeline/export_evidence.py
"""
import os, sys, json
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get('CPHT_DATA_DIR', r'C:\Desktop\Bangchak Internship 2026\Data'))
DASH = REPO / 'dashboard' / 'data'
OUT  = DASH / 'evidence.json'
sys.path.append(str(REPO))

R2_GATE = 0.30   # LEGACY-ONLY fallback for a Fouling_Rate_By_Run.csv without a `reliable`
                 # column (current pipeline always has one — see below). Keep in sync with
                 # `min_r2_gate` in nb_audit.robust_fouling_rate (currently also 0.30).


def _load(name, default=None):
    p = DASH / name
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else default


def _tam_dates():
    try:
        from src.features.heat_duty import get_tam_dates
        return [str(pd.Timestamp(d).date()) for d in get_tam_dates()]
    except Exception:
        return []


def main():
    mm    = _load('model_metrics.json', {})
    chist = _load('cleaning_history.json', {'hx': {}})
    econ  = _load('economics.json', {})
    eor   = _load('end_of_run.json', {'hx': {}})
    drv   = _load('drivers.json', {})

    # ---- data provenance (computed from source) ----
    fr_path = DATA / 'Fouling_Rate_By_Run.csv'
    n_runs = n_hx_runs = n_flagged = n_reliable = None
    flag_counts = {}
    if fr_path.exists():
        fr = pd.read_csv(fr_path)
        n_runs = int(len(fr))
        n_hx_runs = int(fr['HX'].nunique())
        if 'reliable' in fr.columns:   # robust methodology: physics-gated reliability
            n_reliable = int((fr['reliable'] == True).sum())  # noqa: E712
            n_flagged = n_runs - n_reliable
            flag_counts = {k: int(v) for k, v in fr['rate_flag'].value_counts().items()}
        else:                          # legacy CSV: R²-only gate
            n_flagged = int((fr['R2'] < R2_GATE).sum())
            n_reliable = n_runs - n_flagged

    n_events = sum(len(v.get('cleans', [])) for v in chist.get('hx', {}).values())
    n_hx = len(eor.get('hx', {})) or len(chist.get('hx', {}))
    tams = _tam_dates()

    data_block = dict(
        date_start=(mm.get('date_range') or [None, None])[0],
        date_end=(mm.get('date_range') or [None, None])[1],
        n_days_cit=mm.get('n_rows'),
        n_hx=n_hx,
        n_fouling_runs=n_runs,
        n_cleaning_events_audited=n_events,
        n_tams_detected=len(tams), tam_dates=tams,
        as_of=chist.get('as_of') or eor.get('as_of'),
    )

    # ---- validation scorecard ----
    cit_models = [dict(name=m.get('model'), role=m.get('role'), cv_r2=m.get('R2'),
                       beats_persistence=m.get('beats_persistence'), note=m.get('note'))
                  for m in mm.get('models', [])]
    validation = dict(
        cit=dict(
            method=mm.get('validation'), target=mm.get('target'),
            primary_baseline=mm.get('primary_baseline'),
            skill_vs_persistence_pct=mm.get('skill_vs_persistence_pct_mean'),
            headline=mm.get('headline'), models=cit_models),
        fouling_forecast=dict(
            metric='leave-HX-out CV R²', value=0.10,
            source='06_fouling_rate_forecast.ipynb §7 (documented)',
            note='ข้ามไป HX ใหม่ทำนายไม่ได้ (Q scale ต่างกันมาก) — สัญญาณที่ deploy ใช้ได้เพราะ refit บน baseline ของ HX นั้นเอง ไม่ใช่ zero-shot'),
        fouling_quality_gate=dict(
            n_runs=n_runs, n_reliable=n_reliable, n_flagged=n_flagged, flag_breakdown=flag_counts,
            method=('robust: in-service mask + winsorize + AIC race (linear vs asymptotic-decay '
                    'vs power) on U_relative -> current/tail-slope rate + physics gate (slope<0, '
                    'CI) + R2 floor (>=0.30) + oscillation gate (sign-change-rate, catches '
                    'shell-switch sawtooth noise)'),
            note=(f'{n_reliable}/{n_runs} รอบผ่านเกณฑ์ฟิสิกส์ (reliable, slope<0) — ที่เหลือติดธง '
                  + ' · '.join(f'{k}={v}' for k, v in flag_counts.items()) if flag_counts
                  else (f'{n_reliable}/{n_runs} รอบเชื่อถือได้' if n_runs else None))),
        degradation_drivers=dict(
            metric='CV R²', value=drv.get('cv_r2_mean'), n=drv.get('n'),
            note='CV R²<0 = associative (บอกความสัมพันธ์) ไม่ใช่ causation') if drv else None,
    )

    # ---- measured / modeled / assumed register ----
    src = [p.get('cit_gain_source') for p in econ.get('per_hx', [])]
    n_meas = src.count('measured'); n_model = src.count('model')
    register = [
        dict(quantity='U_relative / fouling rate', status='measured',
             basis='U/U_clean ต่อรอบจากข้อมูลจริง (Feature_calculated.csv) + linregress ต่อรอบ',
             source='02_feature_engineering.ipynb'),
        dict(quantity='Q duty shortfall (ค่าเบี่ยงเบน)', status='measured',
             basis='clean-baseline model refit บน 30 วันแรกหลังล้างของ HX นั้นเอง แล้ววัด deviation',
             source='06_fouling_rate_forecast.ipynb'),
        dict(quantity='ΔCIT คืนต่อการล้าง', status='measured-first',
             basis=f'median จาก audit history จริง ({n_meas} HX) · fallback ค่าโมเดล ({n_model} HX) เมื่อวัดไม่ได้',
             source='export_cleaning_history.py → economics.json'),
        dict(quantity='สูตรพลังงาน (Energy Saving Benefit)', status='plant-formula',
             basis='STD_ENERGY 0.74 × Feed[KBD] × NG 390 × 360 × 0.5(decay) — สไลด์วิศวกร',
             source=f"slide-check {econ.get('slide_check_thb_yr'):,} ฿/ปี ✓" if econ.get('slide_check_thb_yr') else 'export_economics.py'),
        dict(quantity='Cp/ρ crude (2.2 / 850 คงที่)', status='assumed',
             basis='ใช้เชิงเปรียบเทียบ (U_relative/Q_drop) — ไม่ขึ้นกับ T/crude',
             source='METHODOLOGY §4'),
        dict(quantity='ค่าล้าง HX (150k-400k ฿/ครั้ง)', status='assumed',
             basis='baseline ตามช่วงจริงหน้างาน ~100k-500k · ปรับต่อ HX ได้บน dashboard',
             source='export_economics.py::CLEANING_COST_BY_HX — รอราคาจริง'),
        dict(quantity='FG price / NEXT_TAM / cleaning-crew cap', status='assumed',
             basis='ค่าปรับได้บน dashboard, ติดป้าย "ค่าสมมติ" ชัดเจน',
             source='รอวิศวกรยืนยัน'),
        dict(quantity='hot-side per-HX flow', status='not-available',
             basis='residue path ใช้ร่วม/สลับ — เป็น confound ที่ละไว้ (บันทึกตรง ๆ)',
             source='METHODOLOGY §4'),
    ]

    # ---- standing caveats (from METHODOLOGY §3-4) ----
    caveats = [
        'โมเดล CIT ไม่ชนะ persistence (walk-forward CV) — tree ใช้ SHAP attribution เท่านั้น ไม่ใช่ตัวพยากรณ์',
        'การพยากรณ์ fouling ข้าม HX ไม่ generalize (leave-HX-out R²≈0.10) — ใช้ได้เฉพาะแบบ refit ต่อ HX',
        'ไม่มี ground-truth Rf — validate ด้วยการ reset หลังล้างเท่านั้น (noisier สำหรับ Q มากกว่าอุณหภูมิ)',
        'ข้อมูลเล็ก (2-6 รอบ/HX) — per-HX Weibull ที่ n<4 ใช้ pooled shape · driver analysis เป็น associative',
        'CIT gain ต่อ HX จาก single-TAM calibration → เชิงทิศทาง จนกว่าจะมี TAM ที่สอง validate',
    ]

    # ---- LIVE honesty flags (computed now) ----
    stale = sorted([h for h, v in eor.get('hx', {}).items()
                    if (v.get('urel') or {}).get('rate_source') not in ('current_run', None)])
    past_trig = sorted([h for h, v in eor.get('hx', {}).items()
                        if (v.get('flags') or {}).get('past_trigger')])
    unreliable = sorted([h for h, v in eor.get('hx', {}).items()
                         if (v.get('flags') or {}).get('unreliable')])
    live_flags = dict(
        stale_rate_hx=stale, past_trigger_hx=past_trig, low_confidence_trend_hx=unreliable,
        note='ธงที่คำนวณจากข้อมูลปัจจุบัน — แสดงตรง ๆ ไม่ซ่อน (เช่น HX ที่อัตรา fouling มาจากรอบก่อนหน้า จะงดสรุปแนวโน้ม)')

    out = dict(
        as_of=data_block['as_of'],
        principle='จัดลำดับล้างอิงสัญญาณกายภาพที่วัดได้เป็นหลัก — ไม่พึ่งโมเดลที่ยัง validate ไม่ผ่าน · ทุกโมเดลมี baseline เทียบ + CV ที่ hold out จริง + ธงความเชื่อมั่น',
        data=data_block, validation=validation,
        quantity_register=register, caveats=caveats, live_flags=live_flags,
        methodology_ref='notebooks/METHODOLOGY.md')
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'Wrote {OUT.name}: {n_hx} HX, {n_runs} runs ({n_flagged} flagged), '
          f'{n_events} cleaning events, {len(tams)} TAMs, {len(stale)} stale-rate flag(s)')


if __name__ == '__main__':
    main()
