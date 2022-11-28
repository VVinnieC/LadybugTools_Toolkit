from __future__ import annotations

from copy import copy
from typing import Union

import pandas as pd
from ladybug.datacollection import HourlyContinuousCollection

from ...ladybug_extension.datacollection import from_series
from ..external_comfort import ExternalComfort, SimulationResult, Typology


class PointMitigation:
    def __init__(
        self,
        simulation_result: SimulationResult,
        point_dbt: Union[pd.Series, HourlyContinuousCollection],
        point_mrt: Union[pd.Series, HourlyContinuousCollection],
        point_rh: Union[pd.Series, HourlyContinuousCollection],
        point_ws: Union[pd.Series, HourlyContinuousCollection],
    ) -> PointMitigation:
        self._point_dbt = (
            point_dbt
            if isinstance(point_dbt, HourlyContinuousCollection)
            else from_series(point_dbt)
        )
        self._point_mrt = (
            point_mrt
            if isinstance(point_mrt, HourlyContinuousCollection)
            else from_series(point_mrt)
        )
        self._point_rh = (
            point_rh
            if isinstance(point_rh, HourlyContinuousCollection)
            else from_series(point_rh)
        )
        self._point_ws = (
            point_ws
            if isinstance(point_ws, HourlyContinuousCollection)
            else from_series(point_ws)
        )

        # adjust values in sim res to contain values from point location
        sim_res = copy(simulation_result)
        sim_res.unshaded_mean_radiant_temperature = self._point_mrt
        setattr(getattr(sim_res.epw, "wind_speed"), "values", self._point_ws.values)
        setattr(
            getattr(sim_res.epw, "relative_humidity"), "values", self._point_rh.values
        )
        setattr(
            getattr(sim_res.epw, "dry_bulb_temperature"),
            "values",
            self._point_dbt.values,
        )
        self.simulation_result = sim_res

    def __repr__(self):
        return f"{self.__class__.__name__}"

    def apply_mitigation(self, typology: Typology) -> ExternalComfort:
        """_"""
        return ExternalComfort(self.simulation_result, typology)