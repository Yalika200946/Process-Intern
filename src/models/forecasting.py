"""Forecast selection that formally defers to persistence when ML lacks skill."""


def forecast_target(candidate_values, persistence_values, candidate_rmse, persistence_rmse):
    use_candidate = candidate_rmse < persistence_rmse
    return {
        "values": list(candidate_values if use_candidate else persistence_values),
        "selected_model": "candidate" if use_candidate else "persistence",
        "candidate_beats_baseline": bool(use_candidate),
        "approval_status": "CANDIDATE",
        "data_kind": "PREDICTED",
        "warning": None if use_candidate else "Candidate model did not beat persistence; baseline used.",
    }

