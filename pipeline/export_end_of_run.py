"""
Export per-HX End-of-Run duty forecast for the dashboard (ข้อ 1 + ข้อ 6).

The chemical-engineer's request: a graph that shows, for the *current* run of each
HX, how far it is from the "must-clean" point and how many days remain — plus the
Q -> CIT consequence when it gets there.

Engineering basis (both views the UI toggles between):
  * TRIGGER (fouling view): the UI still displays U_relative — throughput-independent
    fouling indicator (U/U_clean), clean = 1.0, trigger = 1 - TRIGGER_DROP_FRAC (12.5%
    loss of clean U), the same criterion notebook 5 / METHODOLOGY §4 use. But the
    underlying curve fit/extrapolation (Fouling_Rate_By_Run.csv, since 2026-07-19) is now
    done in Rf (fouling resistance) space, the metric the mechanistic literature actually
    formulates (Kern-Seaton). This module converts Rf<->U_relative via
    Rf = (1/U_relative - 1)/U_clean (see `_rf_to_urel`/`_urel_to_rf`/`_durel_dt_from_drf_dt`)
    so the dashboard's user-facing numbers/chart stay in the familiar U_relative units.
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
sys.path.append(str(REPO))
from src.models import fouling_curves as cm
from src.validation import nb_audit as A
from src.models.phm_config import NEAR_THRESHOLD_DAYS

# --- engineering constants (documented, tunable) ---
TRIGGER_DROP_FRAC   = 0.125   # U_relative loss that defines "must clean" (12.5%), per notebook 5
PROJECT_HORIZON_DAYS = 240    # cap the forward projection drawn on the chart
PROJECT_STEP_DAYS    = 7      # weekly points on the projection line
# NEAR_THRESHOLD_DAYS ("ใกล้เกณฑ์" flag) now imported from phm_config -- single shared source
# with threshold_backtest.py's false-alarm/missed-warning horizon (ข้อ 6), see phm_config.py.
UNRELIABLE_R2        = 0.30   # current-run fit below this = low-confidence trend


def _num(v, nd=3):
    return None if v is None or (isinstance(v, float) and not np.isfinite(v)) else round(float(v), nd)


def _rf_to_urel(rf, u_clean):
    """Rf = (1/U_relative - 1)/U_clean  <=>  U_relative = 1/(1 + Rf*U_clean)."""
    if rf is None or u_clean is None or not np.isfinite(rf) or not np.isfinite(u_clean) or u_clean <= 0:
        return None
    return 1.0 / (1.0 + rf * u_clean)


def _urel_to_rf(urel, u_clean):
    if urel is None or u_clean is None or not np.isfinite(urel) or not np.isfinite(u_clean) or urel <= 0 or u_clean <= 0:
        return None
    return (1.0 / urel - 1.0) / u_clean


def _durel_dt_from_drf_dt(rf_now, drf_dt, u_clean):
    """Chain rule on U_relative = 1/(1+Rf*U_clean): dU_rel/dt = -U_clean*dRf/dt / (1+Rf*U_clean)^2."""
    if any(v is None or not np.isfinite(v) for v in (rf_now, drf_dt, u_clean)) or u_clean <= 0:
        return None
    denom = (1.0 + rf_now * u_clean) ** 2
    return -u_clean * drf_dt / denom if denom > 0 else None


def _load_json(name):
    p = REPO / 'dashboard' / 'data' / name
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else None


def main():
    feat = pd.read_csv(DATA / 'Feature_calculated.csv', parse_dates=['Timestamp']).set_index('Timestamp')
    dev  = pd.read_csv(DATA / 'Q_Deviation_Signal.csv', parse_dates=['Timestamp'])
    fr   = pd.read_csv(DATA / 'Fouling_Rate_By_Run.csv')
    ttc  = pd.read_csv(DATA / 'Time_To_Clean_Prediction.csv').set_index('HX')
    if 'rate_kW_per_day' not in ttc.columns and 'rate_degC_per_day' in ttc.columns:
        ttc = ttc.rename(columns={'rate_degC_per_day': 'rate_kW_per_day'})
    sens = pd.read_csv(DATA / 'Q_CIT_Sensitivity.csv').set_index('HX')

    ranking = {r['HX']: r for r in (_load_json('hx_ranking.json') or [])}

    # BUG FOUND 2026-07-20 (plant engineer flagged the "signals" text and this panel's own
    # "คืน CIT ได้" line showing +8.3 for E113A while the "แผนล้าง HX" tab showed +4.3): this
    # used rk['expected_CIT_gain_C'], notebook 08's early-stage proxy, for cit_loss_now below --
    # same root cause already fixed in export_cleaning_history.py (that file now reports the
    # MEDIAN of E113A's own measured, gain-estimable, non-TAM events, +4.3, matching the Plan
    # tab exactly). Prefer that same per-HX reference value here too, read from
    # Cleaning_Events.csv (written by export_cleaning_history.py, one pipeline-run older at
    # most since both run in the same POST list every time -- self-corrects every run, and
    # falls back to the proxy only on a from-scratch first run before that file exists).
    measured_ref_by_hx = {}
    events_csv = DATA / 'Cleaning_Events.csv'
    if events_csv.exists():
        _ev = pd.read_csv(events_csv)
        if 'cit_model_C' in _ev.columns:
            measured_ref_by_hx = _ev.dropna(subset=['cit_model_C']).groupby('HX')['cit_model_C'].last().to_dict()

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

        # ---- current-run fouling rate, from the ROBUST Fouling_Rate_By_Run ----
        # Only trust a rate the physics-gate marked `reliable` (dRf/dt>0, in-service, enough span).
        # Priority: current run if reliable → most recent OTHER reliable run of this HX (flagged) →
        # current-run tail fit → none. `dRf_per_day` is now itself the curve-aware TAIL slope
        # (nb_audit.robust_fouling_rate's linear-vs-asymptotic AIC race, fit directly on Rf per
        # the mechanistic literature — see curve_models.py), so it is preferred directly rather
        # than falling back to a raw noisy recent-60d window (that window is only used as a
        # secondary cross-check if the tail slope is unavailable). The result is converted to a
        # U_relative-space rate (`_durel_dt_from_drf_dt`) so the dashboard's user-facing number
        # stays in the familiar unit. This supersedes the old "last row in file" logic that mixed
        # a finished run's rate into the current card (the E112C contradiction).
        def _rate_of(row, urel_now):
            tail = _num(row.get('dRf_per_day'), 8)
            rec = _num(row.get('dRf_per_day_recent'), 8)
            rf_rate = tail if tail is not None else rec
            if rf_rate is None:
                return None
            u_clean = row.get('U_clean_run')
            rf_now = _urel_to_rf(urel_now, u_clean)
            return _num(_durel_dt_from_drf_dt(rf_now, rf_rate, u_clean), 6)

        def _curve_of(row):
            """Reconstruct the fitted rising-asymptote Rf(t) curve (A, tau, c, anchor day,
            U_clean of this run) for extrapolation, but only when the run's own data actually
            spans enough of the fitted time constant to trust the asymptote (span >= 0.5*tau)
            — otherwise a short run's curve fit is too uncertain to extrapolate and callers
            should fall back to a linear projection from the tail slope instead. The curve
            itself is fit in Rf-space (A_asymp/tau_days/Rf_inf_asymp now describe the Rf
            ceiling, not a U_relative floor); U_clean_run is carried alongside so callers can
            convert projected Rf(t) back to U_relative for display."""
            if row.get('model_selected') != 'asymptotic':
                return None
            A, tau, c, t0, span, u_clean = (row.get('A_asymp'), row.get('tau_days'), row.get('Rf_inf_asymp'),
                                             row.get('last_day_on_duty'), row.get('span_days'), row.get('U_clean_run'))
            if any(v is None or (isinstance(v, float) and not np.isfinite(v)) for v in (A, tau, c, t0, span, u_clean)):
                return None
            if tau <= 0 or span < 0.5 * tau or u_clean <= 0:
                return None
            return dict(A=float(A), tau=float(tau), c=float(c), t0=float(t0), u_clean=float(u_clean))

        # 4-state rate-evidence cascade (ข้อ 2), centralized in nb_audit.classify_rate_source so
        # export_end_of_run.py / phm_analysis.py's C1/C2 all agree on the same state names.
        cls_state, cls_row = A.classify_rate_source(fr, hx, cur_rid)
        rate_urel, r2, run_dur, rate_source, curve = None, None, None, None, None
        if cls_state == 'current_reliable_run':
            rate_urel = _rate_of(cls_row, cur_urel); r2 = _num(cls_row.get('R2')); run_dur = _num(cls_row.get('Duration_days'), 1)
            rate_source = 'current_reliable_run'
            curve = _curve_of(cls_row)   # only meaningful for the CURRENT run's own days-on-duty axis
        elif cls_state == 'previous_reliable_run':
            rate_urel = _rate_of(cls_row, cur_urel); r2 = _num(cls_row.get('R2')); run_dur = _num(cls_row.get('Duration_days'), 1)
            rate_source = 'previous_reliable_run'
        if rate_urel is None:   # last resort: fit current-run tail (no reliable history at all)
            if cur_rid is not None and dod_col in feat:
                run = feat[feat[rid_col] == cur_rid]
                x, y = run[dod_col].values, run[f'{hx}_U_relative'].values
                m = np.isfinite(x) & np.isfinite(y)
                if m.sum() >= 5:
                    rate_urel = _num(np.polyfit(x[m], y[m], 1)[0], 6)
                    rate_source = 'unreliable_current_fit'
        if rate_urel is None:
            rate_source = 'no_forecast'

        # ---- URel view: days to trigger ----
        # Prefer extrapolating along the fitted asymptotic curve (not linearly from the tail
        # slope) when the current run's own fit selected 'asymptotic' and has enough span to
        # trust the fitted time constant — a flattening run reaches a lower trigger LATER than a
        # naive linear countdown from its instantaneous rate would suggest.
        past_urel = cur_urel <= trigger_urel
        days_urel, curve_used = None, False
        if past_urel:
            days_urel = 0.0
        elif curve is not None:
            # trigger, expressed in the Rf-space the curve was actually fit in
            trigger_rf = _urel_to_rf(trigger_urel, curve['u_clean'])
            d_cross = cm.predict_cross('asymptotic', [curve['A'], curve['tau'], curve['c']],
                                        curve['t0'], trigger_rf, models=cm.MODELS_RISING,
                                        tmax=PROJECT_HORIZON_DAYS * 3, direction='rising')
            if d_cross is not None:
                days_urel = float(d_cross)
                curve_used = True
        if days_urel is None and rate_urel is not None and rate_urel < 0:
            days_urel = (trigger_urel - cur_urel) / rate_urel

        proj_urel_days, proj_urel_val = [], []
        if curve_used:
            horizon = min(PROJECT_HORIZON_DAYS, max(60.0, days_urel * 1.3))
            f_asym = cm.MODELS_RISING['asymptotic'][0]
            for t in range(0, int(horizon) + 1, PROJECT_STEP_DAYS):
                rf_t = float(f_asym(curve['t0'] + t, curve['A'], curve['tau'], curve['c']))
                urel_t = _rf_to_urel(rf_t, curve['u_clean'])
                if urel_t is None:
                    continue
                proj_urel_days.append(t)
                proj_urel_val.append(round(max(0.0, urel_t), 3))
        elif rate_urel is not None:
            horizon = min(PROJECT_HORIZON_DAYS, max(60.0, (days_urel or 0) * 1.3))
            for t in range(0, int(horizon) + 1, PROJECT_STEP_DAYS):
                proj_urel_days.append(t)
                proj_urel_val.append(round(max(0.0, cur_urel + rate_urel * t), 3))

        urel_block = dict(
            current=round(cur_urel, 3), baseline=1.0, trigger=round(trigger_urel, 3),
            rate_per_day=rate_urel, rate_source=rate_source, curve_projection=curve_used,
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
        rate_short = _num(t['rate_kW_per_day'], 3) if t is not None else None
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
        cit_loss_now = _num(measured_ref_by_hx.get(hx, rk.get('expected_CIT_gain_C')), 2)  # recoverable CIT by cleaning now
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
        stale_rate = rate_source is not None and rate_source != 'current_reliable_run'
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
            src_th = {'previous_reliable_run': 'รอบก่อนหน้า', 'unreliable_current_fit': 'การ fit ปัจจุบัน (ยังไม่ผ่านเกณฑ์เชื่อถือ)',
                      'no_forecast': 'ไม่มีข้อมูลเพียงพอ'}.get(rate_source, 'ไม่ทราบแหล่งที่มา')
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
        if curve_used:
            signals.append('คาดการณ์วันที่ต้องล้างตามเส้นโค้ง asymptotic (ไม่ใช่เส้นตรง) — อัตราการสกปรกกำลังชะลอตัว')

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
