"""
Build a SAFE public demo of the CPHT dashboard — no real plant data leaves.

Reads dashboard/index.html + dashboard/data/*.json, then writes ./demo/ with:
  * every real DCS instrument tag (1TI116, 1FI028, 439FI003.pv ...) replaced by a
    generic label that keeps only the instrument TYPE (TI-01, FI-03, PC-02 ...),
  * raw process readings on the P&ID/furnace (temps/flows/O2/draft/assay) replaced
    by values run through a HIDDEN affine transform, so absolute operating values
    are not disclosed while the diagram still looks sensible (relationships preserved),
  * a window.__DEMO__ flag injected so the frontend shows a "DEMO / anonymized"
    banner and disables upload/re-analyze.

Derived scores (priority, RUL days, reliability) are kept — they contain no raw
tags or raw operating values once tags/readings above are anonymized.

Run:  python deploy/anonymize_data.py
Then deploy the ./demo folder to GitHub Pages or Vercel (static).
"""
import json, re, shutil, random
from pathlib import Path

random.seed(20260706)
REPO = Path(__file__).resolve().parent.parent
DASH = REPO / 'dashboard'
SRC_DATA = DASH / 'data'
DEMO = REPO / 'demo'
DEMO_DATA = DEMO / 'data'

# instrument-tag pattern: optional digits, 2-3 letters, digits, optional letter, optional .pv
# (does NOT match HX equipment codes like E101AB / E113A — those start with 1 letter)
TAG_RE = re.compile(r'\b\d{0,3}[A-Za-z]{2,3}\d{2,4}[A-Za-z]?(?:\.pv)?\b')

# hidden transforms (unknown to a viewer) — affine on temps keeps every inequality intact
A_T, B_T = 0.88, round(random.uniform(-8, 8), 2)          # temperatures
F_FLOW  = round(random.uniform(0.8, 1.2), 3)              # flows
F_PCT   = round(random.uniform(0.85, 1.15), 3)            # % (O2 etc.)
F_MISC  = round(random.uniform(0.85, 1.15), 3)            # pressure/draft/misc

_tag_map = {}
def _is_tag(s):
    m = TAG_RE.fullmatch(s.strip())
    return bool(m)

def anon_tag(tag):
    if tag in _tag_map:
        return _tag_map[tag]
    m = re.search(r'[A-Za-z]{2,3}', tag)
    typ = (m.group(0).upper() if m else 'SN')
    n = sum(1 for v in _tag_map.values() if v.startswith(typ + '-')) + 1
    lab = f'{typ}-{n:02d}'
    _tag_map[tag] = lab
    return lab

def scrub_string(s):
    """Replace any instrument tags embedded in a string with generic labels."""
    return TAG_RE.sub(lambda m: anon_tag(m.group(0)), s)

def scrub_tags(obj):
    if isinstance(obj, dict):
        return {k: scrub_tags(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [scrub_tags(v) for v in obj]
    if isinstance(obj, str):
        return scrub_string(obj)
    return obj

def t_temp(v):  return None if v is None else round(A_T * v + B_T, 2)
def t_flow(v):  return None if v is None else round(F_FLOW * v, 2)
def t_pct(v):   return None if v is None else round(F_PCT * v, 2)
def t_misc(v):  return None if v is None else round(F_MISC * v, 2)


def anon_topology(topo):
    """Perturb the raw readings shown on the P&ID + furnace (the sensitive surface)."""
    topo = scrub_tags(topo)
    for n in topo.get('nodes', {}).values():
        for k in ('cold_in_val', 'cold_out_val', 'hot_in_val', 'hot_out_val'):
            if k in n: n[k] = t_temp(n[k])
        if 'cold_flow_val' in n: n['cold_flow_val'] = t_flow(n['cold_flow_val'])
    for f in topo.get('furnace', []):
        u = f.get('unit', '')
        v = f.get('value')
        if u == '°C':   f['value'] = t_temp(v)
        elif u == '%':  f['value'] = t_pct(v)
        elif 't/h' in u: f['value'] = t_flow(v)
        else:            f['value'] = t_misc(v)
        if 'target' in f: f.pop('target', None)   # hide the real setpoint too
    for p in topo.get('passes', []):
        for k in ('in_val', 'out_val', 'in_def', 'out_def'):
            if k in p: p[k] = t_temp(p[k])
        if 'in_val' in p and 'out_val' in p and p['in_val'] is not None:
            p['dT'] = round(p['out_val'] - p['in_val'], 1)
    topo['last_timestamp'] = '2020-01-01 00:00:00'   # generic date
    topo['_demo'] = True
    return topo


def anon_hxts(hxts):
    """Perturb the per-HX time-series raw values (temps/Q) so the demo shows the
    same SHAPES (sawtooth, prediction-vs-actual gap) without disclosing real numbers."""
    for hx, d in hxts.items():
        s = d.get('series', {})
        s['cold_in']  = [t_temp(v) for v in s.get('cold_in', [])]
        s['cold_out'] = [t_temp(v) for v in s.get('cold_out', [])]
        s['Q']           = [t_flow(v) for v in s.get('Q', [])]
        s['predicted_Q'] = [t_flow(v) for v in s.get('predicted_Q', [])]
        s['deviation']   = [t_flow(v) for v in s.get('deviation', [])]
        # U_relative (ratio) + days_on_duty + run stats are not sensitive -> kept
    return hxts


def main():
    if DEMO.exists():
        shutil.rmtree(DEMO)
    DEMO_DATA.mkdir(parents=True)

    # 1) static shell: self-contained index.html + logo, with the DEMO flag injected
    html = (DASH / 'index.html').read_text(encoding='utf-8')
    html = html.replace('<body>', '<body>\n<script>window.__DEMO__=true;</script>', 1)
    (DEMO / 'index.html').write_text(html, encoding='utf-8')
    if (DASH / 'bangchak-logo.png').exists():
        shutil.copy2(DASH / 'bangchak-logo.png', DEMO / 'bangchak-logo.png')

    # 2) anonymized data
    leaked = []
    for jf in sorted(SRC_DATA.glob('*.json')):
        obj = json.loads(jf.read_text(encoding='utf-8'))
        if jf.name == 'pfd_topology.json':
            obj = anon_topology(obj)
        elif jf.name == 'hx_timeseries.json':
            obj = anon_hxts(scrub_tags(obj))
        else:
            obj = scrub_tags(obj)
        out = json.dumps(obj, ensure_ascii=False, indent=1)
        # safety: no original tag pattern should survive
        for real in _tag_map:
            if real in out:
                leaked.append(f'{jf.name}:{real}')
        (DEMO_DATA / jf.name).write_text(out, encoding='utf-8')

    print(f'Wrote demo -> {DEMO}')
    print(f'  anonymized {len(_tag_map)} unique instrument tags -> generic TYPE-NN')
    print(f'  hidden transforms: temp={A_T}*t+{B_T}, flow x{F_FLOW}, pct x{F_PCT}')
    print(f'  data files: {len(list(DEMO_DATA.glob("*.json")))}')
    print('  LEAK CHECK:', 'FAIL ' + str(leaked[:5]) if leaked else 'OK (no real tags survive)')


if __name__ == '__main__':
    main()
