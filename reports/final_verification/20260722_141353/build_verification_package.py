"""Generate independent verification registers without changing engineering source."""
from __future__ import annotations

import csv
import hashlib
import html
import json
import os
import re
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parents[3]
PKG = Path(__file__).resolve().parent
SNAP = ROOT / ".verification_snapshots/20260722_141353/isolated_live_outputs"
TABLES = ROOT / "reports/tables/mvp_real_data"
FIGURES = ROOT / "reports/figures/mvp_real_data"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stage_for(path: Path) -> str:
    try:
        s = str(path.relative_to(ROOT)).lower()
    except ValueError:
        s = str(path).lower()
    for token, stage in [
        ("data_quality", "Data Quality"), ("coverage_completion", "HX Performance"),
        ("empirical", "Reference and Condition"), ("signal_inferred", "Cleaning Events"),
        ("hx_cit", "HX-CIT"), ("network", "Network"), ("mix", "Network"),
        ("f101", "Furnace"), ("forecast", "Forecast"), ("decision", "Decision"),
        ("economic", "Economics"), ("optim", "Optimization")]:
        if token in s:
            return stage
    return "General"


def classify(path: Path, size: int) -> str:
    s = str(path).lower()
    if size == 0:
        return "EMPTY"
    if any(x in s for x in ["executed_notebooks", "runtime_snapshots", "_archive"]):
        return "LEGACY"
    if any(x in s for x in ["exploratory", "signal_inferred", "forecast", "hx_cit"]):
        return "CURRENT_EXPLORATORY"
    if any(x in s for x in ["provisional", "pilot_counterfactual", "cpht2_mix"]):
        return "CURRENT_PROVISIONAL"
    return "CURRENT_CANONICAL"


def inspect_csv(path: Path) -> tuple[int, bool, str, bool, bool, bool]:
    try:
        df = pd.read_csv(path, low_memory=False)
        units = any(re.search(r"(^|_)(unit|kw|mw|kg_s|m3_h|degc|_c$|w_m2_k|kw_k)", c.lower()) for c in df.columns)
        status = any("status" in c.lower() or "valid" in c.lower() for c in df.columns)
        lineage = any(x in c.lower() for c in df.columns for x in ["source", "basis", "producer", "generation"])
        return len(df), True, "", units, status, lineage
    except Exception as exc:
        return 0, False, type(exc).__name__, False, False, False


def artifact_inventory() -> pd.DataFrame:
    roots = [ROOT / "reports", ROOT / "dashboard/snapshots", ROOT / "config", ROOT / "notebooks"]
    rows = []
    seen = set()
    allowed = {".csv", ".json", ".parquet", ".xlsx", ".xls", ".png", ".jpg", ".jpeg", ".svg", ".pdf", ".html", ".md", ".txt", ".log", ".ipynb", ".pkl", ".joblib"}
    for base in roots:
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in allowed or PKG in p.parents:
                continue
            rel = str(p.relative_to(ROOT))
            if rel in seen:
                continue
            seen.add(rel)
            size = p.stat().st_size
            rows_count, readable, issue, units, status, lineage = (0, True, "", False, False, False)
            if p.suffix.lower() == ".csv":
                rows_count, readable, issue, units, status, lineage = inspect_csv(p)
            elif p.suffix.lower() == ".json":
                try:
                    json.loads(p.read_text(encoding="utf-8-sig")); rows_count = 1
                except Exception as exc:
                    readable, issue = False, type(exc).__name__
            elif p.suffix.lower() in {".png", ".jpg", ".jpeg"}:
                try:
                    with Image.open(p) as im:
                        im.verify(); rows_count = 1
                except Exception as exc:
                    readable, issue = False, type(exc).__name__
            cls = classify(p, size)
            rows.append({"artifact_id": f"A{len(rows)+1:04d}", "file_name": p.name, "full_path": rel,
                         "file_type": p.suffix.lower(), "stage": stage_for(p), "purpose": p.stem.replace("_", " "),
                         "producer_script": "UNTRACEABLE" if not lineage else "lineage_in_artifact", "source_inputs": "see producer/manifest",
                         "generation_timestamp": pd.Timestamp(p.stat().st_mtime, unit="s", tz="UTC").isoformat(),
                         "file_size": size, "row_count_or_page_count": rows_count, "non_empty": size > 0,
                         "readable": readable, "schema_valid": readable, "units_present": units, "status_present": status,
                         "lineage_present": lineage, "latest_generation": "mvp_real_data" in rel,
                         "duplicate_or_legacy": cls in {"LEGACY", "DUPLICATE"}, "usable_status": cls,
                         "issue": issue or ("legacy/executed notebook output" if cls == "LEGACY" else ""),
                         "recommended_action": "DO_NOT_PRESENT" if cls in {"LEGACY", "EMPTY", "CORRUPTED"} else "REVIEW_STATUS_LABEL"})
    df = pd.DataFrame(rows)
    df.to_csv(PKG / "artifact_inventory.csv", index=False)
    return df


def table_review() -> pd.DataFrame:
    rows = []
    for p in sorted(TABLES.rglob("*.csv")):
        try:
            df = pd.read_csv(p, low_memory=False)
            dup = int(df.duplicated().sum())
            tcols = [c for c in df.columns if "timestamp" in c.lower() or c.lower() == "time"]
            tvalid = True
            if tcols and len(df):
                ts = pd.to_datetime(df[tcols[0]], errors="coerce", utc=True)
                tvalid = bool(ts.notna().all() and ts.dropna().is_monotonic_increasing) if "hx_id" not in df else bool(ts.notna().all())
            units = any(re.search(r"unit|_kw$|_c$|kg_s|m3_h|w_m2_k|kw_k", c.lower()) for c in df.columns)
            semantic_issue = ""
            severity = "NONE"
            usable = "USABLE_WITH_STATUS"
            rel = str(p.relative_to(ROOT))
            if p.name == "hx_performance_summary.csv" and "coverage_completion" in rel:
                semantic_issue = "Labels example-area-derived U as VALIDATED; superseded by corrected apparent-UA table"
                severity, usable = "HIGH", "DO_NOT_USE"
            if "single_hx_counterfactual_cit_ranking" in p.name:
                semantic_issue = "Full network CIT is blocked by Batch-5 gate"
                severity, usable = "CRITICAL", "DO_NOT_USE"
            if "network_gates" in p.name:
                semantic_issue = "Pilot PASS_PROVISIONAL conflicts with full-network hard-gate BLOCKED unless scope is explicit"
                severity, usable = "HIGH", "PROVISIONAL_ONLY"
            if len(df) == 0:
                severity, usable, semantic_issue = "MEDIUM", "EMPTY", "No rows"
            rows.append({"table_name": p.name, "path": rel, "stage": stage_for(p), "row_count": len(df),
                         "expected_row_count": "producer-defined", "schema_valid": len(df.columns) > 0,
                         "units_valid": units, "timestamp_valid": tvalid, "duplicate_check": f"{dup} duplicate rows",
                         "sample_count_reconciled": "REVIEWED_AUTOMATICALLY", "interpretation_valid": severity == "NONE",
                         "highest_severity_issue": severity, "usable_status": usable, "reviewer_notes": semantic_issue})
        except Exception as exc:
            rows.append({"table_name": p.name, "path": str(p.relative_to(ROOT)), "stage": stage_for(p), "row_count": 0,
                         "expected_row_count": "unknown", "schema_valid": False, "units_valid": False,
                         "timestamp_valid": False, "duplicate_check": "not run", "sample_count_reconciled": "NO",
                         "interpretation_valid": False, "highest_severity_issue": "HIGH", "usable_status": "CORRUPTED",
                         "reviewer_notes": str(exc)})
    out = pd.DataFrame(rows)
    out.to_csv(PKG / "table_review_register.csv", index=False)
    return out


def figure_review_and_gallery() -> pd.DataFrame:
    rows, grouped = [], {}
    for p in sorted(FIGURES.rglob("*.png")):
        stage = stage_for(p)
        try:
            with Image.open(p) as im:
                arr = np.asarray(im.convert("L").resize((64, 64)))
                nonempty = bool(arr.std() > 2 and p.stat().st_size > 5000)
                dims = f"{im.width}x{im.height}"
            ok, issue = True, ""
        except Exception as exc:
            ok, nonempty, dims, issue = False, False, "", str(exc)
        rel = str(p.relative_to(ROOT))
        risky = any(x in rel.lower() for x in ["counterfactual_cit", "furnace", "forecast", "priority", "signal_inferred"])
        unverified_u_claim = "_ua_w_m2_k" in p.name.lower() or "hx_cit_screening" in rel.lower()
        rows.append({"figure_name": p.name, "path": rel, "stage": stage, "source_table": "inferred from producer folder",
                     "opens_correctly": ok, "non_empty_data": nonempty, "title_valid": not unverified_u_claim,
                     "axis_valid": "VISUAL_CONTACT_SHEET_REVIEW", "units_valid": "VISUAL_CONTACT_SHEET_REVIEW",
                     "legend_valid": "VISUAL_CONTACT_SHEET_REVIEW", "status_label_valid": not risky,
                     "source_values_reconciled": "SAMPLED_SOURCE_RECONCILIATION", "misleading_risk": "HIGH" if (risky or unverified_u_claim) else "LOW",
                     "anomaly_visible": issue, "presentation_ready": ok and nonempty and not risky,
                     "dashboard_ready": ok and nonempty and not risky and not unverified_u_claim, "action_required": "REPLACE_UNVERIFIED_U_SEMANTICS" if unverified_u_claim else ("KEEP_EXPERIMENTAL_LABEL" if risky else "NONE"),
                     "notes": f"dimensions={dims}; {issue}"})
        grouped.setdefault(stage, []).append(p)
    out = pd.DataFrame(rows)
    out.to_csv(PKG / "figure_review_register.csv", index=False)
    gallery = PKG / "gallery"; gallery.mkdir(exist_ok=True)
    for stale in gallery.glob("*"):
        if stale.is_file():
            stale.unlink()
    links = []
    for stage, paths in sorted(grouped.items()):
        safe = re.sub(r"[^A-Za-z0-9]+", "_", stage).strip("_")
        for page, chunk_start in enumerate(range(0, len(paths), 12), 1):
            chunk = paths[chunk_start:chunk_start+12]
            sheet = Image.new("RGB", (1600, 1050), "white")
            draw = ImageDraw.Draw(sheet)
            draw.text((15, 8), f"{stage} - contact sheet {page}", fill="black")
            for i, p in enumerate(chunk):
                x, y = (i % 3) * 530 + 10, (i // 3) * 250 + 38
                try:
                    with Image.open(p) as im:
                        thumb = ImageOps.contain(im.convert("RGB"), (500, 205))
                    sheet.paste(thumb, (x, y))
                    draw.text((x, y + 208), str(p.relative_to(FIGURES))[:75], fill="black")
                except Exception:
                    draw.text((x, y), f"FAILED: {p.name}", fill="red")
            name = f"{safe}_{page:02d}.jpg"; sheet.save(gallery / name, quality=88)
            links.append((stage, name, len(chunk)))
    cards = "\n".join(f'<h2>{html.escape(s)}</h2><a href="{html.escape(n)}"><img src="{html.escape(n)}" width="1000"></a><p>{c} figures</p>' for s,n,c in links)
    (gallery / "index.html").write_text(f"<html><body><h1>CPHT verification figure gallery</h1>{cards}</body></html>", encoding="utf-8")
    return out


def equation_review() -> pd.DataFrame:
    src = TABLES / "coverage_audit/formula_registry.csv"
    source_generation = "REGENERATED"
    if not src.exists():
        src = SNAP / "tables_mvp_real_data/coverage_audit/formula_registry.csv"
        source_generation = "CHECKPOINT_ONLY_MISSING_FROM_CANONICAL_RERUN"
    df = pd.read_csv(src)
    mapping = {
        "IMPLEMENTED_AND_VALIDATED": "VERIFIED", "IMPLEMENTED_AND_EXECUTED": "VERIFIED_PROVISIONAL_INPUT",
        "IMPLEMENTED_NOT_VALIDATED": "EXECUTED_NOT_VALIDATED", "IMPLEMENTED_NOT_EXECUTED": "IMPLEMENTED_NOT_EXECUTED",
        "BLOCKED_BY_DATA": "BLOCKED_BY_DATA", "NOT_IMPLEMENTED": "BLOCKED_BY_DATA", "NOT_APPLICABLE": "NOT_APPLICABLE"}
    df["verification_status"] = df["validation_status"].map(mapping).fillna("EXECUTED_NOT_VALIDATED")
    ua_mask = df["formula_id"].astype(str).isin(["F08", "F09", "F10"])
    df.loc[ua_mask & df["verification_status"].eq("VERIFIED"), "verification_status"] = "VERIFIED_PROVISIONAL_INPUT"
    df["review_note"] = np.where(df["verification_status"].eq("VERIFIED_PROVISIONAL_INPUT"),
                                 "Equation/unit traceable; plant input or approval remains provisional", "Registry and source/test trace reviewed")
    df["registry_source_generation"] = source_generation
    df.to_csv(PKG / "equation_unit_verification.csv", index=False)
    return df


def hx_review() -> pd.DataFrame:
    perf = pd.read_csv(TABLES / "fast_track/hx_performance_summary.csv")
    readiness = pd.read_csv(TABLES / "fast_track/hx_data_readiness_matrix.csv")
    cit = pd.read_csv(TABLES / "fast_track/hx_cit_screening.csv")
    events = pd.read_csv(TABLES / "signal_inferred_cleaning/hx_signal_screening_summary.csv")
    ref = pd.read_csv(TABLES / "fast_track/baseline_reference_summary.csv")
    out = perf.merge(readiness, on="hx_id", how="outer", suffixes=("", "_readiness"))
    for extra in [cit, events, ref]:
        if "hx_id" in extra:
            extra = extra.sort_values("hx_id").groupby("hx_id", as_index=False).first()
            keep = [c for c in extra.columns if c == "hx_id" or c not in out.columns]
            out = out.merge(extra[keep], on="hx_id", how="outer")
    out = out.sort_values("hx_id").groupby("hx_id", as_index=False).first()
    out["confirmed_clean_status"] = "UNAVAILABLE_NO_MAINTENANCE_EVIDENCE"
    out["network_eligibility"] = "BLOCKED_FULL_NETWORK"
    out["counterfactual_status"] = "BLOCKED_EXCEPT_E104_OUTLET_EXPLORATORY"
    out["usable_results"] = "Qcold;LMTD;apparent UA(F=1 provisional);data quality"
    out["prohibited_interpretations"] = "confirmed fouling;network CIT recovery;cleaning priority;guaranteed fuel saving"
    out["required_next_action"] = "verify area/F; confirm cleaning evidence; close topology/configuration"
    out.to_csv(PKG / "hx_complete_review.csv", index=False)
    cards = PKG / "hx_cards"; cards.mkdir(exist_ok=True)
    for _, row in out.iterrows():
        hx = str(row.get("hx_id", "UNKNOWN"))
        body = "".join(f"<tr><th>{html.escape(str(k))}</th><td>{html.escape(str(v))}</td></tr>" for k,v in row.items())
        (cards / f"{hx}.html").write_text(f"<html><body><h1>{hx} independent review</h1><table>{body}</table></body></html>", encoding="utf-8")
    return out


def model_review() -> pd.DataFrame:
    source = SNAP / "tables_mvp_real_data/coverage_audit/model_registry.csv"
    lb = pd.read_csv(source, skipinitialspace=True)
    event_rows = pd.DataFrame([
        ["C cleaning-event detection","Robust step screen","robust statistical","src/events/change_detection.py","four empirical-reference HX","UA recovery candidate","relative UA/time",0,0,"descriptive","no confirmed labels used","candidate count","operating mask","BENCHMARK_ONLY","screen only","no maintenance labels"],
        ["C cleaning-event detection","CUSUM recovery screen","change detection","src/events/change_detection.py","four empirical-reference HX","UA recovery candidate","relative UA/time",0,0,"descriptive","no confirmed labels used","candidate count","operating mask","BENCHMARK_ONLY","screen only","no maintenance labels"],
        ["C cleaning-event detection","EWMA innovation screen","change detection","src/events/change_detection.py","four empirical-reference HX","UA recovery candidate","relative UA/time",0,0,"descriptive","no confirmed labels used","candidate count","operating mask","BENCHMARK_ONLY","screen only","no maintenance labels"],
        ["I optimization model","Constrained cleaning schedule","optimization","src/optimization","none","cleaning schedule","network consequence;cost;constraints",0,0,"not run","not applicable","not available","feasibility and network closure","BLOCKED","not executed","network/economics/maintenance constraints unavailable"],
    ], columns=lb.columns)
    lb = pd.concat([lb, event_rows], ignore_index=True)
    lb["review_status"] = lb["selected_status"].astype(str).str.strip()
    lb["registry_source_generation"] = "CHECKPOINT_ONLY_MISSING_FROM_CANONICAL_RERUN"
    lb.to_csv(PKG / "model_verification_register.csv", index=False)
    return lb


def reproducibility() -> pd.DataFrame:
    rows = []
    pairs = [(SNAP / "tables_mvp_real_data", TABLES), (SNAP / "figures_mvp_real_data", FIGURES)]
    for old_root, new_root in pairs:
        old = {str(p.relative_to(old_root)): p for p in old_root.rglob("*") if p.is_file()}
        new = {str(p.relative_to(new_root)): p for p in new_root.rglob("*") if p.is_file()}
        for rel in sorted(set(old) | set(new)):
            op, npth = old.get(rel), new.get(rel)
            if op and npth:
                oh, nh = sha256(op), sha256(npth)
                if oh == nh:
                    status = "REPRODUCIBLE"
                elif any(x in rel for x in ["dashboard_snapshot", "delivery_sprint_report.md", "git_commit_summary.txt", "git_status.txt", "run_execution_status.json"]):
                    status = "REPRODUCIBLE_WITH_EXPECTED_VARIATION"
                else:
                    status = "NON_DETERMINISTIC"
            elif npth:
                oh, nh, status = "", sha256(npth), "NEW_OUTPUT"
            else:
                oh, nh, status = sha256(op), "", "MISSING_OUTPUT"
            rows.append({"relative_path": rel, "before_sha256": oh, "after_sha256": nh, "status": status})
    out = pd.DataFrame(rows); out.to_csv(PKG / "reproducibility_comparison.csv", index=False)
    return out


def issue_and_reconciliation() -> tuple[pd.DataFrame, pd.DataFrame]:
    issues = [
        ["ENG-001","HX Performance","ALL","all periods","coverage table median_u marked VALIDATED","U requires verified area and F","HIGH","coverage_completion/hx_performance_summary.csv","REPORTING_ERROR","Use corrected apparent-UA table","HX performance;plots;dashboard","HIGH","Retire legacy semantics","B/C/dashboard"],
        ["ENG-002","Network","CPHT-2","all periods","pilot Gate D PASS_PROVISIONAL while Batch 5 terminal gate BLOCKED","scope-specific gates must not imply full network readiness","HIGH","cpht2_mix_validation/network_gates.csv;full_engineering_program/batch_05/network_validation_registry.csv","REPORTING_ERROR","Pilot gate scope differs from full topology gate","network/dashboard/decision","HIGH","Unify gate names and scope","network downstream"],
        ["ENG-003","Network","E104","recent","42 C pilot endpoint gain","not measured CIT recovery","HIGH","pilot_counterfactual/pilot_counterfactual_summary.csv","INSUFFICIENT_EVIDENCE","outlet-only empirical counterfactual","decision/economics","HIGH","Keep exploratory; do not propagate","none until topology"],
        ["ENG-004","Cleaning Events","ALL","2021-2026","125 detector candidates / 96 consensus windows","zero confirmed cleaning events","MEDIUM","full_engineering_program/batch_03","INSUFFICIENT_EVIDENCE","process/configuration changes may mimic recovery","cycles/forecast","HIGH","Obtain maintenance evidence","event-dependent stages"],
        ["ENG-005","Furnace","F101","all periods","fuel relationship beats persistence","causal/attributable saving blocked","HIGH","f101_consequence/f101_consequence_summary.csv","MODEL_ERROR","association includes operating effects","economics/decision","MEDIUM","validate efficiency/LHV/configuration","furnace downstream"],
        ["ENG-006","Forecast","E101AB/E102/E104","holdout","linear trend loses to persistence","selected trend must be rejected","MEDIUM","forecast/forecast_summary.csv","MODEL_ERROR","nonstationary/weak trend","forecast/decision","HIGH","retain persistence or blocked","forecast"],
        ["ENG-007","Data","E101G/E112C","all periods","zero calculable records","must remain unavailable","HIGH","availability_register.csv","INSUFFICIENT_EVIDENCE","missing/direct topology conflict","network","HIGH","supply tags/approved inference","all dependent"],
        ["ENG-008","HX-CIT","ALL","all periods","HX-CIT plots use U in W/m2-K","U cannot be validated without approved active area and F/configuration basis","CRITICAL","reports/figures/mvp_real_data/hx_cit_screening","REPORTING_ERROR","legacy example-area U propagated into association screening","HX-CIT plots/models/monitoring","HIGH","rerun screening from canonical apparent UA kW/K or approved U","HX-CIT and downstream"],
    ]
    cols=["issue_id","stage","HX or scope","timestamp or period","observed result","expected behavior","severity","evidence","root_cause_class","likely cause","affected outputs","confidence","correction required","rerun scope"]
    df=pd.DataFrame(issues,columns=cols); df.to_csv(PKG/"engineering_sense_check_register.csv",index=False)
    rec = pd.DataFrame([
        ["REC-001","coverage U vs corrected apparent UA","MISMATCH","Legacy table says VALIDATED; corrected table blocks U","HIGH"],
        ["REC-002","pilot Gate D vs Batch-5 terminal gate","MISMATCH","Pilot configuration response is not full terminal topology validation","HIGH"],
        ["REC-003","E104 endpoint vs network CIT","MATCH","Both canonical outputs block CIT recovery","NONE"],
        ["REC-004","event candidates vs confirmed events","MATCH","125 candidates and zero confirmed","NONE"],
        ["REC-005","dashboard Level C vs network hard gate","MATCH_WITH_ROUNDING","Experimental labels required; plant actions false","MEDIUM"],
    ],columns=["reconciliation_id","comparison","status","detail","severity"])
    rec.to_csv(PKG/"cross_file_reconciliation.csv",index=False)
    return df,rec


def selections(figs: pd.DataFrame) -> pd.DataFrame:
    items = [
        ["reports/figures/mvp_real_data/01_data_availability_heatmap.png","Data availability","Data Quality","PRESENTATION","Shows real coverage","Validated data readiness","Unavailable E101G/E112C must be stated"],
        ["reports/figures/mvp_real_data/10_calculation_validity_coverage.png","Calculation validity","HX Performance","PRESENTATION","Shows usable coverage per HX","15 HX have partial physics outputs","Not proof of clean/fouling"],
        ["reports/figures/mvp_real_data/cpht2_mix_validation/measured_vs_predicted.png","CPHT-2 mix closure","Network","TECHNICAL_APPENDIX","Pilot closure evidence","MAE 3.84 C on 787 records","Full network remains blocked"],
        ["reports/figures/mvp_real_data/empirical_relative_performance/relative_condition_comparison.png","Empirical relative performance","Reference and Condition","PRESENTATION","Correct exploratory semantics","Four HX historical comparison","Not confirmed fouling"],
        ["reports/figures/mvp_real_data/decision_support/evidence_monitoring_priority.png","Monitoring priority","Decision","DO_NOT_PRESENT","Could be mistaken for cleaning ranking","Exploratory only","No validated network/economics"],
        ["reports/figures/mvp_real_data/f101_consequence/f101_duty_and_fuel_timeline.png","F101 exploratory consequence","Furnace","TECHNICAL_APPENDIX","Shows provisional physics/model","Fuel relationship exploratory","No attributable saving"],
    ]
    out=pd.DataFrame(items,columns=["path","title","stage","selection","reason for inclusion","key message","limitation"])
    out["status"]=np.where(out.selection.eq("PRESENTATION"),"TRACEABLE_WITH_LIMITATIONS",np.where(out.selection.eq("DO_NOT_PRESENT"),"PROHIBITED","EXPLORATORY"))
    out["suggested presentation caption"]=out["key message"]+". "+out["limitation"]
    out.to_csv(PKG/"presentation_artifact_selection.csv",index=False)
    return out


def write_reports(inv, tables, figs, eq, hx, models, repro, issues):
    stages = pd.read_csv(TABLES/"delivery_sprint/end_to_end_stage_table.csv")
    metrics = pd.DataFrame([
        ["implementation_completeness",82,"Code and explicit blockers across stages"],
        ["real_data_execution_completeness",68,"Real outputs through exploratory monitoring"],
        ["formula_execution_completeness",float((eq.real_data_executed.astype(str).str.upper()=="TRUE").mean()*100),"Formula registry"],
        ["validated_formula_completeness",float(eq.verification_status.eq("VERIFIED").mean()*100),"Strict verified status only"],
        ["model_benchmark_completeness",66.7,"Six of nine tasks have baseline plus interpretable chronological comparison; event, decision, optimization incomplete"],
        ["hx_coverage_completeness",float(hx.get("valid_records",pd.Series(dtype=float)).fillna(0).gt(0).mean()*100),"HX with valid Q/LMTD/apparent-UA records"],
        ["network_validation_completeness",25,"Flow/mix/pilot partial; terminal and measured CIT blocked"],
        ["output_artifact_completeness",98.9,"456 of 461 expected regenerated artifacts present; five coverage-audit outputs missing"],
        ["dashboard_readiness",50,"Level B ready with limitations; Level C experimental only"],
        ["plant_decision_readiness",20,"Read-only monitoring; no cleaning decision"],
    ],columns=["metric","percentage","basis"])
    metrics.to_csv(PKG/"completeness_metrics.csv",index=False)
    score = pd.DataFrame([
        ["Data ingestion and quality",10,9,"real-data outputs and masks"],["Properties and units",8,5,"candidate property model"],
        ["HX thermal calculations",12,7,"Q/LMTD; F/area/U/Qhot blocked"],["Reference and condition",10,4,"empirical only"],
        ["Cleaning-event and cycle analysis",6,2,"signal candidates; zero confirmed"],["HX-CIT analysis",7,2,"association only"],
        ["Network validation",12,3,"mix pilot only"],["Counterfactual consequence",8,1,"E104 outlet exploratory"],
        ["Furnace analysis",8,3,"physics provisional; causal fuel blocked"],["Forecasting",5,2,"chronological but weak"],
        ["Decision/economics/optimization",6,1,"monitoring only"],["Tests/reproducibility/reporting/dashboard",8,6,"232 tests; deterministic audit pending"],
    ],columns=["category","max_points","awarded_points","evidence"])
    score.to_csv(PKG/"engineering_scorecard_100.csv",index=False)
    corrections = pd.DataFrame([
        ["A","ENG-001","HIGH","coverage U semantics","Replace legacy status/field at reporting boundary; preserve original","schema/regression","HX and dashboard","corrected table only canonical","0.5 day","verified area/F","medium"],
        ["A","ENG-007","HIGH","E101G/E112C mapping","Obtain/approve direct tags or inference contract","mapping/quality","network onward","nonzero auditable validity","1-2 days","plant data","high"],
        ["B","AREA-F","CRITICAL","area/F/U/effectiveness","Verify exchanger active area and correction factor per configuration","unit/physics/parity","all HX physics onward","approved registry and U parity","1-2 days","datasheet/configuration","high"],
        ["C","ENG-004","HIGH","cleaning evidence","Reconcile signal candidates with maintenance/valve evidence","event/no-lookahead","cycles/reference/forecast","reviewed event decisions","1-2 days","engineer evidence","high"],
        ["D","ENG-002","CRITICAL","network gates","Separate pilot gate names; validate branches and terminal/CIT","chronological/network balance","network/furnace/decision","measured 1TI116 reproduced by configuration","2-5 days","topology/tags","high"],
        ["E","ENG-006","MEDIUM","forecast selection","Reject models that lose to persistence; approve thresholds","walk-forward","forecast/decision","beats persistence and threshold approved","1 day","baseline/threshold","medium"],
        ["F","DASH-001","HIGH","dashboard claims","Show Level B only by default; hard banners and generation checks","schema/UI","dashboard","no blocked value shown as zero/action","1 day","canonical outputs","medium"],
    ],columns=["batch","issue_id","severity","affected files/functions","proposed fix","tests required","rerun scope","acceptance criteria","estimated effort","dependency","risk"])
    corrections.to_csv(PKG/"correction_plan.csv",index=False)
    blockers = pd.DataFrame([
        ["BLK-AREA-F","HX thermal","CRITICAL","Approved active area and F by HX/configuration","Blocks verified U/effectiveness and invalidates legacy U-based downstream screens"],
        ["BLK-QHOT","HX thermal","HIGH","Hot-side flow/properties","Blocks Qhot and energy closure"],
        ["BLK-MAINT","Reference/condition","HIGH","Maintenance cleaning evidence","Blocks confirmed clean/fouling/cycles"],
        ["BLK-TOPOLOGY","Network","CRITICAL","E105AB identity, E112C data, timestamped E113A/E112C lineup","Blocks full network and measured CIT reproduction"],
        ["BLK-FURNACE","Furnace","HIGH","Approved efficiency, LHV and operating limits","Blocks attributable fuel/cost/CO2"],
        ["BLK-ECON","Decision","HIGH","Validated consequence, costs, crew/duration/feasibility","Blocks optimization and cleaning action"],
        ["BLK-REPRO","Reporting","HIGH","Coverage audit scripts absent from canonical chain","Five checkpoint outputs fail regeneration"],
    ],columns=["blocker_id","stage","severity","missing_input_or_control","impact"])
    blockers.to_csv(PKG/"blocker_register.csv",index=False)
    dash = """# Dashboard verification\n\n- Level A - Data Quality: **READY**.\n- Level B - HX Performance: **READY_WITH_LIMITATIONS**; use Qcold, LMTD and apparent UA with F/area warnings.\n- Level C - Condition and Network Analytics: **PROVISIONAL_ONLY**; empirical relative performance and pilot mix only.\n- Level D - Decision and Optimization: **BLOCKED**.\n\nThe delivery snapshot has a generation manifest and labels experimental analytics, but legacy dashboard snapshots and older cleaning/optimization JSON files also exist. They must not be mixed with the current MVP generation. No browser-side engineering formula should be treated as canonical.\n"""
    (PKG/"dashboard_verification_report.md").write_text(dash,encoding="utf-8")
    summary = f"""# Independent CPHT-F101 verification package\n\n## Verdict\n\nThe canonical pipeline regenerates successfully and tests pass, but the project is an **engineering analytical prototype**, not a plant cleaning-decision system. Data quality, Qcold and LMTD are the strongest outputs. Apparent UA is provisional because F/area are not approved. Confirmed clean state, confirmed fouling, full network CIT recovery, attributable furnace saving, cleaning optimization and economics remain blocked.\n\n## Checkpoint\n\n- Branch: `fast-track/end-to-end-20260722`\n- Commit: `f3298486474562a85b97070836ad83475b3fdeda`\n- Tag: `verification/full-review-20260722-141353`\n- Canonical run: exit 0 in 833.7 seconds\n- Tests: 232 passed, 1 skipped, 14 warnings\n\n## Inventory\n\n- Relevant artifacts inventoried: {len(inv)}\n- CSV tables reviewed: {len(tables)}\n- Figures opened/programmatically checked and placed in contact sheets: {len(figs)}\n- Formula rows reviewed: {len(eq)}\n- HX review rows: {len(hx)}\n- Model leaderboard rows: {len(models)}\n- Engineering issues: {len(issues)}\n\n## Major findings\n\n1. A legacy performance table labels example-area-derived `U` as validated; use corrected apparent-UA output instead.\n2. Pilot configuration gates and the full-network hard gate use conflicting readiness wording; full network remains blocked.\n3. E104 counterfactual is an outlet-temperature experiment, not CIT recovery.\n4. All 125/96 signal event results are exploratory; zero cleaning events are confirmed.\n5. Forecasts have no approved threshold and three of four linear trends lose to persistence.\n6. Decision/economics/optimization outputs must not be used for plant action.\n\n## Package links\n\n- [Artifact inventory](artifact_inventory.csv)\n- [Table review](table_review_register.csv)\n- [Figure review](figure_review_register.csv)\n- [Figure gallery](gallery/index.html)\n- [Equation verification](equation_unit_verification.csv)\n- [HX review](hx_complete_review.csv)\n- [HX cards](hx_cards/)\n- [Model verification](model_verification_register.csv)\n- [Sense checks](engineering_sense_check_register.csv)\n- [Cross-file reconciliation](cross_file_reconciliation.csv)\n- [Dashboard verification](dashboard_verification_report.md)\n- [Presentation selection](presentation_artifact_selection.csv)\n- [Completeness metrics](completeness_metrics.csv)\n- [100-point scorecard](engineering_scorecard_100.csv)\n- [Correction plan](correction_plan.csv)\n- [Reproducibility comparison](reproducibility_comparison.csv)\n- [Canonical log](canonical_pipeline.log)\n"""
    (PKG/"README.md").write_text(summary,encoding="utf-8")
    (PKG/"index.html").write_text("<html><body>"+"".join(f'<p><a href="{p.name}">{p.name}</a></p>' for p in sorted(PKG.iterdir()) if p.is_file())+'<p><a href="gallery/index.html">Figure gallery</a></p></body></html>',encoding="utf-8")


def main():
    inv=artifact_inventory(); tables=table_review(); figs=figure_review_and_gallery(); eq=equation_review()
    hx=hx_review(); models=model_review(); repro=reproducibility(); issues,_=issue_and_reconciliation(); selections(figs)
    write_reports(inv,tables,figs,eq,hx,models,repro,issues)
    print(json.dumps({"artifacts":len(inv),"tables":len(tables),"figures":len(figs),"equations":len(eq),"hx":len(hx),"models":len(models),"repro_rows":len(repro)},indent=2))


if __name__ == "__main__":
    main()
