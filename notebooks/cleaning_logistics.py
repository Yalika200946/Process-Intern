"""
Per-HX cleaning logistics (ข้อ 4): how each HX can be cleaned, whether it has a
spare/bypass, and its TAM history — the list the dashboard shows and that
centralises exactly what still needs to be confirmed by the plant engineer.

2026-07-12 fix: `cleaning_method`/`online_capable` used to come from
`Time_To_Clean_Prediction.csv`'s `effort_tier`, which was itself a HARD-CODED
guess (see 3b/2d) that directly contradicted the real plant bypass file (e.g.
E103AB/E106AB/E107AB/E109AB were marked "online-clean demonstrated" despite
having NO bypass; E101AB/E105AB were marked TAM-only despite HAVING one — and
E101CD's two shells were lumped together despite only one being bypassable).
`bypass_config.BYPASS_CONFIG` (parsed straight from the plant Excel) is now the
single source of truth for online-cleaning capability, including the 'partial'
case (only some shells in the group can be pulled online).

What is KNOWN (derived from the data / config, not guessed):
  * online_mode/duty_fraction -> bypass_config.BYPASS_CONFIG (real plant bypass list)
  * spare_shell      -> from cpht_config.PARALLEL_SHELL_GROUPS (E113A <-> E112C)
  * last_tam         -> cpht_features.TAM_DATE (verified whole-train reset 2024-06-14)
  * hot_stream/group -> cpht_features titles / cpht_config groups

What is PLACEHOLDER (labelled assumed, awaiting engineer):
  * next_tam date
  * exact online-cleaning PROCEDURE per HX (bypass tells us capability, not the
    step-by-step method — that still needs plant confirmation)

Run as a script to (re)write dashboard/data/cleaning_logistics.json.
"""
import os, sys, json
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.append(str(HERE))
from cpht_config import CPHT_1_HX, CPHT_2_HX, PARALLEL_SHELL_GROUPS
from cpht_features import HX_CONFIG as FULL_CFG, TAM_DATE, get_tam_dates
from bypass_config import BYPASS_CONFIG   # real plant bypass list (2026-07-08) — AUTHORITATIVE

LAST_TAM = get_tam_dates()[-1]   # latest plant-wide TAM detected in the data

DATA = Path(os.environ.get('CPHT_DATA_DIR', r'C:\Desktop\Bangchak Internship 2026\Data'))
OUT  = HERE.parent / 'dashboard' / 'data' / 'cleaning_logistics.json'

NEXT_TAM = '2028-06-01'      # PLACEHOLDER — รอวิศวกรยืนยัน
NEXT_TAM_ASSUMED = True

METHOD_TH = {
    'SWAP_CAPABLE':     'สลับเชลล์ออนไลน์ (มี spare) — ล้างได้โดยไม่หยุดเดินเครื่อง',
    'ONLINE_FULL':      'ล้างออนไลน์ได้เต็มรูป (มี bypass ครบ) — ไม่ต้องหยุดเดินเครื่อง',
    'ONLINE_PARTIAL':   'ล้างออนไลน์ได้บางส่วน (มี bypass แค่บาง shell) — อีก shell รอ TAM',
    'TAM_ONLY':         'ล้างได้เฉพาะช่วง TAM (ต้องหยุดเดินเครื่อง) — ไม่มี bypass',
}


def _spare_map():
    m = {}
    for a, b in PARALLEL_SHELL_GROUPS:
        m[a] = b
        m[b] = a
    return m


def classify(hx, spare):
    """Authoritative online-capability classification for one HX."""
    if hx in spare:
        return 'SWAP_CAPABLE'
    mode = BYPASS_CONFIG.get(hx, {}).get('online_mode', 'none')
    return {'full': 'ONLINE_FULL', 'partial': 'ONLINE_PARTIAL', 'none': 'TAM_ONLY'}[mode]


def main():
    spare = _spare_map()

    hx_rows = []
    for hx in CPHT_1_HX + CPHT_2_HX:
        tier = classify(hx, spare)
        bc = BYPASS_CONFIG.get(hx, {})
        duty_frac = 1.0 if tier == 'SWAP_CAPABLE' else bc.get('duty_fraction', 0.0)
        title = FULL_CFG.get(hx, {}).get('title', '')
        hot = title.split(' vs ')[-1].split('(')[0].strip() if ' vs ' in title else '—'
        hx_rows.append(dict(
            HX=hx,
            group='CPHT-1' if hx in CPHT_1_HX else 'CPHT-2',
            hot_stream=hot,
            effort_tier=tier,
            cleaning_method=METHOD_TH.get(tier, 'รอวิศวกรยืนยันวิธีล้าง'),
            swap_capable=(tier == 'SWAP_CAPABLE'),
            online_capable=(tier in ('SWAP_CAPABLE', 'ONLINE_FULL', 'ONLINE_PARTIAL')),
            duty_fraction=round(duty_frac, 3),
            spare_shell=spare.get(hx),                 # known for E113A/E112C, else None
            bypass=(bc.get('bypass') if hx in BYPASS_CONFIG else None),
            bypass_status=(('มี bypass' if bc.get('bypass') else 'ไม่มี — รอ TAM')
                           if hx in BYPASS_CONFIG else 'รอวิศวกร'),
            bypass_detail=(bc.get('remark') or None),
            last_tam=str(LAST_TAM.date()),
            next_tam=NEXT_TAM,
        ))

    out = dict(
        last_tam=str(LAST_TAM.date()),
        next_tam=NEXT_TAM, next_tam_assumed=NEXT_TAM_ASSUMED,
        note=('effort_tier / duty_fraction / spare / last_TAM / bypass มาจากข้อมูลจริง '
              '(bypass จาก list bypass Cleaning Heat Exchanger.xlsx — แหล่งเดียวที่ใช้ตัดสิน '
              'ว่าล้าง online ได้เต็ม/บางส่วน/ไม่ได้เลย); '
              'next_TAM ยังเป็น placeholder — รอวิศวกรยืนยัน'),
        hx=hx_rows,
    )
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'Wrote {OUT.name}: {len(hx_rows)} HX (last TAM {out["last_tam"]}, next {out["next_tam"]} [assumed])')


if __name__ == '__main__':
    main()
