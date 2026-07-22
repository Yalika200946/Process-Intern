Status: CURRENT (reconciliation pass, 2026-07-22)

# Missing requirements blocking a validated dashboard

Sourced from `registries/blocker_register.csv`, `REVIEW_GUIDE.md` §"Missing evidence requiring explicit resolution", and the reconciliation findings in `claude_vs_codex_logic_reconciliation.csv`.

1. **Approved HX transferable area, active-shell basis, and LMTD correction factor (F).** Blocks verified U (L08), confirmed fouling (L13/L14), and by extension every downstream ranking/economics claim that currently reads U_relative as if it were validated.
2. **Confirmed maintenance/cleaning history and clean-state evidence.** Blocks a confirmed clean baseline (L11), confirmed fouling index (F17), and turns every "cleaning event" the dashboard displays into an unconfirmed candidate (L16).
3. **Time-resolved valve/bypass/split/shell/standby/substitution history.** Blocks configuration-aware masking for E101EF/E101G and the residue-side E113A/E112C/E112AB/E108AB lineup; without it, per-shell condition claims for those HX cannot be trusted.
4. **Approved hot-side flow and property basis.** Blocks Qhot, energy-balance closure, and effectiveness (F04/F12/F11) - currently zero records for all three.
5. **Full CPHT branch propagation and measured-CIT closure with approved error thresholds.** Blocks full-network CIT (L19/L21); only one pilot branch (E103AB→E104) and one pilot endpoint exist today, and even that pilot's own acceptance threshold (CLI-003) is still provisional.
6. **Approved furnace efficiency, LHV, fuel tags, limits, and operating basis.** Blocks any legitimate fuel/THB saving claim (L22/L23) - the dashboard currently states one anyway.
7. **A forecast that beats persistence for a declared horizon, with an approved action threshold.** Currently the linear trend loses to persistence for 3 of 4 eligible HX, and no threshold is approved at all (L17).
8. **Approved operational, economic, crew, bypass, and scheduling constraints for optimization.** `optimization_readiness.csv` marks constrained schedule optimization BLOCKED outright; the dashboard's cleaning-plan wizard is built as if this were solved.
9. **One converged ranking methodology.** The dashboard currently ships two (engineering_priority_score vs hx_ranking.json priority_score) that disagree, with no arbitration rule (L24).
10. **A generation/approval-status contract enforced end to end.** `dashboard/data/*.json` predates the entire Codex MVP program with no mechanism stopping it from being served or mixed with newer canonical output (L01, CLI-007).
