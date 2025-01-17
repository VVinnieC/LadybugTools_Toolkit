from __future__ import annotations

import base64
import colorsys
import contextlib
import copy
import io
import json
import math
import re
import urllib.request
import warnings
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from ladybug.datatype.temperature import WetBulbTemperature
from ladybug.epw import (EPW, AnalysisPeriod, HourlyContinuousCollection,
                         Location)
from ladybug.psychrometrics import wet_bulb_from_db_rh
from ladybug.skymodel import (calc_horizontal_infrared, calc_sky_temperature,
                              estimate_illuminance_from_irradiance,
                              get_extra_radiation, zhang_huang_solar,
                              zhang_huang_solar_split)
from ladybug.sunpath import Sunpath
from matplotlib.colors import cnames, colorConverter, to_rgb
from matplotlib.figure import Figure
from matplotlib.tri.triangulation import Triangulation
from PIL import Image
from scipy.stats import exponweib
from tqdm import tqdm


def relative_luminance(color: Any):
    """Calculate the relative luminance of a color according to W3C standards

    Args:

    color : matplotlib color or sequence of matplotlib colors - Hex code,
    rgb-tuple, or html color name.
    Returns
    -------
    luminance : float(s) between 0 and 1
    """
    rgb = colorConverter.to_rgba_array(color)[:, :3]
    rgb = np.where(rgb <= 0.03928, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    lum = rgb.dot([0.2126, 0.7152, 0.0722])
    try:
        return lum.item()
    except ValueError:
        return lum


def contrasting_color(color: Any):
    """Calculate the contrasting color for a given color.

    Args:
        color (Any): matplotlib color or sequence of matplotlib colors - Hex code,
        rgb-tuple, or html color name.
    Returns:
        str: String code of the contrasting color.
    """
    return ".15" if relative_luminance(color) > 0.408 else "w"


def default_analysis_periods() -> List[AnalysisPeriod]:
    """A set of generic Analysis Period objects, keyed by name."""
    f = io.StringIO()
    with contextlib.redirect_stdout(f):
        aps = [
            AnalysisPeriod(),
            AnalysisPeriod(st_hour=5, end_hour=12, timestep=1),
            AnalysisPeriod(st_hour=12, end_hour=17, timestep=1),
            AnalysisPeriod(st_hour=17, end_hour=21, timestep=1),
            AnalysisPeriod(st_hour=21, end_hour=5, timestep=1),
        ]

    return aps


def animation(
    image_files: List[Union[str, Path]],
    output_gif: Union[str, Path],
    ms_per_image: int = 333,
) -> Path:
    """Create an animated gif from a set of images.

    Args:
        image_files (List[Union[str, Path]]):
            A list of image files.
        output_gif (Union[str, Path]):
            The output gif file to be created.
        ms_per_image (int, optional):
            NUmber of milliseconds per image. Default is 333, for 3 images per second.

    Returns:
        Path:
            The animated gif.

    """

    image_files = [Path(i) for i in image_files]

    images = [Image.open(i) for i in image_files]

    # create white background
    background = Image.new("RGBA", images[0].size, (255, 255, 255))

    images = [Image.alpha_composite(background, i) for i in images]

    images[0].save(
        output_gif,
        save_all=True,
        append_images=images[1:],
        optimize=False,
        duration=ms_per_image,
        loop=0,
    )

    return output_gif


def chunks(lst: List[Any], chunksize: int):
    """Partition an iterable into lists of lenght "chunksize"."""
    for i in range(0, len(lst), chunksize):
        yield lst[i : i + chunksize]


def scrape_weather(
    station: str,
    start_date: str = "1970-01-01",
    end_date: str = None,
    interpolate: bool = False,
    resample: bool = False,
) -> pd.DataFrame:
    """Scrape historic data from global airport weather stations using their ICAO codes
        (https://en.wikipedia.org/wiki/List_of_airports_by_IATA_and_ICAO_code)

    Args:
        station (str):
            Airport ICAO code.
        start_date (str, optional):
            Date from which records will be searched. Defaults to "1970-01-01".
        end_date (str, optional):
            Date until which records will be searched. Defaults to None.
        interpolate (bool, optional):
            Set to True to interpolate gaps smaller than 2-hours. Defaults to False.
        resample (bool, optional):
            Set to True to resample the data to 0 and 30 minutes past the hour. Defaults to False.

    Returns:
        pd.DataFrame:
            A Pandas DataFrame containing time-indexed weather data.
    """

    start_date = datetime.strptime(start_date, "%Y-%m-%d")

    if end_date is None:
        end_date = datetime.now()
    else:
        end_date = datetime.strptime(end_date, "%Y-%m-%d")

    # Scrape data from source website (https://mesonet.agron.iastate.edu/request/download.phtml)
    uri = f"https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?station={station}&year1={start_date.year}&month1={start_date.month}&day1={start_date.day}&year2={end_date.year}&month2={end_date.month}&day2={end_date.day}&tz=Etc%2FUTC&format=onlycomma&latlon=yes&elev=yes&missing=null&trace=null&direct=no&data=tmpc&data=dwpc&data=relh&data=drct&data=sknt&data=alti&data=p01m&data=vsby&data=skyc1&data=skyc2&data=skyc3"
    df = pd.read_csv(
        uri,
        header=0,
        index_col="valid",
        parse_dates=True,
        na_values=["M", "null"],
        low_memory=False,
    )

    # Post-process data into right units
    df["sknt"] = df.sknt / 1.94384  # convert knots to m/s
    # convert inches of mercury (Hg) to Pa
    df["alti"] = df.alti * 3386.38866667
    df["vsby"] = df["vsby"] * 1.60934  # convert miles to kilometres

    # Get sky clearness
    rplc = {
        "   ": 0,
        "CLR": 0,
        "NCD": 0,
        "NSC": 0,
        "SKC": 0,
        "///": 0,
        "FEW": 1.5,
        "SCT": 3.5,
        "BKN": 6,
        "OVC": 8,
        "VV ": 8,
        "VV": 8,
    }

    for i in ["skyc1", "skyc2", "skyc3"]:
        df[i] = df[i].fillna("NSC").replace(rplc) / 8 * 10
    df["opaque_sky_cover"] = df[["skyc1", "skyc2", "skyc3"]].mean(axis=1)
    df.drop(["skyc1", "skyc2", "skyc3"], axis=1, inplace=True)

    # Rename headers
    renamer = {
        "lon": "longitude",
        "lat": "latitude",
        "elevation": "elevation",
        "tmpc": "dry_bulb_temperature",
        "dwpc": "dew_point_temperature",
        "relh": "relative_humidity",
        "drct": "wind_direction",
        "sknt": "wind_speed",
        "alti": "atmospheric_station_pressure",
        "p01m": "liquid_precipitation_depth",
        "vsby": "visibility",
    }
    df.rename(columns=renamer, inplace=True)
    df.index.name = None

    # Calculate HIR and sky temperature
    df["horizontal_infrared_radiation_intensity"] = [
        calc_horizontal_infrared(
            row.opaque_sky_cover, row.dry_bulb_temperature, row.dew_point_temperature
        )
        for row in df.itertuples()
    ]
    df["sky_temperature"] = [
        calc_sky_temperature(
            row.horizontal_infrared_radiation_intensity, source_emissivity=1
        )
        for row in df.itertuples()
    ]

    # Calculate sun locations
    loc = Location(
        latitude=df.latitude.values[0],
        longitude=df.longitude.values[0],
        elevation=df.elevation.values[0],
        city=f"ICAO-{df.station.values[0]}",
    )
    altitude_in_radians = []
    azimuth_in_radians = []
    for i in df.index:
        sunpath = Sunpath.from_location(loc).calculate_sun_from_date_time(i)
        altitude_in_radians.append(sunpath.altitude_in_radians)
        azimuth_in_radians.append(sunpath.azimuth_in_radians)
    df["solar_altitude"] = altitude_in_radians
    df["solar_azimuth"] = azimuth_in_radians

    # Calculate irradiance and illuminance
    df["temp_offset_3"] = df.dry_bulb_temperature.shift(3)
    dir_norm, dif_horiz = zhang_huang_solar_split(
        df.solar_altitude * 180 / math.pi,
        df.index.day_of_year,
        df.opaque_sky_cover,
        df.relative_humidity,
        df.dry_bulb_temperature,
        df.temp_offset_3,
        df.wind_speed,
        df.atmospheric_station_pressure,
    )
    df["direct_normal_radiation"] = dir_norm
    df["diffuse_horizontal_radiation"] = dif_horiz
    df["global_horizontal_radiation"] = [
        zhang_huang_solar(
            row.solar_altitude * 180 / math.pi,
            row.opaque_sky_cover,
            row.relative_humidity,
            row.dry_bulb_temperature,
            row.temp_offset_3,
            row.wind_speed,
            irr_0=1355,
        )
        for row in df.itertuples()
    ]
    df["extraterrestrial_horizontal_radiation"] = [
        get_extra_radiation(i) for i in df.index.day_of_year
    ]
    df["extraterrestrial_horizontal_radiation"] = df[
        "extraterrestrial_horizontal_radiation"
    ].where(df.global_horizontal_radiation != 0, 0)
    df["direct_normal_radiation"].fillna(0, inplace=True)
    df["diffuse_horizontal_radiation"].fillna(0, inplace=True)
    df["global_horizontal_radiation"].fillna(0, inplace=True)

    vals = []
    for _, row in df.iterrows():
        vals.append(
            estimate_illuminance_from_irradiance(
                row.solar_altitude * 180 / math.pi,
                row.global_horizontal_radiation,
                row.direct_normal_radiation,
                row.diffuse_horizontal_radiation,
                row.dew_point_temperature,
            )
        )
    gh_ill, dn_ill, dh_ill, z_lum = list(zip(*vals))
    df["direct_normal_illuminance"] = dn_ill
    df["diffuse_horizontal_illuminance"] = dh_ill
    df["global_horizontal_illuminance"] = gh_ill
    df["zenith_luminance"] = z_lum
    df.drop(["temp_offset_3"], axis=1, inplace=True)

    if interpolate:
        df.interpolate(limit=4, inplace=True)

    if resample:
        df = df.resample("30T").mean()

    return df


def rolling_window(array: List[Any], window: int):
    """Throwaway function here to roll a window along a list.

    Args:
        array (List[Any]):
            A 1D list of some kind.
        window (int):
            The size of the window to apply to the list.

    Example:
        For an input list like [0, 1, 2, 3, 4, 5, 6, 7, 8],
        returns [[0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [5, 6], [6, 7], [7, 8]]

    Returns:
        List[List[Any]]:
            The resulting, "windowed" list.
    """

    if window > len(array):
        raise ValueError("Array length must be larger than window size.")

    a: np.ndarray = np.array(array)
    shape = a.shape[:-1] + (a.shape[-1] - window + 1, window)
    strides = a.strides + (a.strides[-1],)  # pylint: disable=unsubscriptable-object
    return np.lib.stride_tricks.as_strided(a, shape=shape, strides=strides)


def proximity_decay(
    value: float,
    distance_to_value: float,
    max_distance: float,
    decay_method: str = "linear",
) -> float:
    """Calculate the "decayed" value based on proximity (up to a maximum distance).

    Args:
        value (float):
            The value to be distributed.
        distance_to_value (float):
            A distance at which to return the magnitude.
        max_distance (float):
            The maximum distance to which magnitude is to be distributed. Beyond this, the input
            value is 0.
        decay_method (str, optional):
            A type of distribution (the shape of the distribution profile). Defaults to "linear".

    Returns:
        float:
            The value at the given distance.
    """

    distance_to_value = np.interp(distance_to_value, [0, max_distance], [0, 1])

    if decay_method == "linear":
        return (1 - distance_to_value) * value
    if decay_method == "parabolic":
        return (-(distance_to_value**2) + 1) * value
    if decay_method == "sigmoid":
        return (1 - (0.5 * (np.sin(distance_to_value * np.pi - np.pi / 2) + 1))) * value

    raise ValueError(f"Unknown curve type: {decay_method}")


def base64_to_image(base64_string: str, image_path: Path) -> Path:
    """Convert a base64 encoded image into a file on disk.

    Arguments:
        base64_string (str):
            A base64 string encoding of an image file.
        image_path (Path):
            The location where the image should be stored.

    Returns:
        Path:
            The path to the image file.
    """

    # remove html pre-amble, if necessary
    if base64_string.startswith("data:image"):
        base64_string = base64_string.split(";")[-1]

    with open(Path(image_path), "wb") as fp:
        fp.write(base64.decodebytes(base64_string))

    return image_path


def image_to_base64(image_path: Path, html: bool = False) -> str:
    """Load an image file from disk and convert to base64 string.

    Arguments:
        image_path (Path):
            The file path for the image to be converted.
        html (bool, optional):
            Set to True to include the HTML preamble for a base64 encoded image. Default is False.

    Returns:
        str:
            A base64 string encoding of the input image file.
    """

    # convert path string to Path object
    image_path = Path(image_path).absolute()

    # ensure format is supported
    supported_formats = [".png", ".jpg", ".jpeg"]
    if image_path.suffix not in supported_formats:
        raise ValueError(
            f"'{image_path.suffix}' format not supported. Use one of {supported_formats}"
        )

    # load image and convert to base64 string
    with open(image_path, "rb") as image_file:
        base64_string = base64.b64encode(image_file.read()).decode("utf-8")

    if html:
        content_type = f"data:image/{image_path.suffix.replace('.', '')}"
        content_encoding = "utf-8"
        return f"{content_type};charset={content_encoding};base64,{base64_string}"

    return base64_string


def figure_to_base64(figure: Figure, html: bool = False) -> str:
    """Convert a matplotlib figure object into a base64 string.

    Arguments:
        figure (Figure):
            A matplotlib figure object.
        html (bool, optional):
            Set to True to include the HTML preamble for a base64 encoded image. Default is False.

    Returns:
        str:
            A base64 string encoding of the input figure object.
    """

    buffer = io.BytesIO()
    figure.savefig(buffer)
    buffer.seek(0)
    base64_string = base64.b64encode(buffer.read()).decode("utf-8")

    if html:
        content_type = "data:image/png"
        content_encoding = "utf-8"
        return f"{content_type};charset={content_encoding};base64,{base64_string}"

    return base64_string


def figure_to_image(fig: Figure) -> Image:
    """Convert a matplotlib Figure object into a PIL Image.

    Args:
        fig (Figure):
            A matplotlib Figure object.

    Returns:
        Image:
            A PIL Image.
    """

    # draw the renderer
    fig.canvas.draw()

    # Get the RGBA buffer from the figure
    w, h = fig.canvas.get_width_height()
    buf = np.frombuffer(fig.canvas.tostring_argb(), dtype=np.uint8)
    buf.shape = (w, h, 4)
    buf = np.roll(buf, 3, axis=2)

    return Image.fromarray(buf)


def timedelta_tostring(time_delta: timedelta) -> str:
    """timedelta objects don't have a nice string representation, so this function converts them.

    Args:
        time_delta (datetime.timedelta):
            The timedelta object to convert.
    Returns:
        str:
            A string representation of the timedelta object.
    """
    s = time_delta.seconds
    hours, remainder = divmod(s, 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}"


def decay_rate_smoother(
    series: pd.Series,
    difference_threshold: float = -10,
    transition_window: int = 4,
    ewm_span: float = 1.25,
) -> pd.Series:
    """Helper function that adds a decay rate to a time-series for values dropping significantly
        below the previous values.

    Args:
        series (pd.Series):
            The series to modify
        difference_threshold (float, optional):
            The difference between current/previous values which class as a "transition".
            Defaults to -10.
        transition_window (int, optional):
            The number of values after the "transition" within which an exponentially weighted mean
             should be applied. Defaults to 4.
        ewm_span (float, optional):
            The rate of decay. Defaults to 1.25.

    Returns:
        pd.Series:
            A modified series
    """

    # Find periods of major transition (where values vary significantly)
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


def cardinality(direction_angle: float, directions: int = 16):
    """Returns the cardinal orientation of a given angle, where that angle is related to north at
        0 degrees.
    Args:
        direction_angle (float):
            The angle to north in degrees (+Ve is interpreted as clockwise from north at 0.0
            degrees).
        directions (int):
            The number of cardinal directions into which angles shall be binned (This value should
            be one of 4, 8, 16 or 32, and is centred about "north").
    Returns:
        int:
            The cardinal direction the angle represents.
    """

    if direction_angle > 360 or direction_angle < 0:
        raise ValueError(
            "The angle entered is beyond the normally expected range for an orientation in degrees."
        )

    cardinal_directions = {
        4: ["N", "E", "S", "W"],
        8: ["N", "NE", "E", "SE", "S", "SW", "W", "NW"],
        16: [
            "N",
            "NNE",
            "NE",
            "ENE",
            "E",
            "ESE",
            "SE",
            "SSE",
            "S",
            "SSW",
            "SW",
            "WSW",
            "W",
            "WNW",
            "NW",
            "NNW",
        ],
        32: [
            "N",
            "NbE",
            "NNE",
            "NEbN",
            "NE",
            "NEbE",
            "ENE",
            "EbN",
            "E",
            "EbS",
            "ESE",
            "SEbE",
            "SE",
            "SEbS",
            "SSE",
            "SbE",
            "S",
            "SbW",
            "SSW",
            "SWbS",
            "SW",
            "SWbW",
            "WSW",
            "WbS",
            "W",
            "WbN",
            "WNW",
            "NWbW",
            "NW",
            "NWbN",
            "NNW",
            "NbW",
        ],
    }

    if directions not in cardinal_directions:
        raise ValueError(
            f'The input "directions" must be one of {list(cardinal_directions.keys())}.'
        )

    val = int((direction_angle / (360 / directions)) + 0.5)

    arr = cardinal_directions[directions]

    return arr[(val % directions)]


def angle_from_cardinal(cardinal_direction: str) -> float:
    """
    For a given cardinal direction, return the corresponding angle in degrees.

    Args:
        cardinal_direction (str):
            The cardinal direction.
    Returns:
        float:
            The angle associated with the cardinal direction.
    """
    cardinal_directions = [
        "N",
        "NbE",
        "NNE",
        "NEbN",
        "NE",
        "NEbE",
        "ENE",
        "EbN",
        "E",
        "EbS",
        "ESE",
        "SEbE",
        "SE",
        "SEbS",
        "SSE",
        "SbE",
        "S",
        "SbW",
        "SSW",
        "SWbS",
        "SW",
        "SWbW",
        "WSW",
        "WbS",
        "W",
        "WbN",
        "WNW",
        "NWbW",
        "NW",
        "NWbN",
        "NNW",
        "NbW",
    ]
    if cardinal_direction not in cardinal_directions:
        raise ValueError(f"{cardinal_direction} is not a known cardinal_direction.")
    angles = np.arange(0, 360, 11.25)

    lookup = dict(zip(cardinal_directions, angles))

    return lookup[cardinal_direction]


def angle_from_north(vector: List[float]) -> float:
    """For an X, Y vector, determine the clockwise angle to north at [0, 1].

    Args:
        vector (List[float]):
            A vector of length 2.

    Returns:
        float:
            The angle between vector and north in degrees clockwise from [0, 1].
    """
    north = [0, 1]
    angle1 = np.arctan2(*north[::-1])
    angle2 = np.arctan2(*vector[::-1])
    return np.rad2deg((angle1 - angle2) % (2 * np.pi))


def sanitise_string(string: str) -> str:
    """Sanitise a string so that only path-safe characters remain."""
    keep_characters = r"[^.A-Za-z0-9_-]"
    return re.sub(keep_characters, "_", string).replace("__", "_").rstrip()


def stringify_df_header(columns: List[Any]) -> List[str]:
    """Convert a list of objects into their string represenations. This
    method is mostly used for making DataFrames parqeut serialisable.
    """

    return [str(i) for i in columns]


def unstringify_df_header(columns: List[str]) -> List[Any]:
    """Convert a list of strings into a set of objecst capable of being used
    as DataFrame column headers.
    """

    evaled = []
    for i in columns:
        try:
            evaled.append(eval(i))  # pylint: disable=eval-used
        except NameError:
            evaled.append(i)

    if all("(" in i for i in str(evaled)):
        return pd.MultiIndex.from_tuples(evaled)
    return evaled


def store_dataset(
    dataframe: pd.DataFrame, target_path: Path, downcast: bool = True
) -> Path:
    """Serialise a pandas DataFrame as a parquet file, including pre-processing to ensure it is serialisable, and optional downcasting to samller dtypes.

    Args:
        dataframe (pd.DataFrame):
            The dataframe to be serialised
        target_path (Path):
            The target file for storage.
        downcast (bool, optional):
            Optinal downcasting to reduce dataframe dtype complexity. Defaults to True.

    Returns:
        Path:
            The path to the stored dataset.
    """

    target_path = Path(target_path)

    if "parquet" not in target_path.suffix:
        raise ValueError('This method only currently works for "*.parquet" files.')

    if downcast:
        # downcast dataframe type to save on storage
        for col, _type in dataframe.dtypes.items():
            if _type == "float64":
                dataframe[col] = dataframe[col].astype(np.float32)
            if _type == "int64":
                dataframe[col] = dataframe[col].astype(np.int16)

    # prepare dataframe for storage as parquet
    dataframe.columns = stringify_df_header(dataframe.columns)

    # store dataframe
    dataframe.to_parquet(target_path, compression="snappy")

    return target_path


def load_dataset(target_path: Path, upcast: bool = True) -> pd.DataFrame:
    """Read a stored dataset, including upcasting to float64.

    Args:
        target_path (Path):
            The dataset path to be loaded.
        upcast (bool, optional):
            Optional upcasting of data to enable downstream calculations without issues!

    Returns:
        pd.DataFrame:
            The loaded dataset as a dataframe.
    """

    df = pd.read_parquet(target_path)

    if upcast:
        for col, _type in dict(df.dtypes).items():
            if _type == "float32":
                df[col].astype(np.float64)
            elif _type in ["int32", "int16", "int8"]:
                df[col].astype(np.int64)

    df.columns = unstringify_df_header(df.columns)

    return df


class OpenMeteoVariable(Enum):
    """An enumeration of the variables available from OpenMeteo."""

    TIME = "time"
    TEMPERATURE_2M = "temperature_2m"
    DEWPOINT_2M = "dewpoint_2m"
    RELATIVEHUMIDITY_2M = "relativehumidity_2m"
    SURFACE_PRESSURE = "surface_pressure"
    SHORTWAVE_RADIATION = "shortwave_radiation"
    DIRECT_RADIATION = "direct_radiation"
    DIFFUSE_RADIATION = "diffuse_radiation"
    WINDDIRECTION_10M = "winddirection_10m"
    WINDSPEED_10M = "windspeed_10m"
    CLOUDCOVER = "cloudcover"
    WEATHERCODE = "weathercode"
    PRECIPITATION = "precipitation"
    RAIN = "rain"
    SNOWFALL = "snowfall"
    CLOUDCOVER_LOW = "cloudcover_low"
    CLOUDCOVER_MID = "cloudcover_mid"
    CLOUDCOVER_HIGH = "cloudcover_high"
    DIRECT_NORMAL_IRRADIANCE = "direct_normal_irradiance"
    WINDSPEED_100M = "windspeed_100m"
    WINDDIRECTION_100M = "winddirection_100m"
    WINDGUSTS_10M = "windgusts_10m"
    ET0_FAO_EVAPOTRANSPIRATION = "et0_fao_evapotranspiration"
    VAPOR_PRESSURE_DEFICIT = "vapor_pressure_deficit"
    SOIL_TEMPERATURE_0_TO_7CM = "soil_temperature_0_to_7cm"
    SOIL_TEMPERATURE_7_TO_28CM = "soil_temperature_7_to_28cm"
    SOIL_TEMPERATURE_28_TO_100CM = "soil_temperature_28_to_100cm"
    SOIL_TEMPERATURE_100_TO_255CM = "soil_temperature_100_to_255cm"
    SOIL_MOISTURE_0_TO_7CM = "soil_moisture_0_to_7cm"
    SOIL_MOISTURE_7_TO_28CM = "soil_moisture_7_to_28cm"
    SOIL_MOISTURE_28_TO_100CM = "soil_moisture_28_to_100cm"
    SOIL_MOISTURE_100_TO_255CM = "soil_moisture_100_to_255cm"

    @classmethod
    def from_string(cls, name: str) -> OpenMeteoVariable:
        """."""
        d = {
            "time": cls.TIME,
            "temperature_2m": cls.TEMPERATURE_2M,
            "dewpoint_2m": cls.DEWPOINT_2M,
            "relativehumidity_2m": cls.RELATIVEHUMIDITY_2M,
            "surface_pressure": cls.SURFACE_PRESSURE,
            "shortwave_radiation": cls.SHORTWAVE_RADIATION,
            "direct_radiation": cls.DIRECT_RADIATION,
            "diffuse_radiation": cls.DIFFUSE_RADIATION,
            "winddirection_10m": cls.WINDDIRECTION_10M,
            "windspeed_10m": cls.WINDSPEED_10M,
            "cloudcover": cls.CLOUDCOVER,
            "weathercode": cls.WEATHERCODE,
            "precipitation": cls.PRECIPITATION,
            "rain": cls.RAIN,
            "snowfall": cls.SNOWFALL,
            "cloudcover_low": cls.CLOUDCOVER_LOW,
            "cloudcover_mid": cls.CLOUDCOVER_MID,
            "cloudcover_high": cls.CLOUDCOVER_HIGH,
            "direct_normal_irradiance": cls.DIRECT_NORMAL_IRRADIANCE,
            "windspeed_100m": cls.WINDSPEED_100M,
            "winddirection_100m": cls.WINDDIRECTION_100M,
            "windgusts_10m": cls.WINDGUSTS_10M,
            "et0_fao_evapotranspiration": cls.ET0_FAO_EVAPOTRANSPIRATION,
            "vapor_pressure_deficit": cls.VAPOR_PRESSURE_DEFICIT,
            "soil_temperature_0_to_7cm": cls.SOIL_TEMPERATURE_0_TO_7CM,
            "soil_temperature_7_to_28cm": cls.SOIL_TEMPERATURE_7_TO_28CM,
            "soil_temperature_28_to_100cm": cls.SOIL_TEMPERATURE_28_TO_100CM,
            "soil_temperature_100_to_255cm": cls.SOIL_TEMPERATURE_100_TO_255CM,
            "soil_moisture_0_to_7cm": cls.SOIL_MOISTURE_0_TO_7CM,
            "soil_moisture_7_to_28cm": cls.SOIL_MOISTURE_7_TO_28CM,
            "soil_moisture_28_to_100cm": cls.SOIL_MOISTURE_28_TO_100CM,
            "soil_moisture_100_to_255cm": cls.SOIL_MOISTURE_100_TO_255CM,
        }
        try:
            return d[name]
        except KeyError as e:
            raise KeyError(e, f"{name} is not a known variable name.")

    @property
    def conversion_name(self) -> str:
        """Convert the enum value into a Ladybug dataype string representation (for this toolkit)."""
        d = {
            self.TIME.value: "Time (datetime)",
            self.TEMPERATURE_2M.value: "Dry Bulb Temperature (C)",
            self.DEWPOINT_2M.value: "Dew Point Temperature (C)",
            self.RELATIVEHUMIDITY_2M.value: "Relative Humidity (%)",
            self.SURFACE_PRESSURE.value: "Atmospheric Station Pressure (Pa)",
            self.SHORTWAVE_RADIATION.value: "Global Horizontal Radiation (Wh/m2)",
            self.DIRECT_RADIATION.value: "Direct Horizontal Radiation (Wh/m2)",
            self.DIFFUSE_RADIATION.value: "Diffuse Horizontal Radiation (Wh/m2)",
            self.WINDDIRECTION_10M.value: "Wind Direction (degrees)",
            self.WINDSPEED_10M.value: "Wind Speed (m/s)",
            self.CLOUDCOVER.value: "Opaque Sky Cover (tenths)",
            self.WEATHERCODE.value: "Present Weather Codes (codes)",
            self.PRECIPITATION.value: "Precipitable Water (mm)",
            self.RAIN.value: "Liquid Precipitation Depth (mm)",
            self.SNOWFALL.value: "Snow Depth (cm)",
            self.CLOUDCOVER_LOW.value: "Cloud Cover @<2km (tenths)",
            self.CLOUDCOVER_MID.value: "Cloud Cover @2-6km (tenths)",
            self.CLOUDCOVER_HIGH.value: "Cloud Cover @>6km (tenths)",
            self.DIRECT_NORMAL_IRRADIANCE.value: "Direct Normal Radiation (Wh/m2)",
            self.WINDSPEED_100M.value: "Wind Speed @100m (m/s)",
            self.WINDDIRECTION_100M.value: "Wind Direction @100m (degrees)",
            self.WINDGUSTS_10M.value: "Wind Gusts (m/s)",
            self.ET0_FAO_EVAPOTRANSPIRATION.value: "Evapotranspiration (mm/inch)",
            self.VAPOR_PRESSURE_DEFICIT.value: "Vapor Pressure Deficit (Pa)",
            self.SOIL_TEMPERATURE_0_TO_7CM.value: "Soil Temperature @0-7cm (C)",
            self.SOIL_TEMPERATURE_7_TO_28CM.value: "Soil Temperature @7-28cm (C)",
            self.SOIL_TEMPERATURE_28_TO_100CM.value: "Soil Temperature @28-100cm (C)",
            self.SOIL_TEMPERATURE_100_TO_255CM.value: "Soil Temperature @100-255cm (C)",
            self.SOIL_MOISTURE_0_TO_7CM.value: "Soil Moisture @0-7cm (fraction)",
            self.SOIL_MOISTURE_7_TO_28CM.value: "Soil Moisture @7-28cm (fraction)",
            self.SOIL_MOISTURE_28_TO_100CM.value: "Soil Moisture @28-100cm (fraction)",
            self.SOIL_MOISTURE_100_TO_255CM.value: "Soil Moisture @100-255cm (fraction)",
        }

        return d[self.value]

    @property
    def conversion_factor(self) -> float:
        """Factors to multiple returned data from OpenMeteo by to give EPW standard units."""
        d = {
            self.TIME.value: None,
            self.TEMPERATURE_2M.value: 1,
            self.DEWPOINT_2M.value: 1,
            self.RELATIVEHUMIDITY_2M.value: 1,
            self.SURFACE_PRESSURE.value: 100,
            self.SHORTWAVE_RADIATION.value: 1,
            self.DIRECT_RADIATION.value: 1,
            self.DIFFUSE_RADIATION.value: 1,
            self.WINDDIRECTION_10M.value: 1,
            self.WINDSPEED_10M.value: 1 / 3.6,
            self.CLOUDCOVER.value: 0.1,
            self.WEATHERCODE.value: None,
            self.PRECIPITATION.value: 1,
            self.RAIN.value: 1,
            self.SNOWFALL.value: 1,
            self.CLOUDCOVER_LOW.value: 0.1,
            self.CLOUDCOVER_MID.value: 0.1,
            self.CLOUDCOVER_HIGH.value: 0.1,
            self.DIRECT_NORMAL_IRRADIANCE.value: 1,
            self.WINDSPEED_100M.value: 1 / 3.6,
            self.WINDDIRECTION_100M.value: 1,
            self.WINDGUSTS_10M.value: 1 / 3.6,
            self.ET0_FAO_EVAPOTRANSPIRATION.value: 1,
            self.VAPOR_PRESSURE_DEFICIT.value: 0.001,
            self.SOIL_TEMPERATURE_0_TO_7CM.value: 1,
            self.SOIL_TEMPERATURE_7_TO_28CM.value: 1,
            self.SOIL_TEMPERATURE_28_TO_100CM.value: 1,
            self.SOIL_TEMPERATURE_100_TO_255CM.value: 1,
            self.SOIL_MOISTURE_0_TO_7CM.value: 1,
            self.SOIL_MOISTURE_7_TO_28CM.value: 1,
            self.SOIL_MOISTURE_28_TO_100CM.value: 1,
            self.SOIL_MOISTURE_100_TO_255CM.value: 1,
        }

        return d[self.value]


def scrape_openmeteo(
    latitude: float,
    longitude: float,
    start_date: Union[datetime, str],
    end_date: Union[datetime, str],
    variables: List[OpenMeteoVariable],
    convert_units: bool = False,
) -> pd.DataFrame:
    """Obtain historic hourly data from Open-Meteo.
    https://open-meteo.com/en/docs/historical-weather-api

    Args:
        latitude (float):
            The latitude of the target site, in degrees.
        longitude (float):
            The longitude of the target site, in degrees.
        start_date Union[datetime, str]:
            The start-date from which records will be obtained.
        end_date Union[datetime, str]:
            The end-date beyond which records will be ignored.
        variables (List[OpenMeteoVariable]):
            A list of variables to query.
        convert_units (bool, optional):
            Convert units output into more common units, and rename headers accordingly.

    Returns:
        pd.DataFrame:
            A DataFrame containing scraped data.
    """
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, "%Y-%m-%d")
    if isinstance(end_date, str):
        end_date = datetime.strptime(end_date, "%Y-%m-%d")

    var_strings = ",".join([i.value for i in variables if i.name.lower() != "time"])
    query_string = f"https://archive-api.open-meteo.com/v1/era5?latitude={latitude}&longitude={longitude}&start_date={start_date:%Y-%m-%d}&end_date={end_date:%Y-%m-%d}&hourly={var_strings}"

    with urllib.request.urlopen(query_string) as url:
        data = json.load(url)

    if not convert_units:
        headers = [f"{k} ({v})" for (k, v) in data["hourly_units"].items()]
    else:
        headers = [
            OpenMeteoVariable.from_string(k).conversion_name
            for (k, v) in data["hourly_units"].items()
        ]

    if not convert_units:
        values = [v for k, v in data["hourly"].items()]
    else:
        values = []
        for k, v in data["hourly"].items():
            en = OpenMeteoVariable.from_string(k)
            if en.conversion_factor is None:
                values.append(v)
            else:
                values.append([i * en.conversion_factor for i in v])
    df = pd.DataFrame(np.array(values).T, columns=headers)
    df = df.set_index(df.columns[0])
    df.index = pd.to_datetime(df.index)
    return df


def weibull_directional(
    binned_data: Dict[Tuple[float, float], List[float]]
) -> pd.DataFrame:
    """Calculate the weibull coefficients for a given set of binned data in the form {(low, high): [speeds], (low, high): [speeds]}, binned by the number of directions specified.
    Args:
        binned_data (Dict[Tuple[float, float], List[float]]):
            A dictionary of binned wind speed data.
    Returns:
        pd.DataFrame:
            A DataFrame with (direction_bin_low, direction_bin_high) as index, and weibull coefficients as columns.
    """
    warnings.warn(
        "This method was written by someone who doesn't actually know what thesse values mean. PLease don't trust them!"
    )
    d = {}
    for (low, high), speeds in tqdm(
        binned_data.items(), desc="Calculating Weibull shape parameters"
    ):
        d[(low, high)] = weibull_pdf(speeds)

    return pd.DataFrame.from_dict(d, orient="index", columns=["x", "k", "λ", "α"])


def weibull_pdf(wind_speeds: List[float]) -> Tuple[float]:
    """Calculate the parameters of an exponentiated Weibull continuous random variable.
    Returns:
        x (float):
            Shape parameter
            scipy - mean
        k (float):
            Shape parameter
            scipy - variance
        λ (float):
            Scale parameter.
            scipy - skew
        α (float):
            Shape parameter.
            CFD - scale, c
            scipy - kurtosis
    """
    ws = np.array(wind_speeds)
    ws = ws[ws != 0]
    ws = ws[~np.isnan(ws)]
    try:
        return exponweib.fit(ws, floc=0, f0=1)
    except ValueError as exc:
        warnings.warn(f"Not enough data to calculate Weibull parameters.\n{exc}")
        return (1, np.nan, 0, np.nan)  # type: ignore


def circular_weighted_mean(angles: List[float], weights: List[float]):
    """Get the average angle from a set of weighted angles.

    Args:
        angles (List[float]):
            A collection of equally weighted wind directions, in degrees from North (0).
        weights (List[float]):
            A collection of weights, which must sum to 1.

    Returns:
        float:
            An average wind direction.
    """

    angles = np.array(angles)
    weights = np.array(weights)

    if angles.shape != weights.shape:
        raise ValueError("weights must be the same size as angles.")

    if np.any(angles < 0) or np.any(angles > 360):
        raise ValueError("Input angles exist outside of expected range (0-360).")

    if weights is None:
        weights = np.ones_like(angles) / len(angles)

    if sum(weights) != 1:
        raise ValueError("weights must total 1.")

    x = y = 0.0
    for angle, weight in zip(angles, weights):
        x += np.cos(np.radians(angle)) * weight
        y += np.sin(np.radians(angle)) * weight

    mean = np.degrees(np.arctan2(y, x))

    if mean < 0:
        mean = 360 + mean

    return mean


def wind_direction_average(angles: List[float]) -> float:
    """Get the average wind direction from a set of wind directions.

    Args:
        angles (List[float]):
            A collection of equally weighted wind directions, in degrees from North (0).

    Returns:
        float:
            An average angle.
    """

    angles = np.array(angles)  # type: ignore

    if np.any(angles < 0) or np.any(angles > 360):  # type: ignore
        raise ValueError("Input angles exist outside of expected range (0-360).")

    if len(angles) == 0:
        return np.NaN

    angles = np.radians(angles)  # type: ignore

    average_angle = np.round(
        np.arctan2(
            (1 / len(angles) * np.sin(angles)).sum(),
            (1 / len(angles) * np.cos(angles)).sum(),
        ),
        2,
    )

    if average_angle < 0:
        average_angle = (np.pi * 2) - -average_angle

    return np.degrees(average_angle)


def wind_speed_at_height(
    reference_value: float,
    reference_height: float,
    target_height: float,
    **kwargs,
) -> float:
    """Calculate the wind speed at a given height from the 10m default height
        as stated in an EPW file.

    Args:
        reference_wind_speed (float):
            The speed to be translated.
        reference_height (float):
            The original height of the wind speed being translated.
        target_height (float):
            The target height of the wind speed being translated.
        **kwargs:
            Additional keyword arguments to be passed to the
            wind_speed_at_height function. This includes:
                terrain_roughness_length (float):
                    A value describing how rough the ground is. Default is
                    0.03 for Open flat terrain; grass, few isolated obstacles.
                log_function (bool, optional):
                    Set to True to used the log transformation method, or
                    False for the exponent method. Defaults to True.

    Notes:
        Terrain roughness lengths can be found in the following table:
            | Terrain description                               |  z0 (m)   |
            ----------------------------------------------------|-----------|
            | Open sea, Fetch at least 5 km                     |    0.0002 |
            | Mud flats, snow; no vegetation, no obstacles      |    0.005  |
            | Open flat terrain; grass, few isolated obstacle   |    0.03   |
            | Low crops; occasional large obstacles, x/H > 20   |    0.10   |
            | High crops; scattered obstacles, 15 < x/H < 20    |    0.25   |
            | parkland, bushes; numerous obstacles, x/H ≈ 10    |    0.5    |
            | Regular large obstacle coverage (suburb, forest)  |    1.0    |
            | City centre with high- and low-rise buildings     |  ≥ 2      |
            ----------------------------------------------------------------|

    Returns:
        float:
            The translated wind speed at the target height.
    """

    terrain_roughness_length = kwargs.get("terrain_roughness_length", 0.03)
    log_function = kwargs.get("log_function", True)
    kwargs = {}  # reset kwargs to remove invalid arguments

    if log_function:
        return reference_value * (
            np.log(target_height / terrain_roughness_length)
            / np.log(reference_height / terrain_roughness_length)
        )
    wind_shear_exponent = 1 / 7
    return reference_value * (
        np.power((target_height / reference_height), wind_shear_exponent)
    )


def temperature_at_height(
    reference_value: float,
    reference_height: float,
    target_height: float,
    **kwargs,
) -> float:
    """Estimate the dry-bulb temperature at a given height from a referenced
        dry-bulb temperature at another height.

    Args:
        reference_temperature (float):
            The temperature to translate.
        reference_height (float):
            The height of the reference temperature.
        target_height (float):
            The height to translate the reference temperature towards.
        **kwargs:
            Additional keyword arguments to be passed to the
            temperature_at_height function. This includes:
                reduction_per_km_altitude_gain (float, optional):
                    The lapse rate of the atmosphere. Defaults to 0.0065 based
                    on https://scied.ucar.edu/learning-zone/atmosphere/change-atmosphere-altitude#:~:text=Near%20the%20Earth's%20surface%2C%20air,standard%20(average)%20lapse%20rate

        lapse_rate (float, optional):
            The degrees C reduction for every 1 altitude gain. Default is 0.0065C for clear
            conditions (or 6.5C per 1km). This would be nearer 0.0098C/m if cloudy/moist air conditions.

    Returns:
        float:
            A translated air temperature.
    """

    if (target_height > 8000) or (reference_height > 8000):
        warnings.warn(
            "The heights input into this calculation exist partially above the egde of the troposphere. This method is only valid below 8000m."
        )

    lapse_rate = kwargs.get("lapse_rate", 0.0065)
    kwargs = {}  # reset kwargs to remove invalid arguments

    height_difference = target_height - reference_height

    return reference_value - (height_difference * lapse_rate)


def radiation_at_height(
    reference_value: float,
    target_height: float,
    reference_height: float,
    lapse_rate: float = 0.08,
    **kwargs,
) -> float:
    """Calculate the radiation at a given height, given a reference radiation
        and height.

    References:
        Armel Oumbe, Lucien Wald. A parameterisation of vertical profile of
        solar irradiance for correcting solar fluxes for changes in terrain
        elevation. Earth Observation and Water Cycle Science Conference,
        Nov 2009, Frascati, Italy. pp.S05.

    Args:
        reference_radiation (float):
            The radiation at the reference height.
        target_height (float):
            The height at which the radiation is required, in m.
        reference_height (float, optional):
            The height at which the reference radiation was measured.
        **kwargs:
            Additional keyword arguments to be passed to the
            radiation_at_height function. This includes:
                lapse_rate (float, optional):
                    The lapse rate of the atmosphere. Defaults to 0.08.

    Returns:
        float:
            The radiation at the given height.
    """
    lapse_rate = kwargs.get("lapse_rate", 0.08)
    kwargs = {}  # reset kwargs to remove invalid arguments

    lapse_rate_per_m = lapse_rate * reference_value / 1000
    increase = lapse_rate_per_m * (target_height - reference_height)
    return reference_value + increase


def air_pressure_at_height(
    reference_value: float,
    target_height: float,
    reference_height: float,
) -> float:
    """Calculate the air pressure at a given height, given a reference pressure and height.

    Args:
        reference_pressure (float):
            The pressure at the reference height, in Pa.
        target_height (float):
            The height at which the pressure is required, in m.
        reference_height (float, optional):
            The height at which the reference pressure was measured. Defaults to 10m.

    Returns:
        float:
            The pressure at the given height.
    """
    return (
        reference_value
        * (1 - 0.0065 * (target_height - reference_height) / 288.15) ** 5.255
    )


def target_wind_speed_collection(
    epw: EPW, target_average_wind_speed: float, target_height: float
) -> HourlyContinuousCollection:
    """Create an annual hourly collection of wind-speeds whose average equals the target value,
        translated to 10m height, using the source EPW to provide a wind-speed profile.

    Args:
        epw (EPW):
            The source EPW from which the wind speed profile is used to distribute wind speeds.
        target_average_wind_speed (float):
            The value to be translated to 10m and set as the average for the target wind-speed
            collection.
        target_height (float):
            The height at which the wind speed is translated to (this will assume the original wind
            speed is at 10m per EPW conventions.

    Returns:
        HourlyContinuousCollection:
            A ladybug annual hourly data wind speed collection.
    """

    # Translate target wind speed at ground level to wind speed at 10m, assuming an open terrain per airport conditions
    target_average_wind_speed_at_10m = wind_speed_at_height(
        reference_value=target_average_wind_speed,
        reference_height=target_height,
        target_height=10,
        terrain_roughness_length=0.03,
    )

    # Adjust hourly values in wind_speed to give a new overall average equal to that of the target wind-speed
    adjustment_factor = target_average_wind_speed_at_10m / epw.wind_speed.average

    return epw.wind_speed * adjustment_factor


def dry_bulb_temperature_at_height(
    epw: EPW, target_height: float
) -> HourlyContinuousCollection:
    """Translate DBT values from an EPW into

    Args:
        epw (EPW): A Ladybug EPW object.
        target_height (float): The height to translate the reference temperature towards.

    Returns:
        HourlyContinuousCollection: A resulting dry-bulb temperature collection.
    """
    dbt_collection = copy.copy(epw.dry_bulb_temperature)
    dbt_collection.values = [
        temperature_at_height(i, 10, target_height)
        for i in epw.dry_bulb_temperature.values
    ]
    return dbt_collection


def tile_images(
    imgs: Union[List[Path], List[Image.Image]], rows: int, cols: int
) -> Image.Image:
    """Tile a set of images into a grid.

    Args:
        imgs (Union[List[Path], List[Image.Image]]):
            A list of images to tile.
        rows (int):
            The number of rows in the grid.
        cols (int):
            The number of columns in the grid.

    Returns:
        Image.Image:
            A PIL image of the tiled images.
    """

    imgs = np.array([Path(i) for i in np.array(imgs).flatten()])

    # open images if paths passed
    imgs = [Image.open(img) if isinstance(img, Path) else img for img in imgs]

    if len(imgs) != rows * cols:
        raise ValueError(
            f"The number of images given ({len(imgs)}) does not equal ({rows}*{cols})"
        )

    # ensure each image has the same dimensions
    w, h = imgs[0].size
    for img in imgs:
        if img.size != (w, h):
            raise ValueError("All images must have the same dimensions")

    w, h = imgs[0].size
    grid = Image.new("RGBA", size=(cols * w, rows * h))

    for i, img in enumerate(imgs):
        grid.paste(img, box=(i % cols * w, i // cols * h))
        img.close()

    return grid


def validate_timeseries(
    obj: Any,
    is_annual: bool = False,
    is_hourly: bool = False,
    is_contiguous: bool = False,
) -> None:
    """Check if the input object is a pandas Series, and has a datetime index.

    Args:
        obj (Any):
            The object to check.
        is_annual (bool, optional):
            If True, check that the series is annual. Defaults to False.
        is_hourly (bool, optional):
            If True, check that the series is hourly. Defaults to False.
        is_contiguous (bool, optional):
            If True, check that the series is contiguous. Defaults to False.

    Raises:
        TypeError: If the object is not a pandas Series.
        TypeError: If the series does not have a datetime index.
        ValueError: If the series is not annual.
        ValueError: If the series is not hourly.
        ValueError: If the series is not contiguous.
    """
    if not isinstance(obj, pd.Series):
        raise TypeError("series must be a pandas Series")
    if not isinstance(obj.index, pd.DatetimeIndex):
        raise TypeError("series must have a datetime index")
    if is_annual:
        if (obj.index.day_of_year.nunique() != 365) or (
            obj.index.day_of_year.nunique() != 366
        ):
            raise ValueError("series is not annual")
    if is_hourly:
        if obj.index.hour.nunique() != 24:
            raise ValueError("series is not hourly")
    if is_contiguous:
        if not obj.index.is_monotonic_increasing:
            raise ValueError("series is not contiguous")


def lighten_color(color: Union[str, Tuple], amount: float = 0.5) -> Tuple[float]:
    """
    Lightens the given color by multiplying (1-luminosity) by the given amount.

    Args:
        color (str):
            A color-like string.
        amount (float):
            The amount of lightening to apply.

    Returns:
        Tuple[float]:
            An RGB value.

    Examples:
    >> lighten_color('g', 0.3)
    >> lighten_color('#F034A3', 0.6)
    >> lighten_color((.3,.55,.1), 0.5)
    """
    try:
        c = cnames[color]
    except KeyError:
        c = color
    c = colorsys.rgb_to_hls(*to_rgb(c))
    return colorsys.hls_to_rgb(c[0], 1 - amount * (1 - c[1]), c[2])


def triangulation_area(triang: Triangulation) -> float:
    """Calculate the area of a matplotlib Triangulation.

    Args:
        triang (Triangulation):
            A matplotlib Triangulation object.

    Returns:
        float:
            The area of the Triangulation in the units given.
    """

    triangles = triang.triangles
    x, y = triang.x, triang.y
    a, _ = triangles.shape
    i = np.arange(a)
    area = np.sum(
        np.abs(
            0.5
            * (
                (x[triangles[i, 1]] - x[triangles[i, 0]])
                * (y[triangles[i, 2]] - y[triangles[i, 0]])
                - (x[triangles[i, 2]] - x[triangles[i, 0]])
                * (y[triangles[i, 1]] - y[triangles[i, 0]])
            )
        )
    )

    return area


def create_triangulation(
    x: List[float],
    y: List[float],
    alpha: float = None,
    max_iterations: int = 250,
    increment: float = 0.01,
) -> Triangulation:
    """Create a matplotlib Triangulation from a list of x and y coordinates, including a mask to
        remove elements with edges larger than alpha.

    Args:
        x (List[float]):
            A list of x coordinates.
        y (List[float]):
            A list of y coordinates.
        alpha (float, optional):
            A value to start alpha at.
            Defaults to None, with an estimate made for a suitable starting point.
        max_iterations (int, optional):
            The number of iterations to run to check against triangulation validity.
            Defaults to 250.
        increment (int, optional):
            The value by which to increment alpha by when searching for a valid triangulation.
            Defaults to 0.01.

    Returns:
        Triangulation:
            A matplotlib Triangulation object.
    """

    if alpha is None:
        # TODO - add method here to automatically determine appropriate alpha value
        alpha = 1.1

    if len(x) != len(y):
        raise ValueError("x and y must be the same length")

    # Triangulate X, Y locations
    triang = Triangulation(x, y)

    xtri = x[triang.triangles] - np.roll(x[triang.triangles], 1, axis=1)
    ytri = y[triang.triangles] - np.roll(y[triang.triangles], 1, axis=1)
    maxi = np.max(np.sqrt(xtri**2 + ytri**2), axis=1)

    # Iterate triangulation masking until a possible mask is found
    count = 0
    fig, ax = plt.subplots(1, 1)
    synthetic_values = range(len(x))
    success = False
    while not success:
        count += 1
        try:
            tr = copy.deepcopy(triang)
            tr.set_mask(maxi > alpha)
            ax.tricontour(tr, synthetic_values)
            success = True
        except ValueError:
            alpha += increment
        else:
            break
        if count > max_iterations:
            raise ValueError(
                f"Could not create a valid triangulation mask within {max_iterations}"
            )
    plt.close(fig)
    triang.set_mask(maxi > alpha)
    return triang


def evaporative_cooling_effect(
    dry_bulb_temperature: float,
    relative_humidity: float,
    evaporative_cooling_effectiveness: float,
    atmospheric_pressure: float = None,
) -> List[float]:
    """
    For the inputs, calculate the effective DBT and RH values for the evaporative cooling
    effectiveness given.

    Args:
        dry_bulb_temperature (float):
            A dry bulb temperature in degrees Celsius.
        relative_humidity (float):
            A relative humidity in percent (0-100).
        evaporative_cooling_effectiveness (float):
            The evaporative cooling effectiveness. This should be a value between 0 (no effect)
            and 1 (saturated air).
        atmospheric_pressure (float, optional):
            A pressure in Pa. Default is pressure at sea level (101325 Pa).

    Returns:
        effective_dry_bulb_temperature, effective_relative_humidity (List[float]):
            A list of two values for the effective dry bulb temperature and relative humidity.
    """

    if atmospheric_pressure is None:
        atmospheric_pressure = 101325

    wet_bulb_temperature = wet_bulb_from_db_rh(
        dry_bulb_temperature, relative_humidity, atmospheric_pressure
    )

    new_dbt = dry_bulb_temperature - (
        (dry_bulb_temperature - wet_bulb_temperature)
        * evaporative_cooling_effectiveness
    )
    new_rh = (
        relative_humidity * (1 - evaporative_cooling_effectiveness)
    ) + evaporative_cooling_effectiveness * 100

    if new_rh > 100:
        new_rh = 100
        new_dbt = wet_bulb_temperature

    return [new_dbt, new_rh]


def evaporative_cooling_effect_collection(
    epw: EPW, evaporative_cooling_effectiveness: float = 0.3
) -> List[HourlyContinuousCollection]:
    """Calculate the effective DBT and RH considering effects of evaporative cooling.

    Args:
        epw (EPW): A ladybug EPW object.
        evaporative_cooling_effectiveness (float, optional):
            The proportion of difference between DBT and WBT by which to adjust DBT.
            Defaults to 0.3 which equates to 30% effective evaporative cooling, roughly that
            of Misting.

    Returns:
        List[HourlyContinuousCollection]:
            Adjusted dry-bulb temperature and relative humidity collections incorporating
            evaporative cooling effect.
    """

    if (evaporative_cooling_effectiveness > 1) or (
        evaporative_cooling_effectiveness < 0
    ):
        raise ValueError("evaporative_cooling_effectiveness must be between 0 and 1.")

    wbt = HourlyContinuousCollection.compute_function_aligned(
        wet_bulb_from_db_rh,
        [
            epw.dry_bulb_temperature,
            epw.relative_humidity,
            epw.atmospheric_station_pressure,
        ],
        WetBulbTemperature(),
        "C",
    )
    dbt = epw.dry_bulb_temperature.duplicate()
    dbt = dbt - ((dbt - wbt) * evaporative_cooling_effectiveness)
    dbt.header.metadata[
        "evaporative_cooling"
    ] = f"{evaporative_cooling_effectiveness:0.0%}"

    rh = epw.relative_humidity.duplicate()
    rh = (rh * (1 - evaporative_cooling_effectiveness)) + (
        evaporative_cooling_effectiveness * 100
    )
    rh.header.metadata[
        "evaporative_cooling"
    ] = f"{evaporative_cooling_effectiveness:0.0%}"

    return [dbt, rh]

