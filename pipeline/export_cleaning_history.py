"""
Export dashboard/data/cleaning_history.json — the per-HX CLEANING AUDIT HISTORY.

Purpose (พี่วิศวกรขอ): show every PAST cleaning event (online clean / shell SWITCH /
TAM turnaround) as an auditable row so a senior engineer can review the analysis
criteria — how fouling rate is fit and how CIT recovery is judged.

Per cleaning event we report, side-by-side, the MEASURED recovery (the actual
sawtooth jump in the data) and the MODEL estimate, so the two can be compared:

  * U recovery (measured)  = U_relative[event] − U_relative[event−1]  (the reset jump)
  * Q recovery (measured)  = Q[event] − Q[event−1]                    [kW]
  * CIT recovery (measured):
      - terminal HX whose cold_out IS the CIT tag (E113A/E112C) → cold_out jump directly
      - otherwise → ΔQ_recovered / charge × CIT_sensitivity (2c);
        flagged not-estimable when Q_CIT_corr < 0.2 or sensitivity ≤ 0 (downstream pinch)
  * CIT recovery (model)   = expected_CIT_gain_C from 2d/6d (one value per HX)
  * fouling rate of the run that ENDED (run N−1): dUrel/month, R², N, reliable

No physics is recomputed here — it reads the CSVs the pipeline already produced and
`end_of_run.json` for the next-clean forecast row.

Run: python pipeline/export_cleaning_history.py
"""
import os, sys, json
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
NB   = REPO / 'notebooks'
DATA = Path(os.environ.get('CPHT_DATA_DIR', r'C:\Desktop\Bangchak Internship 2026\Data'))
OUT  = REPO / 'dashboard' / 'data' / 'cleaning_history.json'
sys.path.append(str(NB))
from cpht_config import HX_CONFIG as COLD_CFG, CIT_TAG, TOTAL_CHARGE_TAG

CORR_MIN = 0.20                              # min |Q-CIT corr| for a trustworthy sensitivity estimate

EVENT_LABEL = {'SWITCH': 'สลับเชลล์ / ล้างออนไลน์', 'TAM': 'TAM (turnaround)'}


def _num(v, nd=3):
    return None if v is None or (isinstance(v, float) and not np.isfinite(v)) else round(float(v), nd)


def _load_json(name):
    p = REPO / 'dashboard' / 'data' / name
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else None


def main():
    feat = pd.read_csv(DATA / 'Feature_calculated.csv', parse_dates=['Timestamp']).set_index('Timestamp')
    fr   = pd.read_csv(DATA / 'Fouling_Rate_By_Run.csv')
    sens = pd.read_csv(DATA / 'Q_CIT_Sensitivity.csv').set_index('HX')
    cpr  = pd.read_csv(DATA / 'Cleaning_Priority_Ranking.csv').set_index('HX')
    proc = pd.read_csv(DATA / 'Process_information_cleaned.csv', parse_dates=['Timestamp']).set_index('Timestamp')
    eor  = _load_json('end_of_run.json') or {'hx': {}}

    charge = proc[TOTAL_CHARGE_TAG] if TOTAL_CHARGE_TAG in proc.columns else None
    charge_mean = float(charge.mean()) if charge is not None else 525.0

    as_of = feat.index.max()
    out = {'as_of': as_of.strftime('%Y-%m-%d'),
           'criteria': {
               'fouling_rate': 'ต่อรอบเดินเครื่อง: AIC race เชิงเส้น vs asymptotic decay บน U_relative (curve_models.py), รายงานอัตราปัจจุบัน (tail slope) ไม่ใช่ค่าเฉลี่ยทั้งรอบ',
               'quality_gate': 'เชื่อถือได้ (`reliable`, มาจาก nb_audit.robust_fouling_rate) เมื่อ: slope<0 อย่างมีนัยสำคัญ (CI upper < tol), R²ของโมเดลที่เลือก ≥ 0.30, sign-change-rate ≤ 0.35 (ไม่ใช่สัญญาณ oscillation จากการสลับเชลล์), ช่วงข้อมูล/จำนวนจุด/สัดส่วน in-service เพียงพอ, และ Rf สอดคล้องทิศทาง — นิยามเดียวกันทั้งระบบ (ไม่คำนวณซ้ำที่นี่)',
               'clean_trigger': 'U_relative < 0.875 (เสีย 12.5% จากสภาพสะอาด) หรือ duty shortfall > threshold (3b)',
               'cit_recovery_measured': 'จุดกระโดดจริงตอนล้าง: HX ปลายเทรน (cold_out=CIT) ใช้ cold_out jump ตรง; อื่น ๆ ใช้ ΔQ_recovered/charge × CIT_sensitivity (2c)',
               'bypass_correction': 'ก่อน/หลัง = median ของวัน [-12..-2] และ [+2..+12] รอบเหตุการณ์ (เว้นวัน transition 2 วันทั้งสองฝั่ง) — หน้าต่างเดียวกับ event-study ใน notebook 14, กันข้อมูล transient ตอนเริ่ม/TAM-recovery ที่หน้าต่างสั้นกว่านี้จะจับติดมาด้วย',
               'cit_recovery_model': 'expected_CIT_gain_C จาก 2d/6d (single-TAM calibration → เชิงทิศทาง)',
               'note': 'แสดง "วัดจริง" เทียบ "โมเดล" เพื่อให้วิศวกรตรวจว่าโมเดลตรงกับของจริงแค่ไหน',
           },
           'hx': {}}

    for hx in [c[:-len('_U_relative')] for c in feat.columns if c.endswith('_U_relative')]:
        ucol, qcol = f'{hx}_U_relative', f'{hx}_Q'
        ecol, dcol, rcol = f'{hx}_event_type', f'{hx}_days_on_duty', f'{hx}_run_id'
        if ecol not in feat.columns:
            continue
        cold_out_tag = COLD_CFG.get(hx, {}).get('cold_out')
        is_terminal = (cold_out_tag == CIT_TAG)
        sensi = _num(sens.loc[hx, 'CIT_sensitivity_degC_per_Qnorm']) if hx in sens.index else None
        corr  = _num(sens.loc[hx, 'Q_CIT_corr']) if hx in sens.index else None
        cit_model = _num(cpr.loc[hx, 'expected_CIT_gain_C'], 2) if hx in cpr.index else None

        sub = feat[[c for c in [ucol, qcol, ecol, dcol, rcol] if c in feat.columns]].copy()
        sub['cold_out'] = proc[cold_out_tag].reindex(sub.index) if cold_out_tag in proc.columns else np.nan
        sub['charge']   = charge.reindex(sub.index) if charge is not None else charge_mean
        sub = sub.reset_index()   # positional access for previous-row lookup

        # Bypass-cleaning correction: Operating_State stays NORMAL through online
        # bypass cleans (daily averages + shared flow meters hide the diversion), so
        # single-row before/after values can land on corrupted transition days.
        # Robust windows: before = median of days [-(PRE+GAP)..-GAP], after = median of
        # days [+GAP..+(GAP+POST)] around the event, skipping GAP transition days on both
        # sides. Matches notebook 14's event-study window (10-day medians, 2-day gap) — the
        # production window here used to be shorter (2-5 / 1-4 days) and started averaging
        # just 1 day after the event, which is exactly the startup/TAM-recovery-transient
        # risk the wider window avoids; the two are now reconciled to one definition.
        # Known unaddressed edge case (shared with notebook 14's version of this window):
        # cleaning events closer together than PRE+GAP+GAP+POST=~22 days have overlapping
        # pre/post windows, which biases both events' measured recovery — no minimum-spacing
        # guard exists yet. Rare in this dataset but visible for E113A's early-2021 events.
        PRE, POST, GAP = 10, 10, 2

        def robust(colvals, pos, side):
            lo, hi = (pos - PRE - GAP, pos - GAP) if side == 'before' else (pos + GAP, pos + GAP + POST)
            vals = colvals.iloc[max(0, lo): hi + 1].dropna()
            return float(vals.median()) if len(vals) else None

        cleans = []
        for pos in range(1, len(sub)):
            row = sub.iloc[pos]
            et = row.get(ecol)
            if et not in ('SWITCH', 'TAM') or row.get(dcol) != 0:   # reset row only
                continue
            u_b, u_a = robust(sub[ucol], pos, 'before'), robust(sub[ucol], pos, 'after')
            q_b, q_a = robust(sub[qcol], pos, 'before'), robust(sub[qcol], pos, 'after')
            u_b, u_a = _num(u_b), _num(u_a)
            q_b, q_a = _num(q_b, 0), _num(q_a, 0)
            u_rec = _num((u_a - u_b)) if (u_a is not None and u_b is not None) else None
            q_rec = _num((q_a - q_b), 0) if (q_a is not None and q_b is not None) else None
            ch = row.get('charge'); ch = float(ch) if pd.notna(ch) and ch else charge_mean

            # CIT recovered — measured
            co_b, co_a = robust(sub['cold_out'], pos, 'before'), robust(sub['cold_out'], pos, 'after')
            if is_terminal and co_b is not None and co_a is not None:
                cit_meas = _num(co_a - co_b, 2)
                cit_method = 'cold_out jump (=CIT ตรง)'
                estimable = True
            elif sensi is not None and q_rec is not None:
                cit_meas = _num(sensi * (q_rec / ch), 2)
                cit_method = 'ΔQ_norm × sensitivity'
                estimable = (sensi > 0) and (corr is not None and abs(corr) >= CORR_MIN)
            else:
                cit_meas, cit_method, estimable = None, '—', False

            # fouling rate of the run that ended (run N-1)
            run_after = row.get(rcol)
            run_ended = None
            if pd.notna(run_after):
                frx = fr[(fr.HX == hx) & (fr.Run == int(run_after) - 1)]
                if not frx.empty:
                    r = frx.iloc[0]
                    N = int(r.get('N_regression_pts', 0)); R2 = _num(r.get('R2'))
                    # canonical reliability decision: the `reliable` column already produced by
                    # nb_audit.robust_fouling_rate (slope/CI/R2/oscillation/span/Rf gates) —
                    # do not redefine it here (previously an independent, disagreeing R2/N gate).
                    run_ended = dict(run=int(r['Run']), duration_days=_num(r.get('Duration_days'), 1),
                                     dUrel_per_month=_num(r.get('dUrel_per_month')), R2=R2, N=N,
                                     reliable=bool(r.get('reliable')))

            note = ''
            if not estimable and cit_meas is not None:
                note = 'sensitivity อ่อน/downstream — ค่า CIT วัดจริงไม่น่าเชื่อถือ'
            cleans.append(dict(
                date=row['Timestamp'].strftime('%Y-%m-%d'), type=et, method_label=EVENT_LABEL.get(et, et),
                run_ended=run_ended, U_before=u_b, U_after=u_a, U_recovered=u_rec,
                Q_before=q_b, Q_after=q_a, Q_recovered_kW=q_rec,
                cit_measured_C=cit_meas, cit_measured_method=cit_method, gain_estimable=bool(estimable),
                cit_model_C=cit_model, note=note))

        # next-clean forecast row (from end_of_run.json)
        eh = eor['hx'].get(hx, {})
        duty, urel = eh.get('duty', {}), eh.get('urel', {})
        fc = None
        days = duty.get('days_remaining'); pdate = duty.get('projected_date')
        if days is None: days = urel.get('days_remaining'); pdate = urel.get('projected_date')
        if pdate or (eh.get('flags', {}) or {}).get('past_trigger'):
            fc = dict(projected_date=pdate, days_remaining=days,
                      past_trigger=bool((eh.get('flags', {}) or {}).get('past_trigger')),
                      cit_loss_now_C=(eh.get('consequence', {}) or {}).get('cit_loss_now_C'))

        out['hx'][hx] = dict(
            sensitivity=dict(CIT_sensitivity_degC_per_Qnorm=sensi, Q_CIT_corr=corr, is_terminal_CIT=is_terminal),
            n_cleans=len(cleans), cleans=cleans, forecast_next=fc)

    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    tot = sum(v['n_cleans'] for v in out['hx'].values())
    print(f'Wrote {OUT.name}: {len(out["hx"])} HX, {tot} cleaning events, {OUT.stat().st_size // 1024} KB')


if __name__ == '__main__':
    main()
