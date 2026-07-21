# CPHT Fouling & Cleaning Decision Support

> **Approved cleanup target:** development is currently limited to the minimal
> CPHT fouling-analysis boundary documented in
> [`docs/MVP_SCOPE.md`](docs/MVP_SCOPE.md). Phase 1 preserves the existing full
> system and adds characterization tests only; the production pipeline below
> has not yet been reduced or replaced.

> **Engineering review mode:** this repository is a read-only decision-support
> prototype for Bangchak Plant 3. It does not control the furnace, write DCS
> setpoints, override alarms/SIS, or replace Process/Operations/Maintenance approval.

The active production path evaluates Crude Preheat Train heat recovery, operating
states, fouling evidence, CIT/furnace impact, cleaning priority, scheduling, and
economics. Candidate methods and assumed limits remain visibly labelled until an
approval record identifies the engineering source, approver, and date.

## Production workflow

`pipeline/run_all.py` is the execution truth. It runs the notebooks under
`notebooks/production/` in dependency order, executes the post-processors, validates
the complete artifact set, and publishes an immutable dashboard snapshot. The
backend serves only the snapshot selected by `dashboard/data/current_snapshot.json`,
so a failed or partial run cannot replace the last validated generation.

```powershell
# Use the Python environment that has requirements.txt installed
python -m pytest -q
python pipeline/run_all.py --timeout 1800
python backend/server.py
```

Each published generation includes `run_manifest.json` with input/config hashes,
code revision, step results, artifact hashes, schema version, and approval summary.
See `docs/requirements/03_Business_Problem_and_Requirements.md` for scope and
`docs/UNRESOLVED_ENGINEERING_DECISIONS.md` for items that still require plant review.

## Safety boundary

- Outputs are recommendations with evidence, confidence, assumptions, and required human review.
- `CANDIDATE` and `ASSUMPTION` values may be displayed for engineering review but are not approved plant limits.
- Low-confidence equipment is routed to `INVESTIGATE`, not an automatic cleaning command.
- Scenario endpoints return isolated what-if results and do not overwrite the published snapshot.

---

## Legacy repository description

This is the code repository for the Furnace Optimization project, focusing on the application of machine learning methods for optimizing furnace performance in industrial oil refinery processes (Bangchak).

## Repository Intent
This repository hosts the code used for research and development of machine learning-based furnace optimization models. The code may be used by forking or otherwise downloading the repository.

## Contents
The repository contains:
- Notebook examples (`notebooks/` folder)
- Python examples (`py_examples/` folder)
- Dataset profiling (`profiling/` folder)
- Code documentation (`docs/` folder)
- Source code (`src/` folder)
- Installation guide (below)

The source code is structured as follows:
- `src/core.py`: high-level stateful module
- `src/core_stateless.py`: high-level stateless module
- `src/core_configs.py`: used for specific furnace datasets and configurations
- `src/data/`: runnable .py files for various preprocessing use cases
- `src/ml/`: runnable .py files for various machine learning use cases + trained ML models
- `src/utils/`: low-level implementation (utilities, metrics, models, plots, etc.)

The Jupyter Notebook examples are as follows:
- `0_profiling.ipynb`: dataset profiling for furnace operation data
- `1_correlation.ipynb`: correlation analysis of furnace parameters
- `1_pca.ipynb`: principal component analysis
- `2_basic_example.ipynb`: basic predictive model example for furnace data
- `3_model_comparison.ipynb`: comparison of different ML models (Linear, MLP, LSTM, etc.)
- `4_optimization.ipynb`: furnace optimization analysis and results

## Problem Statement
Furnace operation efficiency is critical in oil refinery processing. Factors such as fuel consumption, temperature distribution, heat loss, and emission levels significantly affect both operational costs and product quality. Traditional monitoring and control techniques rely on fixed setpoints and manual adjustments, which often lead to suboptimal performance.

Machine learning methods offer the potential to:
1. Predict furnace performance under varying operating conditions
2. Identify optimal operating parameters to minimize fuel consumption
3. Detect anomalies and degradation in furnace components
4. Enable predictive maintenance scheduling

## Objectives
1. Determine the applicability of machine learning methods for furnace operation optimization
2. Develop predictive models capable of estimating furnace efficiency and key performance indicators
3. Identify the minimal set of sensors required for accurate furnace monitoring
4. Implement optimization strategies based on ML predictions to reduce fuel consumption and emissions

## Methodology
Predictive models are developed to estimate furnace performance metrics such as:
- **Flue gas temperature** (indicator of heat transfer efficiency)
- **Fuel consumption rate** (optimization target)
- **Temperature distribution** (product quality indicator)
- **Emission levels** (environmental compliance)
- **Furnace efficiency** (overall thermal performance)

Input parameters include:
- Fuel flow rate
- Air flow rate (primary and secondary)
- Feed material temperature and flow rate
- Ambient conditions
- Furnace wall/tube temperatures
- Stack/flue gas measurements

Multiple regression models are evaluated:
- Linear regression (baseline)
- Multilayer Perceptron (MLP) neural networks
- Long Short-Term Memory (LSTM) recurrent neural networks
- GRU recurrent neural networks
- Ensemble methods (Random Forest, AdaBoost, Bagging)
- Support Vector Machines

## Installing Required Packages
To install the required packages for running this project:

1. Install Python 3.10+

2. Clone repository
   ```
   git clone <repository-url>
   ```

3. Navigate to repository folder
   ```
   cd furnace-optimization
   ```

4. Create virtual environment
   ```
   python -m venv venv
   ```

5. Activate virtual environment
   ```
   # Windows
   venv\Scripts\activate
   # Linux/Mac
   source venv/bin/activate
   ```

6. Install packages
   ```
   pip install -r requirements.txt
   ```
