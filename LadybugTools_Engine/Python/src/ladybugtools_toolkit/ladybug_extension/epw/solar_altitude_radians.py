from ladybug.epw import EPW
from ladybug.datacollection import HourlyContinuousCollection

from .solar_altitude import solar_altitude


def solar_altitude_radians(
    epw: EPW, sun_position: HourlyContinuousCollection = None
) -> HourlyContinuousCollection:
    """Calculate annual hourly solar altitude angle.

    Args:
        epw (EPW): An EPW object.
        sun_position (HourlyContinuousCollection, optional): A pre-calculated HourlyContinuousCollection of Sun objects. Defaults to None.

    Returns:
        HourlyContinuousCollection: An HourlyContinuousCollection of solar altitude angles.
    """

    collection = solar_altitude(epw, sun_position)
    collection = collection.convert_to_unit("radians")

    return collection
