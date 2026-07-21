"""Canonical economic-benefit scenario contract."""

from src.calculations.furnace import calculate_fuel_gas_penalty


def calculate_cleaning_economic_benefit(cit_gain_c, feed_kbd, energy_factor, gas_price,
                                        cleaning_cost, operating_days=360, decay_factor=0.5):
    gross_day = calculate_fuel_gas_penalty(cit_gain_c, feed_kbd, energy_factor, gas_price)
    annual = gross_day.value * float(operating_days) * float(decay_factor)
    return {
        "gross_saving_thb_year": annual,
        "net_saving_thb_year": annual - float(cleaning_cost),
        "cleaning_cost_thb": float(cleaning_cost),
        "approval_status": "CANDIDATE",
        "data_kind": "CALCULATED",
        "warning": "Scenario estimate; not a guaranteed saving.",
    }
