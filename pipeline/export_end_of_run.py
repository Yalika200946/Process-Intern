"""
Export per-HX End-of-Run duty forecast for the dashboard (ข้อ 1 + ข้อ 6).

The chemical-engineer's request: a graph that shows, for the *current* run of each
HX, how far it is from the "must-clean" point and how many days remain — plus the
Q -> CIT consequence when it gets there.

Engineering basis (both views the UI toggles between):
  * TRIGGER (fouling view): U_relative — throughput-independent fouling indicator
    (U/U_clean). Clean = 1.0. Trigger = 1 - TRIGGER_DROP_FRAC (12.5% loss of clean
    U), the same criterion notebook 5 / METHODOLOGY §4 use.
  * CONSEQUENCE (duty view): actual duty Q [kW] declining vs the clean-model Q, with
    a q_trigger line = clean_Q - threshold_shortfall. "Duty shortfall" (kW below
    clean) is exactly the `deviation` signal (predicted_clean_Q - actual_Q).

Time-to-clean = linear extrapolation of the current run (same method as 3b /
Time_To_Clean_Prediction.csv). This reuses already-computed CSVs — no recompute of
fouling physics here — and pairs each HX with its Q->CIT sensitivity (2c) so the UI
can state Q-loss[kW] and CIT-loss[°C] now and at the trigger.

Run: python pipeline/export_end_of_run.py
"""
import os, sys, json
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
NB   = REPO / 'notebooks'
DATA = Path(os.environ.get('CPHT_DATA_DIR', r'C:\Desktop\Bangchak Internship 2026\Data'))
OUT  = REPO / 'dashboard' / 'data' / 'end_of_run.json'
sys.path.append(str(NB))

# --- engineering constants (documented, tunable) ---
TRIGGER_DROP_FRAC   = 0.125   # U_relative loss that defines "must clean" (12.5%), per notebook 5
PROJECT_HORIZON_DAYS = 240    # cap the forward projection drawn on the chart
PROJECT_STEP_DAYS    = 7      # weekly points on the projection line
NEAR_THRESHOLD_DAYS  = 60     # "ใกล้เกณฑ์" flag
UNRELIABLE_R2        = 0.30   # current-run fit below this = low-confidence trend


def _num(v, nd=3):
    return None if v is None or (isinstance(v, float) and not np.isfinite(v)) else round(float(v), nd)


def _load_json(name):
    p = REPO / 'dashboard' / 'data' / name
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else None


def main():
    feat = pd.read_csv(DATA / 'Feature_calculated.csv', parse_dates=['Timestamp']).set_index('Timestamp')
    dev  = pd.read_csv(DATA / 'Q_Deviation_Signal.csv', parse_dates=['Timestamp'])
    fr   = pd.read_csv(DATA / 'Fouling_Rate_By_Run.csv')
    ttc  = pd.read_csv(DATA / 'Time_To_Clean_Prediction.csv').set_index('HX')
    sens = pd.read_csv(DATA / 'Q_CIT_Sensitivity.csv').set_index('HX')

    ranking = {r['HX']: r for r in (_load_json('hx_ranking.json') or [])}

    as_of = feat.index.max()
    trigger_urel = 1.0 - TRIGGER_DROP_FRAC

    out = {'as_of': as_of.strftime('%Y-%m-%d'),
           'trigger_drop_frac': TRIGGER_DROP_FRAC,
           'trigger_urel': round(trigger_urel, 4),
           'hx': {}}

    for hx in [c[:-len('_U_relative')] for c in feat.columns if c.endswith('_U_relative')]:
        ur = feat[f'{hx}_U_relative'].dropna()
        if ur.empty:
            continue
        rid_col, dod_col = f'{hx}_run_id', f'{hx}_days_on_duty'
        cur_rid = feat[rid_col].dropna().iloc[-1] if rid_col in feat else None
        cur_dod = _num(feat[dod_col].dropna().iloc[-1]) if dod_col in feat else None
        cur_urel = float(ur.iloc[-1])

        # ---- current-run fouling rate (dU_relative/day), from the ROBUST Fouling_Rate_By_Run ----
        # Only trust a rate the physics-gate marked `reliable` (slope<0, in-service, enough span).
        # Priority: current run if reliable → most recent OTHER reliable run of this HX (flagged) →
        # current-run tail fit → none. Prefer the recent-window ("current") rate over the whole-run
        # slope when it's available and still negative (long/asymptotic runs read low whole-run).
        # This supersedes the old "last row in file" logic that mixed a finished run's rate into
        # the current card (the E112C contradiction).
        def _rate_of(row):
            rec = _num(row.get('dUrel_per_day_recent'), 6)
            whole = _num(row.get('dUrel_per_day'), 6)
            return rec if (rec is not None and rec < 0) else whole
        frx_all = fr[fr.HX == hx]
        frx_rel = frx_all[frx_all.get('reliable') == True] if 'reliable' in frx_all else frx_all  # noqa: E712
        frx_cur = frx_rel[frx_rel.Run == cur_rid] if cur_rid is not None else frx_rel.iloc[0:0]
        rate_urel, r2, run_dur, rate_source = None, None, None, None
        if not frx_cur.empty:
            last = frx_cur.iloc[-1]
            rate_urel = _rate_of(last); r2 = _num(last.get('R2')); run_dur = _num(last.get('Duration_days'), 1)
            rate_source = 'current_run'
        if rate_urel is None and not frx_rel.empty:   # most recent OTHER reliable run of this HX
            last = frx_rel.sort_values('Run').iloc[-1]
            rate_urel = _rate_of(last); r2 = _num(last.get('R2')); run_dur = _num(last.get('Duration_days'), 1)
            rate_source = 'previous_reliable_run'
        if rate_urel is None:   # last resort: fit current-run tail (no reliable history)
            if cur_rid is not None and dod_col in feat:
                run = feat[feat[rid_col] == cur_rid]
                x, y = run[dod_col].values, run[f'{hx}_U_relative'].values
                m = np.isfinite(x) & np.isfinite(y)
                if m.sum() >= 5:
                    rate_urel = _num(np.polyfit(x[m], y[m], 1)[0], 6)
                    rate_source = 'current_run_fit'

        # ---- URel view: days to trigger ----
        past_urel = cur_urel <= trigger_urel
        days_urel = 0.0 if past_urel else (
            (trigger_urel - cur_urel) / rate_urel if rate_urel and rate_urel < 0 else None)
        proj_urel_days, proj_urel_val = [], []
        if rate_urel is not None:
            horizon = min(PROJECT_HORIZON_DAYS, max(60.0, (days_urel or 0) * 1.3))
            for t in range(0, int(horizon) + 1, PROJECT_STEP_DAYS):
                proj_urel_days.append(t)
                proj_urel_val.append(round(max(0.0, cur_urel + rate_urel * t), 3))

        urel_block = dict(
            current=round(cur_urel, 3), baseline=1.0, trigger=round(trigger_urel, 3),
            rate_per_day=rate_urel, rate_source=rate_source,
            days_remaining=_num(days_urel, 0), past_trigger=bool(past_urel),
            projected_date=(as_of + pd.Timedelta(days=days_urel)).strftime('%Y-%m-%d') if days_urel else None,
            proj=dict(days=proj_urel_days, val=proj_urel_val))

        # ---- Duty view: shortfall (kW) vs clean Q, from deviation signal + 3b ----
        dh = dev[dev.HX == hx]
        clean_Q = _num(dh['predicted_Q'].median(), 0) if 'predicted_Q' in dh else None
        cur_Q   = _num(dh['Q'].dropna().iloc[-1], 0) if 'Q' in dh and not dh['Q'].dropna().empty else None
        t = ttc.loc[hx] if hx in ttc.index else None
        cur_short = _num(t['current_deviation'], 0) if t is not None else None
        thr_short = _num(t['threshold'], 0) if t is not None else None
        rate_short = _num(t['rate_degC_per_day'], 3) if t is not None else None       # kW/day of shortfall
        days_duty = _num(t['days_to_threshold'], 0) if t is not None else None
        proj_duty_days, proj_duty_q = [], []
        if cur_Q is not None and rate_short is not None:
            horizon = min(PROJECT_HORIZON_DAYS, max(60.0, (days_duty or 0) * 1.3)) if days_duty else 120
            for tt in range(0, int(horizon) + 1, PROJECT_STEP_DAYS):
                proj_duty_days.append(tt)
                proj_duty_q.append(round(cur_Q - rate_short * tt, 0))   # Q declines as shortfall grows

        duty_block = dict(
            clean_Q=clean_Q, current_Q=cur_Q,
            q_trigger=round(clean_Q - thr_short, 0) if (clean_Q is not None and thr_short is not None) else None,
            current_shortfall=cur_short, threshold_shortfall=thr_short,
            rate_shortfall_per_day=rate_short, days_remaining=days_duty,
            past_trigger=bool(cur_short is not None and thr_short is not None and cur_short >= thr_short),
            projected_date=(str(t['projected_need_by_date'])[:10]
                            if t is not None and pd.notna(t['projected_need_by_date']) else None),
            proj=dict(days=proj_duty_days, q=proj_duty_q))

        # ---- Q -> CIT consequence (2c sensitivity + ranking) ----
        rk = ranking.get(hx, {})
        cit_sens = _num(sens.loc[hx, 'CIT_sensitivity_degC_per_Qnorm']) if hx in sens.index else None
        cit_loss_now = _num(rk.get('expected_CIT_gain_C'), 2)          # recoverable CIT by cleaning now
        q_loss_pct = _num(rk.get('Q_drop_%'), 1)
        q_loss_now_kW = cur_short
        cit_loss_trig = None
        if cit_loss_now not in (None, 0) and cur_short and thr_short and cur_short > 0:
            cit_loss_trig = _num(cit_loss_now * (thr_short / cur_short), 2)
        conseq = dict(q_loss_now_kW=q_loss_now_kW, q_loss_pct=q_loss_pct,
                      cit_sensitivity_degC_per_Qnorm=cit_sens,
                      cit_loss_now_C=cit_loss_now, cit_loss_at_trigger_C=cit_loss_trig,
                      q_loss_at_trigger_kW=thr_short)

        # ---- degradation flags + Thai signal text (ข้อ 6) ----
        # trend is only asserted from the CURRENT reliable run; anything else (a prior
        # reliable run, or a raw tail fit) is surfaced as "current data insufficient".
        stale_rate = rate_source is not None and rate_source != 'current_run'
        worsening = bool(rk.get('worsening')) and not stale_rate
        improving = (not stale_rate) and rate_urel is not None and rate_urel >= 0
        unreliable = r2 is not None and r2 < UNRELIABLE_R2
        near = days_urel is not None and 0 < days_urel <= NEAR_THRESHOLD_DAYS
        signals = []
        if past_urel:
            signals.append('เลยเกณฑ์ล้างแล้ว (U_relative ต่ำกว่าเกณฑ์) — ควรวางแผนล้าง')
        elif near:
            signals.append(f'ใกล้เกณฑ์ล้าง ~{int(days_urel)} วัน')
        if stale_rate:
            src_th = ('รอบก่อนหน้า' if rate_source == 'previous_reliable_run' else 'การ fit ปัจจุบัน (ยังไม่ผ่านเกณฑ์เชื่อถือ)')
            signals.append(f'⚠ อัตราปัจจุบันยังไม่มีรอบที่เชื่อถือได้ (ใช้{src_th}) — งดสรุปแนวโน้ม')
        else:
            if rate_urel is not None and rate_urel < 0:
                signals.append(f'U_relative ลดลง ~{abs(rate_urel*30):.3f}/เดือน (สกปรกต่อเนื่อง)')
            if improving:
                signals.append('แนวโน้มไม่แย่ลง (rate ≈ 0 หรือดีขึ้น) — ยังไม่จำเป็นต้องล้าง')
        if q_loss_pct:
            signals.append(f'Duty ลดจากสภาพสะอาด ~{q_loss_pct:.0f}%')
        if cit_loss_now:
            signals.append(f'ล้างแล้วคาดคืน CIT ~{cit_loss_now:+.1f}°C')
        if unreliable:
            signals.append(f'⚠ ความเชื่อมั่นแนวโน้มต่ำ (R²={r2:.2f})')

        health = ('critical' if past_urel else 'warn' if near or worsening else
                  'ok' if improving or (days_urel and days_urel > 120) else 'watch')

        out['hx'][hx] = dict(
            effort_tier=(t['effort_tier'] if t is not None else rk.get('effort_tier')),
            confidence=(t['threshold_confidence'] if t is not None else None),
            days_on_duty=cur_dod, run_duration_days=run_dur, r2=r2, health=health,
            urel=urel_block, duty=duty_block, consequence=conseq,
            flags=dict(worsening=worsening, improving=improving, unreliable=unreliable,
                       near_threshold=bool(near), past_trigger=bool(past_urel)),
            signals=signals)

    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f'Wrote {OUT.name}: {len(out["hx"])} HX, as_of {out["as_of"]}, {OUT.stat().st_size // 1024} KB')


if __name__ == '__main__':
    main()
