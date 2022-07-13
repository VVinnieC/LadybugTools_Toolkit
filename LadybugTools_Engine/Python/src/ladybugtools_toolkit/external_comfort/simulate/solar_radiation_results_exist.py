from honeybee.model import Model
from ladybug.epw import EPW

from ...ladybug_extension.epw import equality as epw_eq
from ..model import equality as model_eq
from .working_directory import working_directory as wd


def solar_radiation_results_exist(model: Model, epw: EPW = None) -> bool:
    """Check whether results already exist for this configuration of model and EPW.

    Args:
        model (Model): The model to check for.
        epw (EPW): The EPW to check for. Currently unused.

    Returns:
        bool: True if the model and EPW have already been simulated, False otherwise.
    """
    working_directory = wd(model)

    # Try to load existing HBJSON file and check that it matches
    try:
        existing_model = Model.from_hbjson(
            (
                working_directory
                / "annual_irradiance"
                / f"{working_directory.stem}.hbjson"
            ).as_posix()
        )
        models_match = model_eq(model, existing_model, include_identifier=True)
    except (FileNotFoundError, AssertionError) as e:
        return False

    # Check that the output files necessary to reload exist
    results_exist = all(
        [
            (
                working_directory / "annual_irradiance/results/direct/UNSHADED.ill"
            ).exists(),
            (
                working_directory / "annual_irradiance/results/total/UNSHADED.ill"
            ).exists(),
        ]
    )

    return all([models_match, results_exist])
