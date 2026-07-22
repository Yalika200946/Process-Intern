import pytest

from src.calculations.overall_heat_transfer import area_to_m2, calculate_u_from_ua


def test_ua_to_u_conversion_preserves_ua_and_unit():
    r=calculate_u_from_ua(ua_value=100,ua_unit="kW/K",area_value=500,area_unit="m2",
                          area_status="VERIFIED_DESIGN_AREA",f_status="VERIFIED",shell_basis_matches=True)
    assert r["ua_value"]==100 and r["ua_unit"]=="kW/K"
    assert r["u_value"]==pytest.approx(200) and r["u_unit"]=="W/m2/K"


def test_ft2_conversion():
    assert area_to_m2(100,"ft2")==pytest.approx(9.290304)


def test_example_area_is_rejected():
    r=calculate_u_from_ua(ua_value=100,ua_unit="kW/K",area_value=500,area_unit="m2",
                          area_status="EXAMPLE_AREA_ONLY",f_status="VERIFIED",shell_basis_matches=True)
    assert r["u_value"] is None and r["u_status"]=="REJECTED_AREA_EVIDENCE"


def test_ambiguous_hx_area_mapping_is_rejected():
    r=calculate_u_from_ua(ua_value=100,ua_unit="kW/K",area_value=500,area_unit="m2",
                          area_status="MAPPING_AMBIGUOUS",f_status="VERIFIED",shell_basis_matches=True)
    assert r["u_value"] is None and r["u_status"]=="REJECTED_AREA_EVIDENCE"


def test_multi_shell_basis_must_match():
    r=calculate_u_from_ua(ua_value=100,ua_unit="kW/K",area_value=500,area_unit="m2",
                          area_status="VERIFIED_DESIGN_AREA",f_status="VERIFIED",shell_basis_matches=False)
    assert r["u_status"]=="CONFIGURATION_BASIS_MISMATCH"


def test_f_status_propagates_and_blocks_u():
    r=calculate_u_from_ua(ua_value=100,ua_unit="kW/K",area_value=500,area_unit="m2",
                          area_status="VERIFIED_DESIGN_AREA",f_status="ASSUMPTION",shell_basis_matches=True)
    assert r["F_status"]=="ASSUMPTION" and r["u_status"]=="F_FACTOR_NOT_VERIFIED"


def test_ambiguous_unit_is_rejected():
    with pytest.raises(ValueError): area_to_m2(100,"area units")
