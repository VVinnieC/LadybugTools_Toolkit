import sys

sys.path.insert(0, r"C:\ProgramData\BHoM\Extensions\PythonCode\LadybugTools_Toolkit")

import pandas as pd
from ladybug.datacollection import (HourlyContinuousCollection,
                                    MonthlyCollection)
from ladybug_extension.datacollection.to_series import to_series


def to_hourly(
    collection: MonthlyCollection, method: str = None
) -> HourlyContinuousCollection:
    """Resample a Ladybug MonthlyContinuousCollection object into a Ladybug HourlyContinuousCollection object.

    Args:
        method (str): The method to use for annualizing the monthly values.

    Returns:
        HourlyContinuousCollection: A Ladybug HourlyContinuousCollection object.
    """

    if method is None:
        method = "smooth"

    interpolation_methods = {
        "smooth": "quadratic",
        "step": "pad",
        "linear": "linear",
    }

    series = to_series(collection)
    annual_hourly_index = pd.date_range(
        f"{series.index[0].year}-01-01", periods=8760, freq="H"
    )
    series_annual = series.reindex(annual_hourly_index)
    series_annual[series_annual.index[-1]] = series_annual[series_annual.index[0]]

    try:
        return HourlyContinuousCollection(
            header=collection.header,
            values=series_annual.interpolate(
                method=interpolation_methods[method]
            ).values,
        )
    except KeyError as e:
        raise e