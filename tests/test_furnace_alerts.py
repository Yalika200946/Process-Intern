"""
Regression tests for pipeline/cleaning_scheduler_network.furnace_current_state_alerts and
export_cleaning_history.event_confidence -- both added 2026-07-16 with no prior test
coverage at all (new logic, not a gap in previously-untested old code).
"""
import cleaning_scheduler_network as sched
import export_cleaning_history as ech


def _topo(furnace=None, passes=None):
    return {"furnace": furnace or [], "passes": passes or []}


def _furnace_tag(key, value, limit, band, advice_hi="hi advice", advice_lo="lo advice"):
    return dict(key=key, name=key, value=value, unit="unit", limit=limit, band=band,
                advice_hi=advice_hi, advice_lo=advice_lo, limit_assumed=True)


class TestFurnaceCurrentStateAlerts:
    def test_value_inside_normal_band_produces_no_alert(self):
        topo = _topo(furnace=[_furnace_tag("COT", 340.0, 345, [335, 338, 342, 345])])
        result = sched.furnace_current_state_alerts(topo)
        assert result["alerts"] == []

    def test_value_in_critical_high_band_is_flagged_critical(self):
        topo = _topo(furnace=[_furnace_tag("COT", 346.0, 345, [335, 338, 342, 345])])
        result = sched.furnace_current_state_alerts(topo)
        assert len(result["alerts"]) == 1
        assert result["alerts"][0]["severity"] == "critical"
        assert result["alerts"][0]["advice"] == "hi advice"

    def test_value_in_critical_low_band_uses_advice_lo(self):
        topo = _topo(furnace=[_furnace_tag("O2", 1.0, 4.5, [1.5, 2.0, 3.5, 4.5])])
        result = sched.furnace_current_state_alerts(topo)
        assert len(result["alerts"]) == 1
        assert result["alerts"][0]["severity"] == "critical"
        assert result["alerts"][0]["advice"] == "lo advice"

    def test_value_in_warning_band_is_flagged_warning_not_critical(self):
        topo = _topo(furnace=[_furnace_tag("STACK", 355.0, 380, [0, 0, 350, 380])])
        result = sched.furnace_current_state_alerts(topo)
        assert len(result["alerts"]) == 1
        assert result["alerts"][0]["severity"] == "warning"

    def test_every_pass_over_alarm_is_flagged_not_just_worst(self):
        """Regression test for the bug caught during development: the first version only
        flagged the single worst pass, silently dropping other passes that were ALSO over
        alarm (observed on real data: passes 1 and 2 both over alarm simultaneously)."""
        passes = [
            {"pass": 1, "skin_val": 401.0, "skin_alarm": 400.0},
            {"pass": 2, "skin_val": 450.0, "skin_alarm": 400.0},
            {"pass": 3, "skin_val": 390.0, "skin_alarm": 400.0},
        ]
        result = sched.furnace_current_state_alerts(_topo(passes=passes))
        tube_alerts = [a for a in result["alerts"] if a["key"].startswith("TUBE_SKIN_PASS")]
        flagged = {a["key"] for a in tube_alerts}
        assert flagged == {"TUBE_SKIN_PASS1", "TUBE_SKIN_PASS2"}

    def test_worst_pass_is_the_lowest_headroom(self):
        passes = [{"pass": 1, "skin_val": 395.0, "skin_alarm": 400.0},
                  {"pass": 2, "skin_val": 450.0, "skin_alarm": 400.0}]
        result = sched.furnace_current_state_alerts(_topo(passes=passes))
        assert result["worst_pass"]["pass_no"] == 2
        assert result["worst_pass"]["over_alarm"] is True

    def test_missing_topo_data_does_not_crash(self):
        result = sched.furnace_current_state_alerts({})
        assert result["alerts"] == []
        assert result["worst_pass"] is None


class TestEventConfidence:
    def test_tam_is_always_confirmed(self):
        assert ech.event_confidence("TAM", u_recovered=None) == "Confirmed"
        assert ech.event_confidence("TAM", u_recovered=-0.5) == "Confirmed"

    def test_switch_with_positive_recovery_is_probable(self):
        assert ech.event_confidence("SWITCH", u_recovered=0.3) == "Probable"

    def test_switch_with_negligible_or_negative_recovery_is_possible(self):
        assert ech.event_confidence("SWITCH", u_recovered=0.0) == "Possible"
        assert ech.event_confidence("SWITCH", u_recovered=-0.05) == "Possible"

    def test_switch_with_no_data_is_uncertain(self):
        assert ech.event_confidence("SWITCH", u_recovered=None) == "Uncertain"
