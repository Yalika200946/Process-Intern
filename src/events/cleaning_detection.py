"""Candidate cleaning-event evidence scoring without claiming confirmation."""


def score_cleaning_event(*, tam_record=False, maintenance_record=False, stable_recovery=False,
                         configuration_change=False, process_change=False):
    score = 0
    score += 5 if tam_record else 0
    score += 5 if maintenance_record else 0
    score += 2 if stable_recovery else 0
    score += 1 if configuration_change else 0
    score -= 3 if process_change else 0
    status = "CONFIRMED_TAM" if tam_record else "SWITCH_CANDIDATE" if configuration_change else "UNEXPLAINED_RECOVERY"
    return {
        "score": score, "event_status": status,
        "confirmed_clean": bool(maintenance_record and stable_recovery),
        "approval_status": "CANDIDATE",
        "warning": None if maintenance_record else "No authoritative maintenance record; event is not confirmed clean.",
    }

