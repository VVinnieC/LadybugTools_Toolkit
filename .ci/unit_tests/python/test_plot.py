import warnings

import matplotlib.pyplot as plt
import numpy as np
import pytest
from ladybug.analysisperiod import AnalysisPeriod
from ladybug_comfort.collection.utci import UTCI
from ladybug_geometry.geometry3d import Point3D
from ladybugtools_toolkit.external_comfort.model.create_model import create_model
from ladybugtools_toolkit.ladybug_extension.datacollection.to_series import to_series
from ladybugtools_toolkit.plot.colormap_sequential import colormap_sequential
from ladybugtools_toolkit.plot.create_triangulation import create_triangulation
from ladybugtools_toolkit.plot.fisheye_sky import fisheye_sky
from ladybugtools_toolkit.plot.lighten_color import lighten_color
from ladybugtools_toolkit.plot.skymatrix import skymatrix
from ladybugtools_toolkit.plot.spatial_heatmap import spatial_heatmap
from ladybugtools_toolkit.plot.sunpath import sunpath
from ladybugtools_toolkit.plot.timeseries_diurnal import timeseries_diurnal
from ladybugtools_toolkit.plot.timeseries_heatmap import timeseries_heatmap
from ladybugtools_toolkit.plot.utci_comparison_diurnal import utci_comparison_diurnal
from ladybugtools_toolkit.plot.utci_day_comfort_metrics import utci_day_comfort_metrics
from ladybugtools_toolkit.plot.utci_distance_to_comfortable import (
    utci_distance_to_comfortable,
)
from ladybugtools_toolkit.plot.utci_heatmap import utci_heatmap
from ladybugtools_toolkit.plot.utci_heatmap_difference import utci_heatmap_difference
from ladybugtools_toolkit.plot.utci_heatmap_histogram import utci_heatmap_histogram
from ladybugtools_toolkit.plot.utci_journey import utci_journey
from ladybugtools_toolkit.plot.utci_pie import utci_pie
from ladybugtools_toolkit.plot.week_profile import week_profile
from ladybugtools_toolkit.plot.windrose import windrose
from PIL.Image import Image

from . import EPW_OBJ, GROUND_MATERIAL

LB_UTCI_COLLECTION = UTCI(
    EPW_OBJ.dry_bulb_temperature,
    EPW_OBJ.relative_humidity,
    EPW_OBJ.dry_bulb_temperature,
    EPW_OBJ.wind_speed,
).universal_thermal_climate_index


def test_colormap_sequential():
    assert sum(colormap_sequential("red", "green", "blue")(0.25)) == pytest.approx(
        1.750003844675125, rel=0.01
    )


def test_create_triangulation():
    x = np.linspace(0, 100, 101)
    y = np.linspace(0, 100, 101)
    xx, yy = np.meshgrid(x, y)
    assert create_triangulation(xx.flatten(), yy.flatten()).x.shape == (10201,)


def test_lighten_color():
    assert sum(lighten_color("#000444")) == pytest.approx(1.3176470588235292, rel=0.01)


def test_spatial_heatmap():
    x = np.linspace(0, 100, 101)
    y = np.linspace(0, 100, 101)
    xx, yy = np.meshgrid(x, y)
    zz = (np.sin(xx) * np.cos(yy)).flatten()
    tri = create_triangulation(xx.flatten(), yy.flatten())
    assert isinstance(spatial_heatmap([tri], [zz], contours=[0]), plt.Figure)
    plt.close("all")


def test_sunpath():
    assert isinstance(
        sunpath(
            EPW_OBJ,
            analysis_period=AnalysisPeriod(
                st_month=3, end_month=4, st_hour=9, end_hour=18
            ),
            data_collection=EPW_OBJ.dry_bulb_temperature,
            cmap="inferno",
        ),
        plt.Figure,
    )
    plt.close("all")


def test_timeseries_diurnal():
    assert isinstance(
        timeseries_diurnal(to_series(EPW_OBJ.dry_bulb_temperature)), plt.Figure
    )
    plt.close("all")


def test_timeseries_heatmap():
    assert isinstance(
        timeseries_heatmap(to_series(EPW_OBJ.dry_bulb_temperature)), plt.Figure
    )
    plt.close("all")


def test_utci_comparison_diurnal():
    assert isinstance(
        utci_comparison_diurnal([LB_UTCI_COLLECTION - 12, LB_UTCI_COLLECTION]),
        plt.Figure,
    )
    plt.close("all")


def test_utci_day_comfort_metrics():
    assert isinstance(
        utci_day_comfort_metrics(
            to_series(LB_UTCI_COLLECTION),
            to_series(EPW_OBJ.dry_bulb_temperature),
            to_series(EPW_OBJ.dry_bulb_temperature).rename(
                "Mean Radiant Temperature (C)"
            ),
            to_series(EPW_OBJ.relative_humidity),
            to_series(EPW_OBJ.wind_speed),
            month=6,
            day=21,
        ),
        plt.Figure,
    )
    plt.close("all")


def test_utci_distance_to_comfortable():
    assert isinstance(utci_distance_to_comfortable(LB_UTCI_COLLECTION), plt.Figure)
    plt.close("all")


def test_utci_heatmap_difference():
    assert isinstance(
        utci_heatmap_difference(LB_UTCI_COLLECTION, LB_UTCI_COLLECTION - 3), plt.Figure
    )
    plt.close("all")


def test_utci_heatmap_histogram():
    assert isinstance(utci_heatmap_histogram(LB_UTCI_COLLECTION), plt.Figure)
    plt.close("all")


def test_utci_heatmap():
    assert isinstance(utci_heatmap(LB_UTCI_COLLECTION), plt.Figure)
    plt.close("all")


def test_utci_journey():
    assert isinstance(
        utci_journey([10, 30, 15, 0], ["A", "B", "C", "D"], curve=True), plt.Figure
    )
    plt.close("all")


def test_week_profile():
    assert isinstance(week_profile(to_series(EPW_OBJ.dry_bulb_temperature)), plt.Figure)
    plt.close("all")


def test_windrose():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert isinstance(
            windrose(
                EPW_OBJ, EPW_OBJ.wind_speed, AnalysisPeriod(st_month=3, end_month=11)
            ),
            plt.Figure,
        )
    plt.close("all")


def test_fisheye_sky():
    model = create_model(GROUND_MATERIAL, GROUND_MATERIAL, "pytest")
    img = fisheye_sky(model, Point3D(0, 0, 1.2))
    assert isinstance(img, Image)
    img.close()


def test_skymatrix():
    assert isinstance(skymatrix(EPW_OBJ), plt.Figure)
    plt.close("all")


def test_utci_pie():
    assert isinstance(utci_pie(LB_UTCI_COLLECTION), plt.Figure)
    plt.close("all")
