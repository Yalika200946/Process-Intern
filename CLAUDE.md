# Bangchak Plant 3 CPHT Analytics

## Project scope

This repository supports heat-exchanger performance, fouling and cleaning analysis, CIT/F101 impact, forecasting, cleaning prioritization, economics, and an approved dashboard dataset.

## Mandatory development rules

- Do not move, rename, delete, or overwrite legacy files without explicit approval.
- Keep raw data immutable.
- Store canonical processed outputs as Parquet.
- One notebook answers one primary analytical question and declares its inputs and outputs.
- Notebooks must Restart Kernel and Run All; notebook memory is never an interface.
- Reusable engineering and modeling logic belongs in `src/`.
- Distinguish `MEASURED`, `CALCULATED`, `INFERRED`, and `ASSUMED` values.
- E101G has no direct sensors and must remain explicitly inferred.
- Do not assume post-TAM periods are perfectly clean.
- Do not interpret `Q_norm` as fouling until its formula is approved.
- Use chronological validation for time series; prevent future, target, and same-timestamp leakage.
- Compare every model with a simple baseline.
- Load limits and assumptions from configuration; never hard-code them.
- The dashboard consumes Stage 15 approved outputs and does not reproduce core calculations.

## Contract workflow

Stage contracts are defined in `config/data_contracts.yaml` and loaded through `src/schemas.py`.
Every output must validate before it is consumed downstream. Unconfirmed limits or formulas must remain `REQUIRES_ENGINEERING_CONFIRMATION`.

