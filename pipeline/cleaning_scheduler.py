"""
Cleaning schedule to TAM 2028 (+ post-2028 extrapolation) — requirement F3/F4.

Method: per-HX ANALYTIC optimal cleaning interval (transparent, hand-checkable —
preferred over black-box optimization per the engineer's explainability priority):

  CIT loss grows ~linearly during a run:  L(t) = r · t     [°C], r = °C/day
  Cleaning every T days costs, per day:   f(T) = k·r·T/2 + C/T
      k = ฿/day per °C of CIT deficit  (plant formula: STD_ENERGY × Feed_KBD × NG_PRICE)
      C = cleaning cost per event [฿]
  Minimize f(T)  →  T* = sqrt(2·C / (k·r))       (classic optimal-interval result)

r per HX is MEASURED: median CIT recovery per clean ÷ median run duration
(cleaning_history.json — the audited sawtooth jumps), falling back to the model
CIT gain over the current-run days-to-trigger (end_of_run.json).

Constraints from the plant bypass list (bypass_config): only HX with a real
bypass can be cleaned online — the rest wait for TAM 2028. T* is clipped to
[MIN_INTERVAL, days-to-TAM].

Outputs dashboard/data/cleaning_schedule.json:
  per_hx: T_opt, freq/yr, scheduled dates to TAM-2028, net saving, rationale
  timeline: flat event list for the Gantt
  post_2028: projected state/frequency for the next 4-year cycle

Run: python pipeline/cleaning_scheduler.py
"""
import os, sys, json, math
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / 'dashboard' / 'data'
OUT  = DATA / 'cleaning_schedule.json'
sys.path.append(str(REPO / 'notebooks'))
sys.path.append(str(REPO / 'pipeline'))
from export_economics import DEFAULT_CLEANING_COST

M3_PER_BBL = 0.1589873
NEXT_TAM = pd.Timestamp(os.environ.get('CPHT_NEXT_TAM', '2028-06-01'))   # placeholder — รอวิศวกร
POST_CYCLE_YEARS = 4
MIN_INTERVAL = 60      # don't schedule online cleans closer than this (logistics floor)
MIN_RATE = 1e-4        # °C/day below this = effectively no CIT decay -> TAM only
# hard cap — real-world crew/logistics ceiling. Tightened 2026-07-20: 2-3/yr in normal
# operation (was 4/yr, "4 only in an emergency"). Configurable via CPHT_MAX_CLEANS_PER_YEAR;
# default matches config/operating_limits.yaml and pipeline/cleaning_scheduler_network.py.
MAX_FREQ_PER_YEAR = int(os.environ.get('CPHT_MAX_CLEANS_PER_YEAR', 3))
MIN_T_FROM_FREQ_CAP = 365.0 / MAX_FREQ_PER_YEAR


def _load(name, default=None):
    p = DATA / name
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else default


def main():
    econ  = _load('economics.json', {})
    chist = _load('cleaning_history.json', {'hx': {}})
    eor   = _load('end_of_run.json', {'hx': {}})
    logi  = _load('cleaning_logistics.json', {'hx': []})
    logi_by = {r['HX']: r for r in logi.get('hx', [])}

    pc = econ.get('plant_constants', {})
    feed_kbd = econ.get('feed_kbd') or 79.3
    k_per_C_day = pc.get('STD_ENERGY', 0.74) * feed_kbd * pc.get('NG_PRICE', 390)   # ฿/day/°C
    as_of = pd.Timestamp((chist.get('as_of') or eor.get('as_of') or pd.Timestamp.now().strftime('%Y-%m-%d')))
    days_to_tam = max(1, (NEXT_TAM - as_of).days)

    econ_by = {r['HX']: r for r in econ.get('per_hx', [])}
    per_hx, timeline = [], []

    for hx, e in econ_by.items():
        dC_full = e['cit_gain_C']                   # measured-first ΔCIT per clean (full clean)
        cost = e.get('cleaning_cost') or DEFAULT_CLEANING_COST
        lg = logi_by.get(hx, {})
        online = bool(lg.get('bypass')) or bool(lg.get('swap_capable'))
        # ONLINE_PARTIAL (bypass_config.py): only some shells can be pulled online, so an
        # online clean recovers a fraction of the full ΔCIT — the rest waits for TAM.
        duty_frac = lg.get('duty_fraction', 1.0) if lg.get('duty_fraction') is not None else 1.0
        dC = (dC_full * duty_frac) if dC_full else dC_full

        # r = CIT decay rate [°C/day]: measured recovery / median run duration
        h = chist.get('hx', {}).get(hx, {})
        durs = [c['run_ended']['duration_days'] for c in h.get('cleans', [])
                if c.get('run_ended') and c['run_ended'].get('duration_days')]
        if durs and dC:
            r = dC / float(np.median(durs))
        else:
            d_eor = eor.get('hx', {}).get(hx, {})
            days_rem = (d_eor.get('urel', {}) or {}).get('days_remaining') or 120
            r = (dC or 1.0) / max(30.0, float(days_rem))
        rationale = []

        if not online:
            per_hx.append(dict(HX=hx, online=False, T_opt_days=None, freq_per_year=0,
                               next_dates=[str(NEXT_TAM.date())], r_C_per_day=round(r, 5),
                               cit_gain_C=dC, cleaning_cost=cost,
                               net_saving_thb_yr=None,
                               rationale='ไม่มี bypass (list โรงงาน) — ล้างได้เฉพาะ TAM 2028'))
            timeline.append(dict(HX=hx, date=str(NEXT_TAM.date()), kind='TAM'))
            continue

        if r < MIN_RATE:
            per_hx.append(dict(HX=hx, online=True, T_opt_days=None, freq_per_year=0,
                               next_dates=[], r_C_per_day=round(r, 6),
                               cit_gain_C=dC, cleaning_cost=cost, net_saving_thb_yr=0,
                               rationale='อัตราการเสีย CIT ต่ำมาก — ยังไม่คุ้มล้างก่อน TAM'))
            continue

        T_star = math.sqrt(2 * cost / (k_per_C_day * r))
        T = float(np.clip(T_star, max(MIN_INTERVAL, MIN_T_FROM_FREQ_CAP), days_to_tam))
        freq = 365.0 / T
        # daily cost with vs without the optimal program (no-clean baseline capped at dC)
        f_opt = k_per_C_day * r * T / 2 + cost / T
        f_none = k_per_C_day * min(r * days_to_tam, dC)          # steady loss if never cleaned (capped at gain)
        net_yr = max(0.0, (f_none - f_opt)) * 365
        dates = []
        t = as_of + pd.Timedelta(days=round(T))
        while t < NEXT_TAM - pd.Timedelta(days=MIN_INTERVAL // 2):
            dates.append(str(t.date()))
            timeline.append(dict(HX=hx, date=str(t.date()), kind='ONLINE'))
            t += pd.Timedelta(days=round(T))
        timeline.append(dict(HX=hx, date=str(NEXT_TAM.date()), kind='TAM'))
        per_hx.append(dict(
            HX=hx, online=True, T_opt_days=round(T), T_unclipped_days=round(T_star),
            freq_per_year=round(freq, 2), next_dates=dates,
            r_C_per_day=round(r, 5), cit_gain_C=dC, cit_gain_source=e.get('cit_gain_source'),
            cleaning_cost=cost, net_saving_thb_yr=round(net_yr), duty_fraction=round(duty_frac, 3),
            rationale=f'T* = sqrt(2×{cost:,}/({k_per_C_day:,.0f}×{r:.4f})) = {T_star:.0f} วัน'
                      + (f' (ชนเพดาน {MAX_FREQ_PER_YEAR} ครั้ง/ปี)' if T_star < MIN_T_FROM_FREQ_CAP else '')
                      + f' → ล้างทุก ~{T:.0f} วัน ({freq:.1f} ครั้ง/ปี)'
                      + (f' [ล้าง online ได้บางส่วน {duty_frac*100:.0f}% — อีก shell รอ TAM]' if duty_frac < 1 else '')))

    per_hx.sort(key=lambda x: -(x.get('net_saving_thb_yr') or 0))
    for i, p in enumerate(per_hx, 1):
        p['priority'] = i

    # post-2028 extrapolation: everything resets at TAM; same rates → same optimal program
    post = dict(
        assumption='ทุก HX ถูกล้างครบที่ TAM 2028 (reset) แล้ว fouling ดำเนินด้วย rate เดิม',
        cycle=[str(NEXT_TAM.date()), str((NEXT_TAM + pd.DateOffset(years=POST_CYCLE_YEARS)).date())],
        per_hx=[dict(HX=p['HX'],
                     first_clean_after_tam=(str((NEXT_TAM + pd.Timedelta(days=p['T_opt_days'])).date())
                                            if p.get('T_opt_days') else None),
                     freq_per_year=p['freq_per_year'],
                     expected_cleans_in_cycle=round(p['freq_per_year'] * POST_CYCLE_YEARS, 1))
                for p in per_hx])

    out = dict(
        as_of=str(as_of.date()), next_tam=str(NEXT_TAM.date()), next_tam_assumed=True,
        k_baht_per_C_day=round(k_per_C_day), feed_kbd=feed_kbd,
        method='analytic optimal interval T*=sqrt(2C/(k·r)) — minimize fouling-energy cost + cleaning cost; '
               'r จากค่าวัดจริง (median recovery ÷ median run duration); เฉพาะ HX ที่มี bypass จริงเท่านั้นที่ล้าง online ได้; '
               f'เพดานความถี่ {MAX_FREQ_PER_YEAR} ครั้ง/ปีต่อ HX (ข้อจำกัดหน้างานจริง)',
        per_hx=per_hx, timeline=sorted(timeline, key=lambda t: t['date']), post_2028=post,
        totals=dict(online_hx=sum(1 for p in per_hx if p['online']),
                    tam_only=sum(1 for p in per_hx if not p['online']),
                    total_net_saving_thb_yr=round(sum(p.get('net_saving_thb_yr') or 0 for p in per_hx))))
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'Wrote {OUT.name}: {len(per_hx)} HX, {len(timeline)} events to {NEXT_TAM.date()}, '
          f'net ~{out["totals"]["total_net_saving_thb_yr"]:,} ฿/yr')
    for p in per_hx[:6]:
        print(f"  #{p['priority']} {p['HX']:8s} online={p['online']} T={p.get('T_opt_days')}d "
              f"freq={p['freq_per_year']}/yr net={p.get('net_saving_thb_yr')}")


if __name__ == '__main__':
    main()
