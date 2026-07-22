# Batch 5 - Configuration-Aware CPHT Network Hard Gate

## Outcome

Status: `BLOCKED`

The CPHT-2 pilot remains provisional, but the full configuration-aware network cannot be validated from current evidence.

## Evidence

- CPHT-2 flow closure: provisional, 97.26% of records within the screening tolerance.
- CPHT-2 mix closure: provisional, 787 valid records, MAE 3.84 degC.
- Branch 1FI015 propagation: provisional, 206 chronological test records, ending at E104 outlet.
- Branches 1FI016 and 1FI017: no chronological end-to-end propagation validation.
- E105AB: no validated counterfactual response model; hot-in tag identity remains conflicted.
- Terminal configuration: blocked because E113A/E112C lineup has no timestamped valve/shell history and E112C has no direct calculable record.
- Measured CIT reproduction at 1TI116: blocked.

## Consequence

Full-network CIT, single-HX network recovery, compensation ratio, and multi-HX interaction remain prohibited. Batch 6 cannot execute scientifically until the hard network inputs are resolved.

## Required engineering input

1. Resolve and approve the E105AB hot-in tag and counterfactual temperature basis.
2. Provide timestamped E113A/E112C active/bypass/cleaning state or an approved inference rule with auditable evidence.
3. Provide E112C crude-side measurements/flow evidence or approve a substitution model and its validity scope.
4. Approve the configuration-specific CIT reproduction acceptance criteria after chronological validation.

Runtime evidence is under `reports/tables/mvp_real_data/full_engineering_program/batch_05/`.
