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
import email.utils
import json, logging, sys, subprocess, io, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import pandas as pd

ROOT      = Path(__file__).resolve().parent.parent
DASH      = ROOT / 'dashboard'
NB        = ROOT / 'notebooks'
SRC       = ROOT / 'src'
DATA      = Path(os.environ.get('CPHT_DATA_DIR', r'C:\Desktop\Bangchak Internship 2026\Data'))
UPLOADS   = DATA / 'uploads'
UPLOADS.mkdir(parents=True, exist_ok=True)
TOPO_OUT  = DASH / 'data' / 'pfd_topology.json'
PARAMS_OUT= DASH / 'data' / 'opt_params.json'
EXECUTED_NB = ROOT / 'reports' / 'executed_notebooks'
EXECUTED_NB.mkdir(parents=True, exist_ok=True)
# Keep module import side-effect free: pytest, WSGI helpers, and other callers place
# their own flags in sys.argv.  The optional positional CLI port is parsed only in main.
PORT      = int(os.environ.get('PORT', 8899))

# Upload size cap -- previously /api/run and /api/run-full read `Content-Length` bytes
# unconditionally, so an arbitrarily large (or falsified) Content-Length could exhaust
# memory/disk before any tag validation ran. Override with CPHT_MAX_UPLOAD_MB.
MAX_UPLOAD_BYTES = int(os.environ.get('CPHT_MAX_UPLOAD_MB', 200)) * 1024 * 1024

# Guards /api/run-full against a second full-pipeline run starting while one is still
# in progress (run_all.py takes several minutes and mutates shared Data/ CSVs + dashboard
# JSON in place -- two overlapping runs would race on the same files). Tracks the most
# recently started pipeline subprocess; `_full_run_lock` only protects the brief
# check-then-launch window, not the run itself.
_full_run_lock = threading.Lock()
_full_run_proc = None


def _safe_filename(name):
    """Return just the basename of an untrusted X-Filename header value, rejecting
    anything that would let it escape UPLOADS/ (e.g. '../../evil.py', an absolute path,
    or a bare '..'). Previously `UPLOADS / filename` used the header value directly."""
    name = (name or '').strip()
    base = Path(name).name
    if not base or base in ('.', '..'):
        raise ValueError("X-Filename ไม่ถูกต้อง")
    return base


def _subprocess_env():
    inherited = os.environ.get('PYTHONPATH', '')
    pythonpath = os.pathsep.join(
        p for p in (str(ROOT), str(NB), str(ROOT / 'pipeline'), inherited) if p
    )
    return {**os.environ, 'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8',
            'PYTHONPATH': pythonpath, 'CPHT_DATA_DIR': str(DATA)}

# Structured log file -- BaseHTTPRequestHandler.log_message() is overridden to a no-op below
# ("quieter console"), so previously nothing about a request/failure was persisted anywhere;
# this is the only record of what the backend did/failed on, across every endpoint, without
# watching the terminal live.
logging.basicConfig(
    level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler(DATA / 'backend_server.log', encoding='utf-8')])
log = logging.getLogger('backend.server')

sys.path.append(str(ROOT))
from src.domain.config import HX_CONFIG, CIT_TAG, TOTAL_CHARGE_TAG

sys.path.append(str(ROOT / 'pipeline'))
import cleaning_scheduler_network as SCHED
import export_economics as ECON

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


def validate_raw_excel(raw, filename):
    """Return missing_tags for a RAW process Excel headed for the full pipeline
    (`/api/run-full` -> `run_all.py --input`). Raises ValueError on a file that
    isn't even readable/structured as `notebooks/01_data_cleaning.ipynb` expects
    (sheet 'Sheet1', tag names in row 4 / 1-indexed, data from row 8).

    Unlike `validate_and_load` above (which validates an already-cleaned CSV
    with tags as column headers), a raw historian export has tags embedded in
    a header ROW, not as DataFrame columns -- so this is a separate check, not
    a call to `validate_and_load`. Exists to close the gap where this upload
    path previously staged the file with zero validation and let a malformed
    file fail deep inside notebook 01 with a cryptic pandas error instead of a
    clear message at the boundary (docs/03 section 2.2, FR-DQ-* gap)."""
    if not filename.lower().endswith(('.xlsx', '.xls')):
        raise ValueError("ไฟล์ pipeline เต็มรูปแบบต้องเป็น .xlsx/.xls (raw historian export) ไม่ใช่ไฟล์ประเภทอื่น")
    buf = io.BytesIO(raw)
    try:
        raw_df = pd.read_excel(buf, sheet_name='Sheet1', header=None, nrows=8)
    except Exception as e:
        raise ValueError(f"อ่านไฟล์ Excel ไม่ได้ หรือไม่มี sheet ชื่อ 'Sheet1': {e}")
    if raw_df.shape[0] < 8 or raw_df.shape[1] < 4:
        raise ValueError("โครงสร้างไฟล์ไม่ตรงกับที่ pipeline คาดไว้ "
                          "(ต้องมีอย่างน้อย 8 แถว และ 4 คอลัมน์ก่อนถึงแถวข้อมูลจริง)")
    tags_row = raw_df.iloc[3, 3:]
    found_tags = {t for t in tags_row if isinstance(t, str)}
    return sorted(t for t in REQUIRED_TAGS if t not in found_tags)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quieter console
        pass

    def _send(self, code, body, ctype='application/json', extra_headers=None):
        # Single choke point every response goes through -- logging HERE (rather than at each
        # individual except-block across every endpoint below) means every non-2xx response
        # gets a persisted record automatically, including any future endpoint that forgets to
        # log its own errors.
        if code >= 400:
            log.error(f'{self.command} {self.path} -> {code}: '
                      f'{body if isinstance(body, dict) else "<binary/other>"}')
        else:
            log.info(f'{self.command} {self.path} -> {code}')
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split('?')[0]
        rel = 'index.html' if path in ('/', '') else path.lstrip('/')
        fp = (DASH / rel).resolve()
        if not str(fp).startswith(str(DASH.resolve())) or not fp.is_file():
            return self._send(404, {'error': 'not found'})
        # Last-Modified lets the dashboard detect when /api/run's "quick update" (topology
        # only) has left pfd_topology.json newer than hx_ranking.json/economics.json --
        # i.e. the displayed ranking/economics are stale relative to the current topology --
        # without requiring every pipeline export script to embed its own generated_at field.
        mtime = email.utils.formatdate(fp.stat().st_mtime, usegmt=True)
        self._send(200, fp.read_bytes(), CTYPE.get(fp.suffix, 'application/octet-stream'),
                   extra_headers={'Last-Modified': mtime})

    def do_POST(self):
        endpoint = self.path.split('?')[0]
        if endpoint == '/api/run-full':
            return self._run_full()
        if endpoint == '/api/recompute-plan':
            return self._recompute_plan()
        if endpoint == '/api/recompute-tam-comparison':
            return self._recompute_tam_comparison()
        if endpoint != '/api/run':
            return self._send(404, {'error': 'unknown endpoint'})
        try:
            n = int(self.headers.get('Content-Length', 0))
            if n > MAX_UPLOAD_BYTES:
                return self._send(413, {'error': f'ไฟล์ใหญ่เกินไป (>{MAX_UPLOAD_BYTES // (1024*1024)}MB)'})
            raw = self.rfile.read(n)
            filename = _safe_filename(self.headers.get('X-Filename', 'upload.csv'))
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
            r = subprocess.run([sys.executable, str(SRC / 'reporting' / 'dashboard_topology.py'),
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
        """Apply per-HX cleaning-cost overrides, an optional CIT-floor constraint, AND an
        optional furnace FG_FLOW limit override from the dashboard's "คำนวณใหม่" button, then
        actually re-run production/13_cleaning_plan_optimization.ipynb's optimizer (not a client-side approximation) so the
        returned schedule/priority genuinely reflects the new inputs. Blocking — takes
        ~10-30s (longer with a tight CIT floor/limit, since that adds SLSQP constraints);
        the dashboard shows a loading state while this runs."""
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

            cit_floor_path = DASH / 'data' / 'cit_floor_override.json'
            cit_floor_C = body.get('cit_floor_C')
            if cit_floor_C is not None:
                try:
                    cit_floor_C = float(cit_floor_C)
                except (TypeError, ValueError):
                    return self._send(422, {'error': 'cit_floor_C ต้องเป็นตัวเลข'})
                cit_floor_path.write_text(json.dumps({'max_deficit_C': cit_floor_C}, indent=1), encoding='utf-8')
            elif cit_floor_path.exists():
                cit_floor_path.unlink()   # no override in this request -> fall back to production/13_cleaning_plan_optimization.ipynb's default

            furnace_limit_path = DASH / 'data' / 'furnace_limit_overrides.json'
            furnace_limits = body.get('furnace_limit_overrides')
            if furnace_limits:
                if not isinstance(furnace_limits, dict):
                    return self._send(422, {'error': 'furnace_limit_overrides ต้องเป็น object {key: limit}'})
                furnace_limit_path.write_text(json.dumps(furnace_limits, ensure_ascii=False, indent=1), encoding='utf-8')
            elif furnace_limit_path.exists():
                furnace_limit_path.unlink()   # no override in this request -> fall back to pfd_topology.json's static limit

            env = _subprocess_env()
            r = subprocess.run(
                [sys.executable, '-m', 'nbconvert', '--to', 'notebook', '--execute',
                 f'--output-dir={EXECUTED_NB}',
                 '--ExecutePreprocessor.timeout=420',
                 str(NB / 'production' / '13_cleaning_plan_optimization.ipynb')],
                capture_output=True, text=True, env=env, timeout=440)
            if r.returncode != 0:
                return self._send(500, {'error': 'production/13_cleaning_plan_optimization.ipynb recompute failed', 'detail': (r.stderr or '')[-1500:]})

            plan = json.loads((DASH / 'data' / 'cleaning_plan.json').read_text(encoding='utf-8'))
            floor_msg = f' · CIT floor {cit_floor_C}°C' if cit_floor_C is not None else ''
            fg_msg = f' · FG_FLOW limit {furnace_limits["FG_FLOW"]}t/h' if furnace_limits and furnace_limits.get('FG_FLOW') is not None else ''
            self._send(200, {
                'ok': True,
                'message': f'คำนวณใหม่แล้วด้วยค่าล้าง {len(overrides)} HX ที่แก้{floor_msg}{fg_msg}',
                'plan': plan,
            })
        except subprocess.TimeoutExpired:
            self._send(504, {'error': 'คำนวณใหม่ใช้เวลานานเกินไป (>440s)'})
        except Exception as e:
            self._send(500, {'error': f'{type(e).__name__}: {e}'})

    def _recompute_tam_comparison(self):
        """Real TAM 3-year-vs-4-year scenario comparison (pipeline.cleaning_scheduler_network.
        compare_tam_cycles). Runs IN-PROCESS -- unlike _recompute_plan, this does NOT go through
        nbconvert/a fresh Jupyter kernel, avoiding that ~10-20s startup cost. That said, this is
        still SLOW in absolute terms (measured ~6 minutes for both scenarios combined): each
        scenario reruns the full 5-window SLSQP sweep over a multi-year horizon, and that cost
        dominates over the kernel-startup saving. Don't undersell this as "fast" in UI copy --
        the dashboard button explicitly warns it can take minutes. Applies
        the same overrides/cit_floor_C/furnace_limit_overrides shape _recompute_plan accepts (NOT
        persisted to disk -- this is a read-only "what if" comparison, doesn't affect
        cleaning_plan.json) so the comparison reflects whatever the dashboard currently has
        entered, without duplicating the override-resolution logic (reuses
        export_economics.resolve_cost_override)."""
        try:
            n = int(self.headers.get('Content-Length', 0))
            raw = self.rfile.read(n) if n else b'{}'
            try:
                body = json.loads(raw.decode('utf-8') or '{}')
            except Exception:
                body = {}

            def _load(name, default=None):
                p = DASH / 'data' / name
                return json.loads(p.read_text(encoding='utf-8')) if p.exists() else default

            econ = _load('economics.json', {})
            chist = _load('cleaning_history.json', {'hx': {}})
            logi = _load('cleaning_logistics.json', {'hx': []})
            sched_v1 = _load('cleaning_schedule.json')
            topo = _load('pfd_topology.json', {})

            overrides = body.get('overrides') or {}
            econ_live = dict(econ)
            econ_live['per_hx'] = [
                {**r, 'cleaning_cost': ECON.resolve_cost_override(overrides.get(r['HX']), r.get('cleaning_cost'))[0]}
                for r in econ.get('per_hx', [])
            ]

            cit_floor_C = body.get('cit_floor_C')
            if cit_floor_C is not None:
                cit_floor_C = float(cit_floor_C)
            furnace_limits = body.get('furnace_limit_overrides') or {}
            base_tam = body.get('base_tam') or str(SCHED.NEXT_TAM.date())
            years_options = tuple(body.get('years_options') or (3, 4))

            comparison = SCHED.compare_tam_cycles(
                econ_live, chist, logi, sched_v1, base_tam=base_tam, years_options=years_options,
                max_cit_deficit_C=cit_floor_C, topo=topo, limit_overrides=furnace_limits)
            (DASH / 'data' / 'tam_comparison.json').write_text(
                json.dumps(comparison, ensure_ascii=False, indent=1), encoding='utf-8')
            self._send(200, {'ok': True, 'comparison': comparison})
        except Exception as e:
            self._send(500, {'error': f'{type(e).__name__}: {e}'})

    def _run_full(self):
        """Kick off the full notebook pipeline (run_all.py) in the background.
        Optionally stages an uploaded RAW process Excel first. Returns
        immediately — the full chain takes several minutes; the dashboard
        refreshes when the operator reloads after it finishes."""
        global _full_run_proc
        try:
            with _full_run_lock:
                if _full_run_proc is not None and _full_run_proc.poll() is None:
                    return self._send(409, {'error': 'pipeline เต็มรูปแบบกำลังรันอยู่ กรุณารอให้เสร็จก่อนเริ่มใหม่'})

                n = int(self.headers.get('Content-Length', 0))
                if n > MAX_UPLOAD_BYTES:
                    return self._send(413, {'error': f'ไฟล์ใหญ่เกินไป (>{MAX_UPLOAD_BYTES // (1024*1024)}MB)'})
                raw = self.rfile.read(n) if n else b''
                filename = self.headers.get('X-Filename', '')
                cmd = [sys.executable, str(ROOT / 'pipeline' / 'run_all.py'), '--timeout', '1200']
                staged = None
                if raw and filename:
                    filename = _safe_filename(filename)
                    missing = validate_raw_excel(raw, filename)
                    if missing:
                        return self._send(422, {'error': f'ไฟล์ขาด tag ที่จำเป็น {len(missing)} คอลัมน์',
                                                'missing_tags': missing[:20]})
                    staged = UPLOADS / filename
                    staged.write_bytes(raw)
                    cmd += ['--input', str(staged)]
                env = _subprocess_env()
                log = (UPLOADS / 'pipeline_last.log').open('wb')
                _full_run_proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, env=env)
            self._send(200, {
                'ok': True, 'started': True,
                'message': ('เริ่มรัน pipeline เต็มรูปแบบแล้ว (รันโน้ตบุ๊ก 13 ไฟล์ อาจใช้เวลาหลายนาที)'
                            + (f' · ใช้ไฟล์ {filename}' if staged else ' · ใช้ข้อมูลปัจจุบัน')),
                'note': 'เมื่อเสร็จแล้วให้กดรีเฟรชหน้าเพื่อโหลดผลใหม่ · log: Data/uploads/pipeline_last.log',
            })
        except ValueError as e:
            self._send(422, {'error': str(e)})
        except Exception as e:
            self._send(500, {'error': f'{type(e).__name__}: {e}'})


if __name__ == '__main__':
    # bind 127.0.0.1 by default (local only, safe). Docker/intranet sets CPHT_BIND=0.0.0.0
    HOST = os.environ.get('CPHT_BIND', '127.0.0.1')
    cli_port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    print(f'CPHT backend on http://{HOST}:{cli_port}/  (serving {DASH}, data={DATA})')
    print(f'  required tags for upload: {len(REQUIRED_TAGS)} columns')
    ThreadingHTTPServer((HOST, cli_port), Handler).serve_forever()
