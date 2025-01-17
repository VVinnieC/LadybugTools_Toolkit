from ladybug.epw import EPW
from ladybugtools_toolkit.external_comfort.ground_temperature import (
    ground_temperature_at_depth,
    hourly_ground_temperature,
    monthly_ground_temperature,
)

from .. import EPW_FILE

EPW_OBJ = EPW(EPW_FILE)


def test_ground_temperature_at_depth():
    """_"""
    assert ground_temperature_at_depth(EPW_OBJ, 0.5).average == 10.108297296260833


def test_hourly_ground_temperature():
    """_"""
    hourly_ground_temperature(EPW_OBJ)


def test_monthly_ground_temperature():
    """_"""
    monthly_ground_temperature(EPW_OBJ)
