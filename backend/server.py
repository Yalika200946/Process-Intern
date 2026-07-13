"""
Zero-dependency backend for the CPHT dashboard (Python stdlib only — no
FastAPI/Flask needed, so it runs on any plant machine with plain Python).

Serves the static dashboard AND provides the "upload new data + re-analyze"
endpoint the operators asked for:

  GET  /                     -> dashboard/index.html
  GET  /<path>               -> static files under dashboard/
  POST /api/run              -> accept an uploaded cleaned-process file (raw
                                body; filename in X-Filename, optimization
                                params JSON in X-Params), validate its tag
                                columns against cpht_config, save it, and
                                regenerate dashboard/data/pfd_topology.json
                                (P&ID latest values + furnace constraints) from
                                the new data. Returns a JSON status report.

The heavier ranking/forecast recompute (notebooks 01->02->03->08->06->13) is the
`pipeline/` package (A6) — this endpoint refreshes the artifacts that a single
cleaned-process file can regenerate on its own and reports exactly what it did.

Run:  python backend/server.py         (defaults to http://localhost:8899)
"""
import os
import json, sys, subprocess, io
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import pandas as pd

ROOT      = Path(__file__).resolve().parent.parent
DASH      = ROOT / 'dashboard'
NB        = ROOT / 'notebooks'
DATA      = Path(os.environ.get('CPHT_DATA_DIR', r'C:\Desktop\Bangchak Internship 2026\Data'))
UPLOADS   = DATA / 'uploads'
UPLOADS.mkdir(parents=True, exist_ok=True)
TOPO_OUT  = DASH / 'data' / 'pfd_topology.json'
PARAMS_OUT= DASH / 'data' / 'opt_params.json'
PORT      = int(os.environ.get('PORT') or (sys.argv[1] if len(sys.argv) > 1 else 8899))

sys.path.append(str(NB))
from cpht_config import HX_CONFIG, CIT_TAG, TOTAL_CHARGE_TAG

# tags a cleaned-process file MUST contain for the topology/furnace to rebuild
REQUIRED_TAGS = {CIT_TAG, TOTAL_CHARGE_TAG}
for cfg in HX_CONFIG.values():
    for k in ('cold_in', 'cold_out'):
        if cfg.get(k):
            REQUIRED_TAGS.add(cfg[k])

CTYPE = {'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json',
         '.png':'image/png','.svg':'image/svg+xml','.ico':'image/x-icon'}


def validate_and_load(raw, filename):
    """Return (df, missing_tags). Raises ValueError on unreadable/invalid file."""
    buf = io.BytesIO(raw)
    if filename.lower().endswith(('.xlsx', '.xls')):
        df = pd.read_excel(buf)
    else:
        df = pd.read_csv(buf)
    if 'Timestamp' not in df.columns:
        raise ValueError("ไฟล์ต้องมีคอลัมน์ 'Timestamp' (schema เดียวกับ Process_information_cleaned.csv)")
    df = df.set_index('Timestamp')
    missing = sorted(t for t in REQUIRED_TAGS if t not in df.columns)
    return df, missing


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quieter console
        pass

    def _send(self, code, body, ctype='application/json'):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split('?')[0]
        rel = 'index.html' if path in ('/', '') else path.lstrip('/')
        fp = (DASH / rel).resolve()
        if not str(fp).startswith(str(DASH.resolve())) or not fp.is_file():
            return self._send(404, {'error': 'not found'})
        self._send(200, fp.read_bytes(), CTYPE.get(fp.suffix, 'application/octet-stream'))

    def do_POST(self):
        endpoint = self.path.split('?')[0]
        if endpoint == '/api/run-full':
            return self._run_full()
        if endpoint == '/api/recompute-plan':
            return self._recompute_plan()
        if endpoint != '/api/run':
            return self._send(404, {'error': 'unknown endpoint'})
        try:
            n = int(self.headers.get('Content-Length', 0))
            raw = self.rfile.read(n)
            filename = self.headers.get('X-Filename', 'upload.csv')
            try:
                params = json.loads(self.headers.get('X-Params', '{}'))
            except Exception:
                params = {}

            df, missing = validate_and_load(raw, filename)
            if missing:
                return self._send(422, {'error': f'ไฟล์ขาด tag ที่จำเป็น {len(missing)} คอลัมน์',
                                        'missing_tags': missing[:20]})

            # persist the validated file + params
            saved = UPLOADS / filename
            saved.write_bytes(raw)
            df.to_csv(UPLOADS / 'last_cleaned.csv')  # normalized CSV the builder reads
            PARAMS_OUT.write_text(json.dumps(params, ensure_ascii=False, indent=2), encoding='utf-8')

            # regenerate topology + furnace from the uploaded data
            r = subprocess.run([sys.executable, str(NB / 'build_dashboard_topology.py'),
                                str(UPLOADS / 'last_cleaned.csv'), str(TOPO_OUT)],
                               capture_output=True, text=True, timeout=120)
            if r.returncode != 0:
                return self._send(500, {'error': 'topology rebuild failed', 'detail': r.stderr[-800:]})

            self._send(200, {
                'ok': True,
                'message': f'อัปเดตแล้วจาก {filename} ({len(df)} แถว, ล่าสุด {df.index.max()})',
                'refreshed': ['pfd_topology.json (P&ID + furnace)', 'opt_params.json'],
                'note': 'การจัดอันดับ/พยากรณ์เต็มรูปแบบต้องรัน pipeline (notebooks 01->02->08->06->13)',
            })
        except ValueError as e:
            self._send(422, {'error': str(e)})
        except Exception as e:
            self._send(500, {'error': f'{type(e).__name__}: {e}'})

    def _recompute_plan(self):
        """Apply per-HX cleaning-cost overrides from the dashboard's "คำนวณใหม่" button
        and actually re-run notebook 16's optimizer (not a client-side approximation) so
        the returned schedule/priority genuinely reflects the new costs. Blocking —
        takes ~10-20s; the dashboard shows a loading state while this runs."""
        try:
            n = int(self.headers.get('Content-Length', 0))
            raw = self.rfile.read(n) if n else b'{}'
            try:
                body = json.loads(raw.decode('utf-8') or '{}')
            except Exception:
                body = {}
            overrides = body.get('overrides') or {}
            if not isinstance(overrides, dict):
                # value per HX is either a flat THB number or a {"methods":[...]} formula --
                # see export_economics.resolve_cost_override, this endpoint is a pure
                # passthrough (writes whatever shape it's given) so no schema change needed here.
                return self._send(422, {'error': 'overrides ต้องเป็น object {HX: cost | {"methods":[...]}}'})

            overrides_path = DASH / 'data' / 'cost_overrides.json'
            overrides_path.write_text(json.dumps(overrides, ensure_ascii=False, indent=1), encoding='utf-8')

            env = {**os.environ, 'PYTHONUTF8': '1'}
            r = subprocess.run(
                [sys.executable, '-m', 'nbconvert', '--to', 'notebook', '--execute', '--inplace',
                 '--ExecutePreprocessor.timeout=300',
                 str(NB / '16_cleaning_plan_optimization.ipynb')],
                capture_output=True, text=True, env=env, timeout=320)
            if r.returncode != 0:
                return self._send(500, {'error': 'notebook 16 recompute failed', 'detail': (r.stderr or '')[-1500:]})

            plan = json.loads((DASH / 'data' / 'cleaning_plan.json').read_text(encoding='utf-8'))
            self._send(200, {
                'ok': True,
                'message': f'คำนวณใหม่แล้วด้วยค่าล้าง {len(overrides)} HX ที่แก้',
                'plan': plan,
            })
        except subprocess.TimeoutExpired:
            self._send(504, {'error': 'คำนวณใหม่ใช้เวลานานเกินไป (>320s)'})
        except Exception as e:
            self._send(500, {'error': f'{type(e).__name__}: {e}'})

    def _run_full(self):
        """Kick off the full notebook pipeline (run_all.py) in the background.
        Optionally stages an uploaded RAW process Excel first. Returns
        immediately — the full chain takes several minutes; the dashboard
        refreshes when the operator reloads after it finishes."""
        try:
            n = int(self.headers.get('Content-Length', 0))
            raw = self.rfile.read(n) if n else b''
            filename = self.headers.get('X-Filename', '')
            cmd = [sys.executable, str(ROOT / 'pipeline' / 'run_all.py'), '--timeout', '1200']
            staged = None
            if raw and filename:
                staged = UPLOADS / filename
                staged.write_bytes(raw)
                cmd += ['--input', str(staged)]
            env = {**__import__('os').environ, 'PYTHONUTF8': '1'}
            log = (UPLOADS / 'pipeline_last.log').open('wb')
            subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, env=env)
            self._send(200, {
                'ok': True, 'started': True,
                'message': ('เริ่มรัน pipeline เต็มรูปแบบแล้ว (รันโน้ตบุ๊ก 13 ไฟล์ อาจใช้เวลาหลายนาที)'
                            + (f' · ใช้ไฟล์ {filename}' if staged else ' · ใช้ข้อมูลปัจจุบัน')),
                'note': 'เมื่อเสร็จแล้วให้กดรีเฟรชหน้าเพื่อโหลดผลใหม่ · log: Data/uploads/pipeline_last.log',
            })
        except Exception as e:
            self._send(500, {'error': f'{type(e).__name__}: {e}'})


if __name__ == '__main__':
    # bind 127.0.0.1 by default (local only, safe). Docker/intranet sets CPHT_BIND=0.0.0.0
    HOST = os.environ.get('CPHT_BIND', '127.0.0.1')
    print(f'CPHT backend on http://{HOST}:{PORT}/  (serving {DASH}, data={DATA})')
    print(f'  required tags for upload: {len(REQUIRED_TAGS)} columns')
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
