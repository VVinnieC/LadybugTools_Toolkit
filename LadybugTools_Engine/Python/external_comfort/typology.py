from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
import json
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd
from ladybug.datacollection import AnalysisPeriod, Header, HourlyContinuousCollection
from ladybug.datatype.temperature import WetBulbTemperature
from ladybug.epw import EPW
from ladybug.psychrometrics import wet_bulb_from_db_rh
from ladybug.sunpath import Sunpath
from ladybug_comfort.collection.utci import UTCI
from ladybug_comfort.collection.pmv import PMV
from ladybug_extension.datacollection import from_series, to_series

from external_comfort.encoder import Encoder
from external_comfort.external_comfort import ExternalComfort, ExternalComfortResult, ExternalComfortEncoder
from external_comfort.shelter import Shelter

class TypologyEncoder(Encoder):
    """A JSON encoder for the Typology and TypologyResult classes."""
    def default(self, obj):
        if isinstance(obj, ExternalComfort):
            return obj.to_dict()
        if isinstance(obj, ExternalComfortResult):
            return obj.to_dict()
        if isinstance(obj, Shelter):
            return obj.to_dict()
        if isinstance(obj, Typology):
            return obj.to_dict()
        if isinstance(obj, TypologyResult):
            return obj.to_dict()
        return super(TypologyEncoder, self).default(obj)

@dataclass(frozen=True)
class Typology:
    name: str = field(init=True, repr=True)
    shelters: List[Shelter] = field(init=True, repr=True, default_factory=list)
    evaporative_cooling_effectiveness: float = field(init=True, repr=True, default=0)
    wind_speed_multiplier: float = field(init=True, repr=True, default=1)

    def __post_init__(self) -> Typology:
        if self.shelters is None:
            object.__setattr__(self, "shelters", [])

        if Shelter._overlaps(self.shelters):
            raise ValueError("Shelters overlap")

    def __repr__(self):
        return (
            f"{self.__class__.__name__}"
            f" - {self.name}"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Return this object as a dictionary

        Returns:
            Dict: The dict representation of this object.
        """

        d = {
            "name": self.name,
            "shelters": [i.to_dict() for i in self.shelters],
            "evaporative_cooling_effectiveness": self.evaporative_cooling_effectiveness,
            "wind_speed_multiplier": self.wind_speed_multiplier,
        }
        return d
    
    def to_json(self, file_path: str) -> Path:
        """Write the content of this object to a JSON file

        Returns:
            Path: The path to the newly created JSON file.
        """

        file_path: Path = Path(file_path)
        file_path.parent.mkdir(exist_ok=True, parents=True)

        with open(file_path, "w") as fp:
            json.dump(self.to_dict(), fp, cls=TypologyEncoder, indent=4)

        return file_path


@dataclass(frozen=True)
class TypologyResult:
    typology: Typology = field(init=True, repr=True)
    external_comfort_result: ExternalComfortResult = field(init=True, repr=True)

    dry_bulb_temperature: HourlyContinuousCollection = field(init=False, repr=False)
    relative_humidity: HourlyContinuousCollection = field(init=False, repr=False)
    wind_speed: HourlyContinuousCollection = field(init=False, repr=False)
    mean_radiant_temperature: HourlyContinuousCollection = field(init=False, repr=False)
    universal_thermal_climate_index: HourlyContinuousCollection = field(
        init=False, repr=False
    )
    standard_effective_temperature: HourlyContinuousCollection = field(
        init=False, repr=False
    )

    def __post_init__(self) -> TypologyResult:
        print(f"- Calculating {self.__class__.__name__} - {self.typology.name}")
        dbt_rh = self.evaporatively_cooled_dbt_rh(
            self.external_comfort_result.external_comfort.epw,
            self.typology.evaporative_cooling_effectiveness,
        )
        object.__setattr__(self, "dry_bulb_temperature", dbt_rh["dry_bulb_temperature"])
        object.__setattr__(self, "relative_humidity", dbt_rh["relative_humidity"])
        object.__setattr__(self, "wind_speed", self._wind_speed())
        object.__setattr__(
            self, "mean_radiant_temperature", self._mean_radiant_temperature()
        )
        object.__setattr__(
            self,
            "universal_thermal_climate_index",
            self._universal_thermal_climate_index(),
        )
        # object.__setattr__(
        #     self,
        #     "standard_effective_temperature",
        #     self._standard_effective_temperature(),
        # )

    def _wind_speed(self) -> HourlyContinuousCollection:
        if len(self.typology.shelters) == 0:
            return self.external_comfort_result.external_comfort.epw.wind_speed * self.typology.wind_speed_multiplier
        else:
            collections = []
            for shelter in self.typology.shelters:
                collections.append(
                    to_series(
                        shelter.effective_wind_speed(
                            self.external_comfort_result.external_comfort.epw
                        )
                        * self.typology.wind_speed_multiplier
                    )
                )
            return from_series(
                pd.concat(collections, axis=1).min(axis=1).rename("Wind Speed (m/s)")
            )

    def _sky_visibility(self) -> float:
        """Calculate the proportion of sky visible from a typology with any nuber of shelters.

        Returns:
            float: The proportion of sky visible from the typology.
        """
        unsheltered_proportion = 1
        sheltered_proportion = 0
        for shelter in self.typology.shelters:
            occ = shelter.sky_occluded
            unsheltered_proportion -= occ
            sheltered_proportion += occ * shelter.porosity
        return sheltered_proportion + unsheltered_proportion

    def _annual_hourly_sun_exposure(self) -> List[float]:
        """Return NaN if sun below horizon, and a value between 0-1 for sun-hidden to sun-exposed.

        Returns:
            List[float]: A list of sun visibility values for each hour of the year.
        """

        sunpath = Sunpath.from_location(
            self.external_comfort_result.external_comfort.epw.location
        )
        suns = [sunpath.calculate_sun_from_hoy(i) for i in range(8760)]
        sun_is_up = np.array([True if sun.altitude > 0 else False for sun in suns])

        nans = np.empty(
            len(
                self.external_comfort_result.external_comfort.epw.dry_bulb_temperature
            )
        )
        nans[:] = np.NaN

        if len(self.typology.shelters) == 0:
            return np.where(sun_is_up, 1, nans)

        blocked = []
        for shelter in self.typology.shelters:
            shelter_blocking = shelter.sun_blocked(suns)
            temp = np.where(shelter_blocking, shelter.porosity, nans)
            temp = np.where(np.logical_and(np.isnan(temp), sun_is_up), 1, temp)
            blocked.append(temp)

        return pd.DataFrame(blocked).T.min(axis=1).values.tolist()

    def _mean_radiant_temperature(self) -> HourlyContinuousCollection:
        """Return the effective mean radiant temperature for the given typology.

        Returns:
            HourlyContinuousCollection: An calculated mean radiant temperature based on the shelter configuration for the given typology.
        """

        shaded_mrt = to_series(
            self.external_comfort_result.shaded_mean_radiant_temperature
        )
        unshaded_mrt = to_series(
            self.external_comfort_result.unshaded_mean_radiant_temperature
        )

        sun_exposure = self._annual_hourly_sun_exposure()
        effective_sky_visibility = self._sky_visibility()
        daytime = np.array(
            [
                True if i > 0 else False
                for i in self.external_comfort_result.external_comfort.epw.global_horizontal_radiation
            ]
        )
        mrts = []
        for hour in range(8760):
            if daytime[hour]:
                mrts.append(
                    np.interp(
                        sun_exposure[hour],
                        [0, 1],
                        [shaded_mrt[hour], unshaded_mrt[hour]],
                    )
                )
            else:
                mrts.append(
                    np.interp(
                        effective_sky_visibility,
                        [0, 1],
                        [shaded_mrt[hour], unshaded_mrt[hour]],
                    )
                )

        # Fill any gaps where sun-visible/sun-occluded values are missing, and apply an exponentially weighted moving average to account for transition betwen shaded/unshaded periods.
        mrt_series = pd.Series(
            mrts, index=shaded_mrt.index, name=shaded_mrt.name
        ).interpolate()

        def __smoother(
            series: pd.Series,
            difference_threshold: float = -10,
            transition_window: int = 4,
            ewm_span: float = 1.25,
        ) -> pd.Series:
            """Helper function that adds a decay rate to a time-series for values dropping significantly below the previous values.

            Args:
                series (pd.Series): The series to modify
                difference_threshold (float, optional): The difference between current/prtevious values which class as a "transition". Defaults to -10.
                transition_window (int, optional): The number of values after the "transition" within which an exponentially weighted mean should be applied. Defaults to 4.
                ewm_span (float, optional): The rate of decay. Defaults to 1.25.

            Returns:
                pd.Series: A modified series
            """
            # Find periods of major transition (where values drop signifigantly from loss of radiation mainly)
            transition_index = series.diff() < difference_threshold

            # Get boolean index for all periods within window from the transition indices
            ewm_mask = []
            n = 0
            for i in transition_index:
                if i:
                    n = 0
                if n < transition_window:
                    ewm_mask.append(True)
                else:
                    ewm_mask.append(False)
                n += 1

            # Run an EWM to get the smoothed values following changes to values
            ewm_smoothed: pd.Series = series.ewm(span=ewm_span).mean()

            # Choose from ewm or original values based on ewm mask
            new_series = ewm_smoothed.where(ewm_mask, series)
            return new_series

        mrt_series = __smoother(
            mrt_series, difference_threshold=-10, transition_window=4, ewm_span=1.25
        )

        return from_series(mrt_series)

    def _universal_thermal_climate_index(self) -> HourlyContinuousCollection:
        """Return the effective UTCI for the given typology.

        Returns:
            HourlyContinuousCollection: The calculated UTCI based on the shelter configuration for the given typology.
        """

        return UTCI(
            air_temperature=self.dry_bulb_temperature,
            rel_humidity=self.relative_humidity,
            rad_temperature=self.mean_radiant_temperature,
            wind_speed=self.wind_speed,
        ).universal_thermal_climate_index

    def _standard_effective_temperature(self) -> HourlyContinuousCollection:
        """Return the standard effective temperature for the given typology.

        Returns:
            HourlyContinuousCollection: The calculated standard effective temperature based on the shelter configuration for the given typology.
        """        

        return PMV(
            air_temperature=self.dry_bulb_temperature,
            rel_humidity=self.relative_humidity,
            rad_temperature=self.mean_radiant_temperature,
            air_speed=self.wind_speed,
            met_rate=1.1,
            clo_value=0.7,
            external_work=0,
        ).standard_effective_temperature
    
    def to_dataframe(self, include_external_comfort_results: bool = True) -> pd.DataFrame:
        """Create a dataframe from the typology results.

        Args:
            include_external_comfort_results (bool, optional): Whether to include the external comfort results in the dataframe. Defaults to True.

        Returns:
            pd.DataFrame: A dataframe containing the typology results.
        """        

        attributes = [
            "dry_bulb_temperature",
            "relative_humidity",
            "wind_speed",
            "mean_radiant_temperature",
            "universal_thermal_climate_index",
        ]
        series: List[pd.Series] = []
        for attribute in attributes:
            series.append(to_series(getattr(self, attribute)))
        df = pd.concat(series, axis=1, keys=[f"{self.__class__.__name__} - {i}" for i in attributes])

        if include_external_comfort_results:
            df = pd.concat([df, self.external_comfort_result.to_dataframe()], axis=1)
        
        return df

    def to_dict(self) -> Dict[str, Any]:
        """Return this object as a dictionary

        Returns:
            Dict: The dict representation of this object.
        """

        attributes = [
            "typology",
            "external_comfort_result",
            "dry_bulb_temperature",
            "relative_humidity",
            "wind_speed",
            "mean_radiant_temperature",
            "universal_thermal_climate_index",
            # "standard_effective_temperature",
        ]
        return {attribute: getattr(self, attribute) for attribute in attributes}  
    
    def to_json(self, file_path: str) -> Path:
        """Write the content of this object to a JSON file

        Returns:
            Path: The path to the newly created JSON file.
        """

        file_path: Path = Path(file_path)
        file_path.parent.mkdir(exist_ok=True, parents=True)

        with open(file_path, "w") as fp:
            json.dump(self.to_dict(), fp, cls=TypologyEncoder, indent=4)

        return file_path



    @staticmethod
    def evaporatively_cooled_dbt_rh(
        epw: EPW, evaporative_cooling_effectiveness: float = 0.3
    ) -> Dict[str, HourlyContinuousCollection]:
        """Calculate the effective DBT and RH considering effects of evaporative cooling.

        Args:
            epw (EPW): A ladybug EPW object.
            evaporative_cooling_effectiveness (float, optional): The proportion of difference betwen DBT and WBT by which to adjust DBT. Defaults to 0.3 which equates to 30% effective evaporative cooling, roughly that of Misting.

        Returns:
            HourlyContinuousCollection: An adjusted dry-bulb temperature collection with evaporative cooling factored in.
        """

        dbt: HourlyContinuousCollection = copy.deepcopy(epw.dry_bulb_temperature)
        wbt = HourlyContinuousCollection(
            header=Header(
                data_type=WetBulbTemperature(),
                unit="C",
                analysis_period=AnalysisPeriod(),
            ),
            values=[
                wet_bulb_from_db_rh(
                    epw.dry_bulb_temperature[i],
                    epw.relative_humidity[i],
                    epw.atmospheric_station_pressure[i],
                )
                for i in range(8760)
            ],
        )
        dbt_adjusted = dbt - ((dbt - wbt) * evaporative_cooling_effectiveness)
        dbt_adjusted.header.metadata = {
            **dbt.header.metadata,
            **{
                "evaporative_cooling": f"{evaporative_cooling_effectiveness:0.0%}",
                "description": f"Evaporatively Cooled Dry Bulb Temperature (C) - {evaporative_cooling_effectiveness:0.0%} effective",
            },
        }

        rh: HourlyContinuousCollection = copy.deepcopy(epw.relative_humidity)
        rh_adjusted = (rh * (1 - evaporative_cooling_effectiveness)) + (
            evaporative_cooling_effectiveness * 100
        )
        rh_adjusted.header.metadata = {
            **rh.header.metadata,
            **{
                "evaporative_cooling": f"{evaporative_cooling_effectiveness:0.0%}",
                "description": f"Evaporatively Cooled Relative Humidity (%) - {evaporative_cooling_effectiveness:0.0%} effective",
            },
        }

        return {"dry_bulb_temperature": dbt_adjusted, "relative_humidity": rh_adjusted}
    
    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}"
            f" [{self.external_comfort_result.external_comfort.model.identifier}] - {self.typology.name}"
        )

class Typologies(Enum):
    Openfield = Typology(
        name="Openfield",
        evaporative_cooling_effectiveness=0,
        shelters=[],
        wind_speed_multiplier=1,
    )
    Enclosed = Typology(
        name="Enclosed",
        evaporative_cooling_effectiveness=0,
        shelters=[Shelter(altitude_range=[0, 90], azimuth_range=[0, 360], porosity=0)],
        wind_speed_multiplier=1,
    )
    PorousEnclosure = Typology(
        name="Porous enclosure",
        evaporative_cooling_effectiveness=0,
        shelters=[
            Shelter(altitude_range=[0, 90], azimuth_range=[0, 360], porosity=0.5)
        ],
        wind_speed_multiplier=1,
    )
    SkyShelter = Typology(
        name="Sky-shelter",
        evaporative_cooling_effectiveness=0,
        shelters=[Shelter(altitude_range=[45, 90], azimuth_range=[0, 360], porosity=0)],
        wind_speed_multiplier=1,
    )
    FrittedSkyShelter = Typology(
        name="Fritted sky-shelter",
        evaporative_cooling_effectiveness=0,
        shelters=[
            Shelter(altitude_range=[45, 90], azimuth_range=[0, 360], porosity=0.5),
        ],
        wind_speed_multiplier=1,
    )
    NearWater = Typology(
        name="Near water",
        evaporative_cooling_effectiveness=0.15,
        shelters=[
            Shelter(altitude_range=[0, 0], azimuth_range=[0, 0], porosity=1),
        ],
        wind_speed_multiplier=1.2,
    )
    Misting = Typology(
        name="Misting",
        evaporative_cooling_effectiveness=0.3,
        shelters=[
            Shelter(altitude_range=[0, 0], azimuth_range=[0, 0], porosity=1),
        ],
        wind_speed_multiplier=0.5,
    )
    PDEC = Typology(
        name="PDEC",
        evaporative_cooling_effectiveness=0.7,
        shelters=[
            Shelter(altitude_range=[0, 0], azimuth_range=[0, 0], porosity=1),
        ],
        wind_speed_multiplier=0.5,
    )
    NorthShelter = Typology(
        name="North shelter",
        evaporative_cooling_effectiveness=0.0,
        shelters=[
            Shelter(altitude_range=[0, 70], azimuth_range=[337.5, 22.5], porosity=0),
        ],
        wind_speed_multiplier=1,
    )
    NortheastShelter = Typology(
        name="Northeast shelter",
        evaporative_cooling_effectiveness=0.0,
        shelters=[
            Shelter(altitude_range=[0, 70], azimuth_range=[22.5, 67.5], porosity=0),
        ],
        wind_speed_multiplier=1,
    )
    EastShelter = Typology(
        name="East shelter",
        evaporative_cooling_effectiveness=0.0,
        shelters=[
            Shelter(altitude_range=[0, 70], azimuth_range=[67.5, 112.5], porosity=0),
        ],
        wind_speed_multiplier=1,
    )
    SoutheastShelter = Typology(
        name="Southeast shelter",
        evaporative_cooling_effectiveness=0.0,
        shelters=[
            Shelter(altitude_range=[0, 70], azimuth_range=[112.5, 157.5], porosity=0),
        ],
        wind_speed_multiplier=1,
    )
    SouthShelter = Typology(
        name="South shelter",
        evaporative_cooling_effectiveness=0.0,
        shelters=[
            Shelter(altitude_range=[0, 70], azimuth_range=[157.5, 202.5], porosity=0),
        ],
        wind_speed_multiplier=1,
    )
    SouthwestShelter = Typology(
        name="Southwest shelter",
        evaporative_cooling_effectiveness=0.0,
        shelters=[
            Shelter(altitude_range=[0, 70], azimuth_range=[202.5, 247.5], porosity=0),
        ],
        wind_speed_multiplier=1,
    )
    WestShelter = Typology(
        name="West shelter",
        evaporative_cooling_effectiveness=0.0,
        shelters=[
            Shelter(altitude_range=[0, 70], azimuth_range=[247.5, 292.5], porosity=0),
        ],
        wind_speed_multiplier=1,
    )
    NorthwestShelter = Typology(
        name="Northwest shelter",
        evaporative_cooling_effectiveness=0.0,
        shelters=[
            Shelter(altitude_range=[0, 70], azimuth_range=[292.5, 337.5], porosity=0),
        ],
        wind_speed_multiplier=1,
    )
    NorthShelterWithCanopy = Typology(
        name="North shelter (with canopy)",
        evaporative_cooling_effectiveness=0.0,
        shelters=[
            Shelter(altitude_range=[0, 90], azimuth_range=[337.5, 22.5], porosity=0),
        ],
        wind_speed_multiplier=1,
    )
    NortheastShelterWithCanopy = Typology(
        name="Northeast shelter (with canopy)",
        evaporative_cooling_effectiveness=0.0,
        shelters=[
            Shelter(altitude_range=[0, 90], azimuth_range=[22.5, 67.5], porosity=0),
        ],
        wind_speed_multiplier=1,
    )
    EastShelterWithCanopy = Typology(
        name="East shelter (with canopy)",
        evaporative_cooling_effectiveness=0.0,
        shelters=[
            Shelter(altitude_range=[0, 90], azimuth_range=[67.5, 112.5], porosity=0),
        ],
        wind_speed_multiplier=1,
    )
    SoutheastShelterWithCanopy = Typology(
        name="Southeast shelter (with canopy)",
        evaporative_cooling_effectiveness=0.0,
        shelters=[
            Shelter(altitude_range=[0, 90], azimuth_range=[112.5, 157.5], porosity=0),
        ],
        wind_speed_multiplier=1,
    )
    SouthShelterWithCanopy = Typology(
        name="South shelter (with canopy)",
        evaporative_cooling_effectiveness=0.0,
        shelters=[
            Shelter(altitude_range=[0, 90], azimuth_range=[157.5, 202.5], porosity=0),
        ],
        wind_speed_multiplier=1,
    )
    SouthwestShelterWithCanopy = Typology(
        name="Southwest shelter (with canopy)",
        evaporative_cooling_effectiveness=0.0,
        shelters=[
            Shelter(altitude_range=[0, 90], azimuth_range=[202.5, 247.5], porosity=0),
        ],
        wind_speed_multiplier=1,
    )
    WestShelterWithCanopy = Typology(
        name="West shelter (with canopy)",
        evaporative_cooling_effectiveness=0.0,
        shelters=[
            Shelter(altitude_range=[0, 90], azimuth_range=[247.5, 292.5], porosity=0),
        ],
        wind_speed_multiplier=1,
    )
    NorthwestShelterWithCanopy = Typology(
        name="Northwest shelter (with canopy)",
        evaporative_cooling_effectiveness=0.0,
        shelters=[
            Shelter(altitude_range=[0, 90], azimuth_range=[292.5, 337.5], porosity=0),
        ],
        wind_speed_multiplier=1,
    )
    EastWestShelter = Typology(
        name="East-west shelter",
        evaporative_cooling_effectiveness=0.0,
        shelters=[
            Shelter(altitude_range=[0, 70], azimuth_range=[67.5, 112.5], porosity=0),
            Shelter(altitude_range=[0, 70], azimuth_range=[247.5, 292.5], porosity=0),
        ],
        wind_speed_multiplier=1,
    )
    EastWestShelterWithCanopy = Typology(
        name="East-west shelter (with canopy)",
        evaporative_cooling_effectiveness=0.0,
        shelters=[
            Shelter(altitude_range=[0, 90], azimuth_range=[67.5, 112.5], porosity=0),
            Shelter(altitude_range=[0, 90], azimuth_range=[247.5, 292.5], porosity=0),
        ],
        wind_speed_multiplier=1,
    )
    
TYPOLOGIES: Dict[str, Typology] = {
    "Openfield": Typology(
        name="Openfield",
        evaporative_cooling_effectiveness=0,
        shelters=[],
        wind_speed_multiplier=1,
    ),
    "Enclosed": Typology(
        name="Enclosed",
        evaporative_cooling_effectiveness=0,
        shelters=[Shelter(altitude_range=[0, 90], azimuth_range=[0, 360], porosity=0)],
        wind_speed_multiplier=1,
    ),
    "PorousEnclosure": Typology(
        name="Porous enclosure",
        evaporative_cooling_effectiveness=0,
        shelters=[
            Shelter(altitude_range=[0, 90], azimuth_range=[0, 360], porosity=0.5)
        ],
        wind_speed_multiplier=1,
    ),
    "SkyShelter": Typology(
        name="Sky-shelter",
        evaporative_cooling_effectiveness=0,
        shelters=[Shelter(altitude_range=[45, 90], azimuth_range=[0, 360], porosity=0)],
        wind_speed_multiplier=1,
    ),
    "FrittedSkyShelter": Typology(
        name="Fritted sky-shelter",
        evaporative_cooling_effectiveness=0,
        shelters=[
            Shelter(altitude_range=[45, 90], azimuth_range=[0, 360], porosity=0.5),
        ],
        wind_speed_multiplier=1,
    ),
    "NearWater": Typology(
        name="Near water",
        evaporative_cooling_effectiveness=0.15,
        shelters=[
            Shelter(altitude_range=[0, 0], azimuth_range=[0, 0], porosity=1),
        ],
        wind_speed_multiplier=1.2,
    ),
    "Misting": Typology(
        name="Misting",
        evaporative_cooling_effectiveness=0.3,
        shelters=[
            Shelter(altitude_range=[0, 0], azimuth_range=[0, 0], porosity=1),
        ],
        wind_speed_multiplier=0.5,
    ),
    "PDEC": Typology(
        name="PDEC",
        evaporative_cooling_effectiveness=0.7,
        shelters=[
            Shelter(altitude_range=[0, 0], azimuth_range=[0, 0], porosity=1),
        ],
        wind_speed_multiplier=0.5,
    ),
    "NorthShelter": Typology(
        name="North shelter",
        evaporative_cooling_effectiveness=0.0,
        shelters=[
            Shelter(altitude_range=[0, 70], azimuth_range=[337.5, 22.5], porosity=0),
        ],
        wind_speed_multiplier=1,
    ),
    "NortheastShelter": Typology(
        name="Northeast shelter",
        evaporative_cooling_effectiveness=0.0,
        shelters=[
            Shelter(altitude_range=[0, 70], azimuth_range=[22.5, 67.5], porosity=0),
        ],
        wind_speed_multiplier=1,
    ),
    "EastShelter": Typology(
        name="East shelter",
        evaporative_cooling_effectiveness=0.0,
        shelters=[
            Shelter(altitude_range=[0, 70], azimuth_range=[67.5, 112.5], porosity=0),
        ],
        wind_speed_multiplier=1,
    ),
    "SoutheastShelter": Typology(
        name="Southeast shelter",
        evaporative_cooling_effectiveness=0.0,
        shelters=[
            Shelter(altitude_range=[0, 70], azimuth_range=[112.5, 157.5], porosity=0),
        ],
        wind_speed_multiplier=1,
    ),
    "SouthShelter": Typology(
        name="South shelter",
        evaporative_cooling_effectiveness=0.0,
        shelters=[
            Shelter(altitude_range=[0, 70], azimuth_range=[157.5, 202.5], porosity=0),
        ],
        wind_speed_multiplier=1,
    ),
    "SouthwestShelter": Typology(
        name="Southwest shelter",
        evaporative_cooling_effectiveness=0.0,
        shelters=[
            Shelter(altitude_range=[0, 70], azimuth_range=[202.5, 247.5], porosity=0),
        ],
        wind_speed_multiplier=1,
    ),
    "WestShelter": Typology(
        name="West shelter",
        evaporative_cooling_effectiveness=0.0,
        shelters=[
            Shelter(altitude_range=[0, 70], azimuth_range=[247.5, 292.5], porosity=0),
        ],
        wind_speed_multiplier=1,
    ),
    "NorthwestShelter": Typology(
        name="Northwest shelter",
        evaporative_cooling_effectiveness=0.0,
        shelters=[
            Shelter(altitude_range=[0, 70], azimuth_range=[292.5, 337.5], porosity=0),
        ],
        wind_speed_multiplier=1,
    ),
    "NorthShelterWithCanopy": Typology(
        name="North shelter (with canopy)",
        evaporative_cooling_effectiveness=0.0,
        shelters=[
            Shelter(altitude_range=[0, 90], azimuth_range=[337.5, 22.5], porosity=0),
        ],
        wind_speed_multiplier=1,
    ),
    "NortheastShelterWithCanopy": Typology(
        name="Northeast shelter (with canopy)",
        evaporative_cooling_effectiveness=0.0,
        shelters=[
            Shelter(altitude_range=[0, 90], azimuth_range=[22.5, 67.5], porosity=0),
        ],
        wind_speed_multiplier=1,
    ),
    "EastShelterWithCanopy": Typology(
        name="East shelter (with canopy)",
        evaporative_cooling_effectiveness=0.0,
        shelters=[
            Shelter(altitude_range=[0, 90], azimuth_range=[67.5, 112.5], porosity=0),
        ],
        wind_speed_multiplier=1,
    ),
    "SoutheastShelterWithCanopy": Typology(
        name="Southeast shelter (with canopy)",
        evaporative_cooling_effectiveness=0.0,
        shelters=[
            Shelter(altitude_range=[0, 90], azimuth_range=[112.5, 157.5], porosity=0),
        ],
        wind_speed_multiplier=1,
    ),
    "SouthShelterWithCanopy": Typology(
        name="South shelter (with canopy)",
        evaporative_cooling_effectiveness=0.0,
        shelters=[
            Shelter(altitude_range=[0, 90], azimuth_range=[157.5, 202.5], porosity=0),
        ],
        wind_speed_multiplier=1,
    ),
    "SouthwestShelterWithCanopy": Typology(
        name="Southwest shelter (with canopy)",
        evaporative_cooling_effectiveness=0.0,
        shelters=[
            Shelter(altitude_range=[0, 90], azimuth_range=[202.5, 247.5], porosity=0),
        ],
        wind_speed_multiplier=1,
    ),
    "WestShelterWithCanopy": Typology(
        name="West shelter (with canopy)",
        evaporative_cooling_effectiveness=0.0,
        shelters=[
            Shelter(altitude_range=[0, 90], azimuth_range=[247.5, 292.5], porosity=0),
        ],
        wind_speed_multiplier=1,
    ),
    "NorthwestShelterWithCanopy": Typology(
        name="Northwest shelter (with canopy)",
        evaporative_cooling_effectiveness=0.0,
        shelters=[
            Shelter(altitude_range=[0, 90], azimuth_range=[292.5, 337.5], porosity=0),
        ],
        wind_speed_multiplier=1,
    ),
    "EastWestShelter": Typology(
        name="East-west shelter",
        evaporative_cooling_effectiveness=0.0,
        shelters=[
            Shelter(altitude_range=[0, 70], azimuth_range=[67.5, 112.5], porosity=0),
            Shelter(altitude_range=[0, 70], azimuth_range=[247.5, 292.5], porosity=0),
        ],
        wind_speed_multiplier=1,
    ),
    "EastWestShelterWithCanopy": Typology(
        name="East-west shelter (with canopy)",
        evaporative_cooling_effectiveness=0.0,
        shelters=[
            Shelter(altitude_range=[0, 90], azimuth_range=[67.5, 112.5], porosity=0),
            Shelter(altitude_range=[0, 90], azimuth_range=[247.5, 292.5], porosity=0),
        ],
        wind_speed_multiplier=1,
    ),
}


def calculate_typology_results(
    typologies: List[Typology], external_comfort_result: ExternalComfortResult
) -> List[TypologyResult]:
    """Create a set of results for a set of typologies.

    Args:
        external_comfort_result (ExternalComfortResult): An ExternalComfortResult object containing the results of an external comfort simulation.
        typologies (List[Typology]): A list of Typology objects to be evaluated.

    Returns:
        List[TypologyResult]: A list of typology result objects.
    """

    if not all(isinstance(x, Typology) for x in typologies):
        raise ValueError("Not all elements in list given are Typology objects.")

    results = []
    with ThreadPoolExecutor() as executor:
        for typology in typologies:
            results.append(
                executor.submit(TypologyResult, typology, external_comfort_result)
            )

    typology_results = []
    for result in results:
        typology_results.append(result.result())

    return typology_results
