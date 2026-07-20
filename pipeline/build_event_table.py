"""
Build the per-HX run-end event / censoring taxonomy (ข้อ 11).

Every downstream RUL/survival estimate needs to know WHY a run ended, not just how long
it lasted: a run that ended because a plant-wide TAM happened is not the same kind of
observation as one that ended because the operator actually cleaned it at/near its
threshold. Treating every run-end as an equivalent "failure" event (the previous behavior
of phm_analysis.py's C3 Weibull fit) silently biases the survival estimate toward whatever
mix of TAM/preventive/threshold-driven cleans happens to be in the historical data.

event_category per completed run (classified from the event that STARTED the *next* run,
i.e. Fouling_Rate_By_Run.csv's `Start_event`, cross-referenced with Cleaning_Events.csv's
measured-recovery confidence and this run's own U_relative trajectory):
  threshold_driven_clean  -- a real SWITCH clean, and the run reached >= THRESHOLD_CROSS_TOLERANCE
                             of its trigger-drop before ending. Observed event (not censored).
  preventive_clean        -- a real SWITCH clean, but ended well before its threshold.
                             Observed event (not censored) -- the operator's choice IS the
                             event of interest for run-duration survival.
  TAM                     -- ended because of a plant-wide turnaround, not the HX's own
                             condition. Censored (didn't fail on its own account).
  shutdown                -- KNOWN GAP: no signal in this codebase currently distinguishes a
                             broader unit shutdown from a TAM. Never emitted today; reserved
                             in EVENT_CATEGORIES for when/if such a signal exists. Any run-end
                             that would conceptually be "shutdown" is currently folded into
                             mode_transition (ambiguous, ends up censored) or TAM (if the next
                             run's Start_event says so) -- do not treat this classifier as
                             having solved that distinction.
  mode_transition         -- a SWITCH with no measurable positive U_relative recovery jump
                             (Cleaning_Events.csv's `Possible`/`Uncertain` confidence tier) --
                             i.e. asserted by config but not corroborated by a real fouling
                             recovery. Censored by default (conservative: don't invent a
                             failure event without recovery evidence).
  censored_in_progress    -- the current, still-running run for this HX. Always censored;
                             duration_days is a lower bound on the true (unknown) run length.

Run: python pipeline/build_event_table.py
"""
import os, sys, json
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get('CPHT_DATA_DIR', r'C:\Desktop\Bangchak Internship 2026\Data'))
OUT_CSV = DATA / 'Event_Table.csv'
OUT_JSON = REPO / 'dashboard' / 'data' / 'event_table.json'
sys.path.append(str(REPO))
from src.models import phm_config as C


def _num(v, nd=4):
    return None if v is None or (isinstance(v, float) and not np.isfinite(v)) else round(float(v), nd)


def _run_end_urel(feat, hx, run_id):
    """Last U_relative value recorded during this run (same convention export_end_of_run.py
    uses for the CURRENT run: last observed point of the run's own days-on-duty axis)."""
    rid_col, ucol = f'{hx}_run_id', f'{hx}_U_relative'
    if rid_col not in feat.columns or ucol not in feat.columns:
        return None
    sub = feat.loc[feat[rid_col] == run_id, ucol].dropna()
    return float(sub.iloc[-1]) if not sub.empty else None


def main():
    fr = pd.read_csv(DATA / 'Fouling_Rate_By_Run.csv')
    feat = pd.read_csv(DATA / 'Feature_calculated.csv', parse_dates=['Timestamp']).set_index('Timestamp')
    events_csv = DATA / 'Cleaning_Events.csv'
    ce = pd.read_csv(events_csv) if events_csv.exists() else pd.DataFrame(
        columns=['HX', 'run_ended', 'type', 'confidence', 'event_status'])

    trigger_urel = 1.0 - C.TRIGGER_DROP_FRAC_FOR_EVENT_TABLE
    rows = []
    n_by_cat = {}

    for hx in sorted(fr.HX.unique()):
        frx = fr[fr.HX == hx].sort_values('Run').reset_index(drop=True)
        cex = ce[ce.HX == hx] if 'HX' in ce.columns else ce.iloc[0:0]
        last_run = int(frx.iloc[-1]['Run'])

        for i, row in frx.iterrows():
            run = int(row['Run'])
            start_date = str(row.get('Run_start'))[:10] if pd.notna(row.get('Run_start')) else None
            duration = _num(row.get('Duration_days'), 1)

            if run == last_run:
                # still-open run: always censored, duration is a lower bound only
                category, censored, threshold_crossed, evidence_confidence = (
                    'censored_in_progress', True, None, None)
                end_date = None
            else:
                nxt = frx[frx.Run == run + 1]
                next_se = nxt.iloc[0]['Start_event'] if not nxt.empty else None
                end_date = nxt.iloc[0].get('Run_start') if not nxt.empty else None
                end_date = str(end_date)[:10] if pd.notna(end_date) else None

                u_end = _run_end_urel(feat, hx, run)
                frac_of_threshold = (_num((1 - u_end) / (1 - trigger_urel), 3)
                                     if (u_end is not None and trigger_urel < 1) else None)
                threshold_crossed = bool(frac_of_threshold is not None
                                          and frac_of_threshold >= C.THRESHOLD_CROSS_TOLERANCE)

                ce_row = cex[(cex.run_ended == run) & (cex.type == 'SWITCH')] if not cex.empty else cex.iloc[0:0]
                ce_row = ce_row.iloc[0] if not ce_row.empty else None
                real_clean = ce_row is not None and ce_row.get('event_status') == 'SWITCH_CANDIDATE'

                if next_se == 'TAM':
                    category, censored = 'TAM', True
                elif next_se == 'SWITCH' and real_clean:
                    category, censored = (('threshold_driven_clean', False) if threshold_crossed
                                           else ('preventive_clean', False))
                elif next_se == 'SWITCH':
                    # SWITCH asserted by config but no measurable recovery -- ambiguous, don't
                    # invent a failure event without corroborating evidence (see module docstring).
                    category, censored = 'mode_transition', True
                else:
                    # DATA_START or unrecognized -- shouldn't occur mid-series; conservative fallback.
                    category, censored = 'mode_transition', True
                evidence_confidence = (ce_row.get('confidence') if ce_row is not None
                                       else ('Confirmed' if next_se == 'TAM' else None))

            n_by_cat[category] = n_by_cat.get(category, 0) + 1
            rows.append(dict(HX=hx, Run=run, start_date=start_date, end_date=end_date,
                             duration_days=duration, event_category=category, censored=censored,
                             threshold_crossed=threshold_crossed, evidence_confidence=evidence_confidence))

    out_df = pd.DataFrame(rows)
    out_df.to_csv(OUT_CSV, index=False, encoding='utf-8')

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(
        dict(as_of=pd.Timestamp.now().strftime('%Y-%m-%d'), n_by_category=n_by_cat,
             note='censoring taxonomy for survival analysis (ข้อ 11/12) — threshold_driven_clean '
                  'and preventive_clean are observed events; TAM/mode_transition/censored_in_progress '
                  'are right-censored (see pipeline/build_event_table.py docstring)',
             events=rows),
        ensure_ascii=False, indent=1), encoding='utf-8')

    print(f'Wrote {OUT_CSV.name} + {OUT_JSON.name}: {len(out_df)} run-end events, {n_by_cat}')


if __name__ == '__main__':
    main()
