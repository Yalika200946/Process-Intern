import math
from pipeline.analyze_f101_consequence import furnace_duty_kw

def test_furnace_duty_unit_consistency():
    assert furnace_duty_kw(100,2.5,250,350)==25000

def test_furnace_duty_rejects_invalid_inputs():
    assert math.isnan(furnace_duty_kw(0,2.5,250,350))
    assert math.isnan(furnace_duty_kw(100,2.5,350,250))
