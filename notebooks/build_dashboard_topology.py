"""
Generate dashboard/data/pfd_topology.json — the data-driven P&ID model.

Single source of truth for the dashboard's connected-piping diagram: reuses
cpht_config (train topology, chain links, parallel shells) and cpht_features
HX_CONFIG (cold/hot instrument tags + human labels), and stamps each tag with
its latest value from the cleaned process CSV so the P&ID shows real numbers.

Also emits the furnace Key-Constraints block (CIT/COT/O2/draft/FG/body/passes)
with latest values + normal/alarm bands.

Run: python build_dashboard_topology.py
"""
import os
import json, sys
from pathlib import Path
import pandas as pd

HERE = Path(__file__).parent
sys.path.append(str(HERE))
from cpht_config import (CPHT_1_HX, CPHT_2_HX, CHAIN_PREDECESSOR,
                         PARALLEL_SHELL_GROUPS, HX_CONFIG as COLD_CFG)
from cpht_features import HX_CONFIG as FULL_CFG, parse_hx

REPO = HERE.parent
DATA = Path(os.environ.get('CPHT_DATA_DIR', r'C:\Desktop\Bangchak Internship 2026\Data'))
OUT  = REPO / 'dashboard' / 'data' / 'pfd_topology.json'

# Optional CLI args let the backend regenerate topology from an uploaded file:
#   python build_dashboard_topology.py [input_cleaned_csv] [output_json]
INPUT_CSV = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA / 'Process_information_cleaned.csv'
OUT       = Path(sys.argv[2]) if len(sys.argv) > 2 else OUT

# ---- latest process values ----
proc = pd.read_csv(INPUT_CSV, index_col='Timestamp', parse_dates=True)
last = proc.iloc[-1]
last_ts = proc.index[-1]

def val(tag):
    if tag and tag in proc.columns:
        v = last[tag]
        return None if pd.isna(v) else round(float(v), 2)
    return None

# ---- predecessor HX (invert CHAIN_PREDECESSOR via cold_out->cold_in) ----
coldout_to_hx = {c['cold_out']: hx for hx, c in COLD_CFG.items() if 'cold_out' in c}
def predecessor_hx(hx):
    cin = COLD_CFG.get(hx, {}).get('cold_in')
    pred_tag = CHAIN_PREDECESSOR.get(COLD_CFG.get(hx, {}).get('cold_out'))
    # upstream HX is the one whose cold_out == this HX's cold_in
    return coldout_to_hx.get(cin)

# ---- hot-stream label from cpht_features title ----
def hot_stream_name(hx):
    title = FULL_CFG.get(hx, {}).get('title', '')
    # "E108AB - Crude vs Residue" -> "Residue"
    return title.split(' vs ')[-1].split('(')[0].strip() if ' vs ' in title else '—'

hx_list = CPHT_1_HX + CPHT_2_HX
parallel = {a: b for a, b in PARALLEL_SHELL_GROUPS}
parallel.update({b: a for a, b in PARALLEL_SHELL_GROUPS})

nodes = {}
for hx in hx_list:
    cold = COLD_CFG.get(hx, {})
    p = parse_hx(FULL_CFG[hx]) if hx in FULL_CFG else {}
    ci, co = cold.get('cold_in'), cold.get('cold_out')
    hi, ho, hf = p.get('hot_in'), p.get('hot_out'), p.get('hot_flow')
    nodes[hx] = {
        'group': 'CPHT-1' if hx in CPHT_1_HX else 'CPHT-2',
        'cold_in_tag': ci,  'cold_in_val': val(ci),
        'cold_out_tag': co, 'cold_out_val': val(co),
        'cold_flow_tag': cold.get('cold_flow'), 'cold_flow_val': val(cold.get('cold_flow')),
        'hot_stream': hot_stream_name(hx),
        'hot_in_tag': hi, 'hot_in_val': val(hi),
        'hot_out_tag': ho, 'hot_out_val': val(ho),
        'hot_flow_tag': hf, 'hot_flow_val': val(hf),
        'predecessor': predecessor_hx(hx),
        'parallel_with': parallel.get(hx),
        'flow_note': cold.get('flow_source'),
    }

# ---- furnace Key Constraints (project brief table + Honeywell F101 screens) ----
# band = [alarm_lo, normal_lo, normal_hi, alarm_hi] (None where n/a)
# group = which constraint family (for the optimization-setup table)
# limit = the operating LIMIT the optimizer must respect (min for higher_better, else max)
furnace = [
    # -- Coil / CIT (what fouling directly hurts) --
    {'key': 'CIT',   'tag': '1TI116.pv', 'name': 'Coil Inlet Temp (จาก E113A)',  'unit': '°C',      'group': 'Coil / CIT',        'target': 258.05, 'limit': 250,  'band': [242, 250, 999, 999], 'higher_better': True},
    {'key': 'COT',   'tag': '1TI150.pv', 'name': 'Coil Outlet Temp',             'unit': '°C',      'group': 'Coil / CIT',        'target': 340.1,  'limit': 345,  'band': [335, 338, 342, 345]},
    {'key': 'COT_SP','tag': '1TC007.pv', 'name': 'COT Setpoint (control)',       'unit': '°C',      'group': 'Coil / CIT',        'target': 340.1,  'limit': 345,  'band': None},
    {'key': 'INLET_P','tag':'1PI003.pv', 'name': 'Crude Pressure เข้าเตา',       'unit': 'kg/cm²g', 'group': 'Coil / CIT',        'target': 18.17,  'limit': 25,   'band': None},
    # -- Firing / Fuel --
    {'key': 'FG_FLOW','tag':'1FI028.pv', 'name': 'Fuel Gas flow (firing)',       'unit': 't/h',     'group': 'Firing / Fuel',     'target': 6.66,   'limit': 9.0,  'band': [0, 0, 8, 9.5]},
    {'key': 'FG_PRESS','tag':'1PC010.pv','name': 'Fuel Gas pressure',            'unit': 'kg/cm²g', 'group': 'Firing / Fuel',     'target': 1.82,   'limit': 2.5,  'band': None},
    # -- Combustion / Draft --
    {'key': 'O2',    'tag': '1AI001.pv', 'name': 'O₂ ใน flue gas',               'unit': '%',       'group': 'Combustion / Draft','target': 2.52,   'limit': 4.5,  'band': [1.5, 2.0, 3.5, 4.5]},
    {'key': 'DRAFT', 'tag': '1PC034.pv', 'name': 'Furnace draft',                'unit': 'mmH₂O',   'group': 'Combustion / Draft','target': -3.02,  'limit': 0,    'band': [-6, -4, -1, 0.5]},
    {'key': 'DRAFT_K151','tag':'1PC035.pv','name':'Draft fan K151 (%open)',      'unit': '%',       'group': 'Combustion / Draft','target': 28.1,   'limit': 90,   'band': None},
    # -- Body / Stack (mechanical / heat-loss) --
    {'key': 'BODY1', 'tag': '1TI212.pv', 'name': 'Furnace Body 1',               'unit': '°C',      'group': 'Body / Stack',      'target': 183.71, 'limit': 250,  'band': None},
    {'key': 'BODY2', 'tag': '1TI213.pv', 'name': 'Furnace Body 2',               'unit': '°C',      'group': 'Body / Stack',      'target': 182.9,  'limit': 250,  'band': None},
    {'key': 'STACK', 'tag': '1TI182.pv', 'name': 'Stack (flue) temp',            'unit': '°C',      'group': 'Body / Stack',      'target': 324.28, 'limit': 380,  'band': [0, 0, 350, 380]},
    # -- Crude throughput --
    {'key': 'CHARGE','tag': '1fi005.pv', 'name': 'Crude charge (total)',         'unit': 'm³/h',    'group': 'Crude',             'target': 525.0,  'limit': 400,  'band': None, 'higher_better': True},
]
# Operator advisory when a constraint leaves its normal band (ข้อ 3). advice_hi fires
# when the value is high (or, for higher_better tags, when it is LOW — the harmful side),
# advice_lo the opposite. These are ASSUMED engineering guidelines pending confirmed
# limits from the plant furnace engineer.
ADVICE = {
    'CIT':   {'lo': 'CIT ต่ำกว่าเป้า → preheat train สกปรก ทำให้เตาต้องเผา FG เพิ่ม: ล้าง HX ตามลำดับ priority (E113A/E112C เป็น swap-capable เริ่มก่อน) เพื่อคืน CIT และลดภาระเตา'},
    'COT':   {'hi': 'COT สูงเกินเกณฑ์ → ลด firing/FG หรือตรวจ coil coking; เสี่ยง tube overheat/creep',
              'lo': 'COT ต่ำกว่าเป้า → เพิ่ม firing หรือตรวจ flow/feed ให้ได้อุณหภูมิ reaction ปลายทาง'},
    'FG_FLOW':{'hi':'FG flow สูง (เตาทำงานหนัก) → หาสาเหตุ: CIT ต่ำ / O₂ เกิน / ความร้อนสูญเสียที่ปล่อง; แก้ที่ต้นเหตุก่อนเพิ่มเชื้อเพลิง'},
    'O2':    {'hi': 'O₂ สูง = อากาศส่วนเกินมาก เสียความร้อนไปปล่อง → trim air (ลด damper/ID fan) ให้ O₂ ~2–3%',
              'lo': 'O₂ ต่ำ → เสี่ยงเผาไหม้ไม่สมบูรณ์/CO และ afterburn: เพิ่มอากาศทันที เฝ้าระวังเปลวไฟ'},
    'DRAFT': {'hi': 'Draft เป็นบวก/สูงเกิน → เสี่ยง flue gas รั่วออก/ความร้อนย้อน: เปิด stack damper หรือปรับ ID fan ให้ draft ~ −2 ถึง −4 mmH₂O',
              'lo': 'Draft ติดลบมากเกิน → ดูดอากาศรั่วเข้ามาก (tramp air) เสีย efficiency: ลด ID fan/ปิด damper'},
    'BODY1': {'hi': 'อุณหภูมิ body สูง → refractory/insulation เสื่อม หรือ flame impingement: ตรวจสอบผนังเตา/ตำแหน่งเปลวไฟ'},
    'BODY2': {'hi': 'อุณหภูมิ body สูง → refractory/insulation เสื่อม หรือ flame impingement: ตรวจสอบผนังเตา/ตำแหน่งเปลวไฟ'},
    'STACK': {'hi': 'Stack (flue) temp สูง → convection section สกปรก/soot สะสม ความร้อนสูญเสียมาก: soot-blow และตรวจ excess air'},
    'INLET_P':{'hi':'Crude pressure เข้าเตาสูง → ตรวจ fouling/restriction ใน coil หรือ downstream'},
    'FG_PRESS':{'hi':'FG pressure สูง → ตรวจ control valve/หัวเผา; เสี่ยง flame length/ NOx'},
    'CHARGE':{'lo': 'Charge ต่ำกว่าเป้า → กำลังการผลิตลด (ไม่ใช่ปัญหา fouling โดยตรง แต่กระทบ economics)'},
}

for f in furnace:
    f['value'] = val(f['tag'])
    if f['value'] is None:
        f['value'] = f['target']   # fallback to brief-table value if tag absent
        f['is_fallback'] = True
    adv = ADVICE.get(f['key'], {})
    # for higher_better tags the harmful direction is LOW, so map its advice to advice_lo
    f['advice_hi'] = adv.get('hi')
    f['advice_lo'] = adv.get('lo')
    f['limit_assumed'] = True   # limits pending confirmation from furnace engineer

# 4 passes × (convection-out / radiation tube-skin / coil-out temps + pass flow), from F101 TEMP PROFILE screen
PASS_TAGS = [
    {'pass': 1, 'conv': '1TI142.pv', 'skin': '1TI151.pv', 'coil': '1TI148.pv', 'flow': '1FC020.pv',
     'conv_def': 291.05, 'skin_def': 389.40, 'coil_def': 356.36, 'flow_def': 130.6},
    {'pass': 2, 'conv': '1TI141.pv', 'skin': '1TI152.pv', 'coil': '1TI143.pv', 'flow': '1FC021.pv',
     'conv_def': 286.29, 'skin_def': 370.14, 'coil_def': 335.61, 'flow_def': 131.7},
    {'pass': 3, 'conv': '1TI140.pv', 'skin': '1TI146.pv', 'coil': '1TI144.pv', 'flow': '1FC022.pv',
     'conv_def': 286.84, 'skin_def': 356.49, 'coil_def': 335.00, 'flow_def': 131.7},
    {'pass': 4, 'conv': '1TI139.pv', 'skin': '1TI145.pv', 'coil': '1TI149.pv', 'flow': '1FC023.pv',
     'conv_def': 290.30, 'skin_def': 378.75, 'coil_def': 345.41, 'flow_def': 131.8},
]
SKIN_ALARM = 400.0   # tube-skin (metal) temp alarm — coking/creep risk above this
passes = []
for p in PASS_TAGS:
    row = {'pass': p['pass']}
    for k in ('conv', 'skin', 'coil', 'flow'):
        row[f'{k}_tag'] = p[k]
        row[f'{k}_val'] = val(p[k]) if val(p[k]) is not None else p[f'{k}_def']
    # legacy fields kept for the existing Furnace passes table (in=conv, out=skin)
    row['in_tag'], row['out_tag'] = p['conv'], p['skin']
    row['in_val'], row['out_val'] = row['conv_val'], row['skin_val']
    row['dT'] = round(row['coil_val'] - row['conv_val'], 1)     # crude temp rise through the pass
    row['skin_alarm'] = SKIN_ALARM
    row['advice'] = ('Tube-skin ร้อนใกล้/เกินเกณฑ์ → เสี่ยง coking/creep: ปรับสมดุล flow ระหว่าง pass '
                     '(เพิ่ม flow pass ที่ร้อน), ลด firing เฉพาะจุด, ตรวจ coking ภายใน tube')
    passes.append(row)

topo = {
    'last_timestamp': str(last_ts),
    'order': hx_list,
    'cpht1': CPHT_1_HX,
    'cpht2': CPHT_2_HX,
    'parallel_shells': PARALLEL_SHELL_GROUPS,
    'nodes': nodes,
    'furnace': furnace,
    'passes': passes,
    'cit_tag': '1TI116.pv',
    'limits_assumed': True,
    'advice_note': 'คำแนะนำและค่า limit เป็น "ค่าสมมติเชิงวิศวกรรม" — รอยืนยันค่าจริงจากวิศวกรเตา',
}
OUT.write_text(json.dumps(topo, indent=2, ensure_ascii=False), encoding='utf-8')
print(f'Wrote {OUT}')
print(f'  {len(nodes)} HX nodes, {len(furnace)} furnace params, {len(passes)} passes')
print(f'  latest process timestamp: {last_ts}')
missing = [hx for hx, n in nodes.items() if n['cold_out_val'] is None]
print(f'  HX with no latest cold_out value: {missing or "none"}')
