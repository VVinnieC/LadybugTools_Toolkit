import warnings

import matplotlib.pyplot as plt
import numpy as np
import pytest
from ladybug.analysisperiod import AnalysisPeriod
from ladybug.epw import EPW
from ladybug_comfort.collection.utci import UTCI
from ladybugtools_toolkit.external_comfort.material import Materials
from ladybugtools_toolkit.helpers import create_triangulation, lighten_color
from ladybugtools_toolkit.ladybug_extension.datacollection import collection_to_series
from ladybugtools_toolkit.plot import (
    colormap_sequential,
    heatmap,
    sunpath,
    timeseries_diurnal,
    utci_heatmap,
    utci_heatmap_difference,
    utci_journey,
    utci_pie,
    week_profile,
    windrose,
)
from ladybugtools_toolkit.plot.spatial_heatmap import spatial_heatmap
from ladybugtools_toolkit.plot.utci_comparison_diurnal import utci_comparison_diurnal
from ladybugtools_toolkit.plot.utci_day_comfort_metrics import utci_day_comfort_metrics
from ladybugtools_toolkit.plot.utci_distance_to_comfortable import (
    utci_distance_to_comfortable,
)
from ladybugtools_toolkit.plot.utci_heatmap_histogram import utci_heatmap_histogram

from . import EPW_FILE

EPW_OBJ = EPW(EPW_FILE)

GROUND_MATERIAL = Materials.LBT_AsphaltPavement.value
LB_UTCI_COLLECTION = UTCI(
    EPW_OBJ.dry_bulb_temperature,
    EPW_OBJ.relative_humidity,
    EPW_OBJ.dry_bulb_temperature,
    EPW_OBJ.wind_speed,
).universal_thermal_climate_index


def test_colormap_sequential():
    """_"""
    assert sum(colormap_sequential("red", "green", "blue")(0.25)) == pytest.approx(
        1.750003844675125, rel=0.01
    )


def test_create_triangulation():
    """_"""
    x = np.linspace(0, 100, 101)
    y = np.linspace(0, 100, 101)
    xx, yy = np.meshgrid(x, y)
    assert create_triangulation(xx.flatten(), yy.flatten()).x.shape == (10201,)


def test_lighten_color():
    """_"""
    assert sum(lighten_color("#000444")) == pytest.approx(1.3176470588235292, rel=0.01)


def test_spatial_heatmap():
    """_"""
    x = np.linspace(0, 100, 101)
    y = np.linspace(0, 100, 101)
    xx, yy = np.meshgrid(x, y)
    zz = (np.sin(xx) * np.cos(yy)).flatten()
    tri = create_triangulation(xx.flatten(), yy.flatten())
    assert isinstance(spatial_heatmap([tri], [zz], contours=[0]), plt.Figure)
    plt.close("all")


def test_sunpath():
    """_"""
    assert isinstance(
        sunpath(
            EPW_OBJ,
            analysis_period=AnalysisPeriod(
                st_month=3, end_month=4, st_hour=9, end_hour=18
            ),
            data_collection=EPW_OBJ.dry_bulb_temperature,
            cmap="inferno",
        ),
        plt.Axes,
    )
    plt.close("all")


def test_timeseries_diurnal():
    """_"""
    assert isinstance(
        timeseries_diurnal(collection_to_series(EPW_OBJ.dry_bulb_temperature)), plt.Axes
    )
    plt.close("all")


def test_timeseries_heatmap():
    """_"""
    assert isinstance(
        heatmap(collection_to_series(EPW_OBJ.dry_bulb_temperature)), plt.Axes
    )
    plt.close("all")


def test_utci_comparison_diurnal():
    """_"""
    assert isinstance(
        utci_comparison_diurnal([LB_UTCI_COLLECTION - 12, LB_UTCI_COLLECTION]),
        plt.Figure,
    )
    plt.close("all")


def test_utci_day_comfort_metrics():
    """_"""
    assert isinstance(
        utci_day_comfort_metrics(
            collection_to_series(LB_UTCI_COLLECTION),
            collection_to_series(EPW_OBJ.dry_bulb_temperature),
            collection_to_series(EPW_OBJ.dry_bulb_temperature).rename(
                "Mean Radiant Temperature (C)"
            ),
            collection_to_series(EPW_OBJ.relative_humidity),
            collection_to_series(EPW_OBJ.wind_speed),
            month=6,
            day=21,
        ),
        plt.Figure,
    )
    plt.close("all")


def test_utci_distance_to_comfortable():
    """_"""
    assert isinstance(utci_distance_to_comfortable(LB_UTCI_COLLECTION), plt.Figure)
    plt.close("all")


def test_utci_heatmap_difference():
    """_"""
    assert isinstance(
        utci_heatmap_difference(LB_UTCI_COLLECTION, LB_UTCI_COLLECTION - 3), plt.Axes
    )
    plt.close("all")


def test_utci_heatmap_histogram():
    """_"""
    assert isinstance(utci_heatmap_histogram(LB_UTCI_COLLECTION), plt.Figure)
    plt.close("all")


def test_utci_heatmap():
    """_"""
    assert isinstance(utci_heatmap(LB_UTCI_COLLECTION), plt.Axes)
    plt.close("all")


def test_utci_journey():
    """_"""
    assert isinstance(
        utci_journey(
            utci_values=(10, 30, 15, 0),
            ax=None,
            names=("A", "B", "C", "D"),
            curve=True,
            ylims=(-10, 50),
            show_legend=True,
            title="Hey there",
            show_grid=True,
        ),
        plt.Axes,
    )
    plt.close("all")


def test_week_profile():
    """_"""
    assert isinstance(
        week_profile(collection_to_series(EPW_OBJ.dry_bulb_temperature)), plt.Axes
    )
    plt.close("all")


def test_windrose():
    """_"""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert isinstance(
            windrose(
                EPW_OBJ,
                EPW_OBJ.wind_speed,
                None,
                AnalysisPeriod(st_month=3, end_month=11),
            ),
            plt.Axes,
        )
    plt.close("all")


# def test_fisheye_sky():
#     """_"""
#     model = create_model(
#         GROUND_MATERIAL.to_lbt(), GROUND_MATERIAL.to_lbt(), EXTERNAL_COMFORT_IDENTIFIER
#     )
#     img = fisheye_sky(model, Point3D(0, 0, 1.2))
#     assert isinstance(img, Image)
#     img.close()


# def test_skymatrix():
#     """_"""
#     assert isinstance(skymatrix(EPW_OBJ), plt.Figure)
#     plt.close("all")


def test_utci_pie():
    """_"""
    assert isinstance(utci_pie(LB_UTCI_COLLECTION), plt.Axes)
    plt.close("all")
