from ladybug.epw import EPW
from ladybug.datacollection import HourlyContinuousCollection

from .solar_azimuth import solar_azimuth


def solar_azimuth_radians(
    epw: EPW, sun_position: HourlyContinuousCollection = None
) -> HourlyContinuousCollection:
    """Calculate annual hourly solar azimuth angle.

    Args:
        epw (EPW): An EPW object.
        sun_position (HourlyContinuousCollection, optional): A pre-calculated HourlyContinuousCollection of Sun objects. Defaults to None.

    Returns:
        HourlyContinuousCollection: An HourlyContinuousCollection of solar azimuth angles.
    """

    collection = solar_azimuth(epw, sun_position)
    collection = collection.convert_to_unit("radians")

    return collection
