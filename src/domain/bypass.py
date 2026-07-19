"""
Per-HX bypass capability, parsed from the plant's real list:
`Data/list bypass Cleaning Heat Exchanger.xlsx` (received 2026-07-08).

THIS FILE IS THE SINGLE SOURCE OF TRUTH for "can this HX be cleaned online" —
2026-07-12 correction: earlier, `08_cleaning_priority_ranking.ipynb` and
`07_time_to_clean_prediction.ipynb` each carried their OWN hand-written
SWAP_CAPABLE/TAM_ONLY lists that directly CONTRADICTED this real plant file
(e.g. E103AB/E106AB/E107AB/E109AB were coded "online-clean demonstrated" despite
the sheet marking them TAM-only; E101AB/E105AB were coded TAM-only despite
having a real bypass). Every consumer must import `BYPASS_CONFIG` from here.

The sheet lists individual shells (3E101A, 3E101B, ...) with tube-side and
shell-side bypass yes/no plus a remark ("TAM" = no bypass, clean only at
turnaround; "... ร่วม T/S & S/S" = one shared bypass valve covers the whole
listed set). This module maps shells onto the analysis HX groups used
everywhere else (E101AB = shells 3E101A+3E101B, ...) and classifies each
group's `online_mode`:

  * 'full'    — every shell in the group can be pulled without a full plant
                shutdown: either a SHARED bypass valve covers the group (any
                shell's remark says "ร่วม"), or every individual shell has its
                own tube+shell bypass marked.
  * 'partial' — SOME but not all shells are individually bypassable, with NO
                shared-valve remark tying them together (e.g. E101CD: shell C
                is hard-piped/TAM-only, shell D has its own bypass) — only the
                bypassable shell(s) can be pulled online; the other keeps
                fouling until TAM. `duty_fraction` = bypassable/total shells,
                used to scale the achievable online-clean benefit.
  * 'none'    — no shell has a bypass; the whole group waits for TAM.

Import `BYPASS_CONFIG` (dict per HX) or run as a script to print the table.
"""
import os
import re
from pathlib import Path
import pandas as pd

DATA = Path(os.environ.get('CPHT_DATA_DIR', r'C:\Desktop\Bangchak Internship 2026\Data'))
XLSX = DATA / 'list bypass Cleaning Heat Exchanger.xlsx'

# shell code (3E101A) -> analysis HX group (E101AB), mirroring cpht_config groups
SHELL_TO_GROUP = {
    '3E101A': 'E101AB', '3E101B': 'E101AB',
    '3E101C': 'E101CD', '3E101D': 'E101CD',
    '3E101E': 'E101EF', '3E101F': 'E101EF',
    '3E102': 'E102',
    '3E103A': 'E103AB', '3E103B': 'E103AB',
    '3E104': 'E104',
    '3E105A': 'E105AB', '3E105B': 'E105AB',
    '3E106A': 'E106AB', '3E106B': 'E106AB',
    '3E107A': 'E107AB', '3E107B': 'E107AB',
    '3E108A': 'E108AB', '3E108B': 'E108AB',
    '3E109A': 'E109AB', '3E109B': 'E109AB',
    '3E110A': 'E110ABC', '3E110B': 'E110ABC', '3E110C': 'E110ABC',
    '3E111': 'E111',
    '3E112A': 'E112AB', '3E112B': 'E112AB',
    # plant sheet lists a single 3E113 shell; analysis tracks E113A + spare E112C
    '3E113': 'E113A',
}


def _load_shells():
    raw = pd.read_excel(XLSX, sheet_name='Sheet1', header=None)
    shells = []
    for _, r in raw.iterrows():
        code = str(r[0]).strip().replace(' ', '')
        if not re.match(r'^3E\d{3}[A-F]?$', code):
            continue
        tube_yes = str(r[4]).strip() == '√'
        shell_yes = str(r[6]).strip() == '√'
        remark = str(r[8]).replace('\n', ' ').strip() if pd.notna(r[8]) else ''
        shells.append(dict(shell=code, tube_bypass=tube_yes, shell_bypass=shell_yes,
                           remark=remark, fluid_shell=str(r[2]).strip() if pd.notna(r[2]) else '',
                           fluid_tube=str(r[3]).strip() if pd.notna(r[3]) else ''))
    return shells


def build_bypass_config():
    """{HX: {online_mode, duty_fraction, bypass, tube_bypass, shell_bypass, shells, remark, source}}

    online_mode/duty_fraction is the authoritative online-cleaning capability (see
    module docstring). `bypass` is kept as a boolean convenience (True unless
    online_mode=='none') for callers that only need yes/no."""
    cfg = {}
    for s in _load_shells():
        hx = SHELL_TO_GROUP.get(s['shell'])
        if hx is None:
            continue
        c = cfg.setdefault(hx, dict(shells=[], remarks=[]))
        c['shells'].append(dict(shell=s['shell'], tube=s['tube_bypass'], shell_side=s['shell_bypass'],
                                bypassable=(s['tube_bypass'] and s['shell_bypass']),
                                remark=s['remark']))
        if s['remark']:
            c['remarks'].append(s['remark'])

    for hx, c in cfg.items():
        c['remark'] = ' / '.join(sorted(set(c['remarks']))) if c['remarks'] else ''
        del c['remarks']
        c['source'] = 'list bypass Cleaning Heat Exchanger.xlsx (plant, 2026-07-08)'

    # E111: its own row shows shell-side bypass only, but 3E110C's remark says
    # "3E-110C & 3E-111 Bypass ร่วม T/S" — tube-side bypass is SHARED with 3E110C,
    # so the exchanger is bypassable through the shared arrangement.
    if 'E111' in cfg:
        e110 = cfg.get('E110ABC', {})
        if any('3E-111' in s.get('remark', '') for s in e110.get('shells', [])):
            for s in cfg['E111']['shells']:
                s['tube'] = True; s['bypassable'] = s['tube'] and s['shell_side']
            cfg['E111']['remark'] = ((cfg['E111']['remark'] + ' / ') if cfg['E111']['remark'] else '') + \
                                    'tube bypass ร่วมกับ 3E-110C (จาก remark แถว 3E110C)'

    # classify online_mode per group: shared valve (any 'ร่วม' remark) -> full;
    # else all-bypassable -> full, some -> partial (duty_fraction = bypassable/total), none -> none
    for hx, c in cfg.items():
        shells = c['shells']
        n_total = len(shells)
        n_ok = sum(1 for s in shells if s['bypassable'])
        shared = 'ร่วม' in c['remark']
        if shared or n_ok == n_total:
            mode, frac = 'full', 1.0
        elif n_ok > 0:
            mode, frac = 'partial', round(n_ok / n_total, 3)
        else:
            mode, frac = 'none', 0.0
        c['online_mode'] = mode
        c['duty_fraction'] = frac
        c['bypass'] = mode != 'none'                       # convenience boolean (any capability)
        c['tube_bypass'] = any(s['tube'] for s in shells)
        c['shell_bypass'] = any(s['shell_side'] for s in shells)

    # E112C is the physical spare for E113A's train position (3E113 row covers the pair)
    if 'E113A' in cfg and 'E112C' not in cfg:
        c = dict(cfg['E113A'])
        c['remark'] = (c['remark'] + ' / ' if c['remark'] else '') + 'spare shell ของ E113A (สลับใช้ตำแหน่งเดียวกัน)'
        cfg['E112C'] = c
    return cfg


try:
    BYPASS_CONFIG = build_bypass_config()
except FileNotFoundError:    # xlsx missing on another machine (e.g. anonymized demo) — degrade gracefully
    BYPASS_CONFIG = {}
# NOTE: anything other than FileNotFoundError (bad sheet layout, locked/corrupt xlsx, a
# parsing regression) is intentionally NOT swallowed here -- it used to be caught by a bare
# `except Exception`, which silently produced an empty BYPASS_CONFIG on a transient failure
# and made every HX look like "no bypass / TAM-only" everywhere downstream (cleaning_logistics.json,
# the dashboard's bypass table, the online-clean optimizer) with no error surfaced anywhere.
# Let it raise loudly instead so a real failure is never mistaken for "not a real bypass".


# ───────────────────── additive feasibility-status labels (2026-07-17) ─────────────────────
# Pure relabeling over `online_mode`/`duty_fraction` computed above -- does NOT change how
# either is computed. Vocabulary matches the TAM_ONLY/ONLINE_FULL/ONLINE_PARTIAL/SWAP_CAPABLE
# split requested for the cleaning-feasibility taxonomy (see
# docs/UNRESOLVED_ENGINEERING_DECISIONS.md and docs/archive/MIGRATION_MAP.md).
FEASIBILITY_LABELS = {'full': 'ONLINE_FULL', 'partial': 'ONLINE_PARTIAL', 'none': 'TAM_ONLY'}

# HX with a known interchangeable spare shell (from cpht_config.PARALLEL_SHELL_GROUPS, e.g.
# E113A<->E112C) -- these can be taken offline for cleaning by switching to the spare
# regardless of whether they also carry an online bypass, so SWAP_CAPABLE takes precedence
# over the bypass-derived label for them.
from src.domain.config import PARALLEL_SHELL_GROUPS as _PARALLEL_SHELL_GROUPS  # noqa: E402
_SWAP_CAPABLE_HX = {hx for pair in _PARALLEL_SHELL_GROUPS for hx in pair}


def feasibility_label(hx):
    """Return TAM_ONLY / ONLINE_PARTIAL / ONLINE_FULL / SWAP_CAPABLE for one HX group."""
    if hx in _SWAP_CAPABLE_HX:
        return 'SWAP_CAPABLE'
    mode = BYPASS_CONFIG.get(hx, {}).get('online_mode')
    return FEASIBILITY_LABELS.get(mode, 'TAM_ONLY')


if __name__ == '__main__':
    for hx, c in sorted(BYPASS_CONFIG.items()):
        print(f"{hx:9s} mode={c['online_mode']:7s} duty_frac={c['duty_fraction']:.2f} "
              f"shells={[(s['shell'], s['bypassable']) for s in c['shells']]} {c['remark']}")
