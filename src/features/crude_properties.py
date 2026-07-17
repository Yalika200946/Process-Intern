"""
Shared crude physical-property correlations (Cp, density) for computing HX duty (Q).

Single source of truth for the fouling-feature pipeline (notebooks/02_feature_engineering.
ipynb) and the CIT-model feature builder (src/features/heat_duty.py, was notebooks/cpht_features.py) — these previously used
TWO different formulas for the same physical quantity (a fixed Cp=2.2 kJ/kg.K / rho=850 kg/m3
default in cpht_features.py vs. this temperature- and SG-dependent correlation in notebook
02), with no cross-check between them, so the "duty" each pipeline computed for the same HX at
the same timestamp could quietly disagree. Both now call this one function.
"""
import numpy as np


def cp_rho_crude(t_avg, SG):
    """Temperature- and SG-dependent crude Cp [kJ/kg.K] and density [kg/m3] at t_avg [degC].

    Cp: linear correlation in temperature, corrected by 1/sqrt(SG) (Watson & Nelson form).
    Density: petroleum thermal-expansion correlation (ASTM D1250/Rackett-style), referenced
    to the 15.6 degC (60 degF) density implied by SG at 15.6 degC.
    """
    cp = (1.685 + 0.00339 * t_avg) / np.sqrt(SG)
    rho_156 = SG * 999.016
    alpha = 613.9723 / rho_156 ** 2
    rho_t = rho_156 * np.exp(-alpha * (t_avg - 15.6) * (1 + 0.8 * alpha * (t_avg - 15.6)))
    return cp, rho_t
