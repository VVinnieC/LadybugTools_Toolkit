import sys

sys.path.insert(0, r"C:\ProgramData\BHoM\Extensions\PythonCode\LadybugTools_Toolkit")

# TODO - Add EnergyMaterialVegetation once this material is available via general release.

from typing import Dict

from honeybee_energy.material.opaque import (  # EnergyMaterialVegetation,
    EnergyMaterial,
    _EnergyMaterialOpaqueBase,
)

MATERIALS: Dict[str, _EnergyMaterialOpaqueBase] = {
    "ASPHALT": EnergyMaterial(
        identifier="ASPHALT",
        roughness="MediumRough",
        thickness=0.2,
        conductivity=0.75,
        density=2360.0,
        specific_heat=920.0,
        thermal_absorptance=0.93,
        solar_absorptance=0.87,
        visible_absorptance=0.87,
    ),
    "CONCRETE_HEAVYWEIGHT": EnergyMaterial(
        identifier="CONCRETE_HEAVYWEIGHT",
        roughness="MediumRough",
        thickness=0.2,
        conductivity=1.95,
        density=2240.0,
        specific_heat=900.0,
        thermal_absorptance=0.9,
        solar_absorptance=0.8,
        visible_absorptance=0.8,
    ),
    "CONCRETE_LIGHTWEIGHT": EnergyMaterial(
        identifier="CONCRETE_LIGHTWEIGHT",
        roughness="MediumRough",
        thickness=0.1,
        conductivity=0.53,
        density=1280.0,
        specific_heat=840.0,
        thermal_absorptance=0.9,
        solar_absorptance=0.8,
        visible_absorptance=0.8,
    ),
    "DUST_DRY": EnergyMaterial(
        identifier="DUST_DRY",
        roughness="Rough",
        thickness=0.2,
        conductivity=0.5,
        density=1600.0,
        specific_heat=1026.0,
        thermal_absorptance=0.9,
        solar_absorptance=0.7,
        visible_absorptance=0.7,
    ),
    "METAL_PAINTED": EnergyMaterial(
        identifier="METAL_PAINTED",
        roughness="Smooth",
        thickness=0.0015,
        conductivity=5.0,
        density=7690.0,
        specific_heat=410.0,
        thermal_absorptance=0.9,
        solar_absorptance=0.5,
        visible_absorptance=0.5,
    ),
    "METAL_REFLECTIVE": EnergyMaterial(
        identifier="METAL_REFLECTIVE",
        roughness="MediumSmooth",
        thickness=0.0015,
        conductivity=5.0,
        density=7680.0,
        specific_heat=418.0,
        thermal_absorptance=0.75,
        solar_absorptance=0.45,
        visible_absorptance=0.6,
    ),
    "MUD": EnergyMaterial(
        identifier="MUD",
        roughness="MediumRough",
        thickness=0.2,
        conductivity=1.4,
        density=1840.0,
        specific_heat=1480.0,
        thermal_absorptance=0.95,
        solar_absorptance=0.8,
        visible_absorptance=0.8,
    ),
    "ROCK": EnergyMaterial(
        identifier="ROCK",
        roughness="MediumRough",
        thickness=0.2,
        conductivity=3.0,
        density=2700.0,
        specific_heat=790.0,
        thermal_absorptance=0.96,
        solar_absorptance=0.55,
        visible_absorptance=0.55,
    ),
    "SAND_DRY": EnergyMaterial(
        identifier="SAND_DRY",
        roughness="Rough",
        thickness=0.2,
        conductivity=0.33,
        density=1555.0,
        specific_heat=800.0,
        thermal_absorptance=0.85,
        solar_absorptance=0.65,
        visible_absorptance=0.65,
    ),
    "SOIL_DAMP": EnergyMaterial(
        identifier="SOIL_DAMP",
        roughness="Rough",
        thickness=0.2,
        conductivity=1.0,
        density=1250.0,
        specific_heat=1252.0,
        thermal_absorptance=0.92,
        solar_absorptance=0.75,
        visible_absorptance=0.75,
    ),
    "SOFTWOOD": EnergyMaterial(
        identifier="SOFTWOOD",
        roughness="MediumSmooth",
        thickness=0.0254,
        conductivity=0.129,
        density=496.0,
        specific_heat=1630.0,
        thermal_absorptance=0.9,
        solar_absorptance=0.65,
        visible_absorptance=0.65,
    ),
    "HARDWOOD": EnergyMaterial(
        identifier="HARDWOOD",
        roughness="MediumSmooth",
        thickness=0.0254,
        conductivity=0.167,
        density=680.0,
        specific_heat=1630.0,
        thermal_absorptance=0.9,
        solar_absorptance=0.7,
        visible_absorptance=0.7,
    ),
    "FABRIC": EnergyMaterial(
        identifier="FABRIC",
        roughness="Smooth",
        thickness=0.002,
        conductivity=0.06,
        density=500.0,
        specific_heat=1800.0,
        thermal_absorptance=0.89,
        solar_absorptance=0.5,
        visible_absorptance=0.5,
    ),
    # "GRASS_DAMP": EnergyMaterialVegetation(
    #     identifier="GRASS_DAMP",
    #     roughness="MediumRough",
    #     thickness=0.1,
    #     conductivity=0.35,
    #     density=1100,
    #     specific_heat=1252,
    #     soil_thermal_absorptance=0.92,
    #     soil_solar_absorptance=0.7,
    #     soil_visible_absorptance=0.7,
    #     plant_height=0.2,
    #     leaf_area_index=1.71,
    #     leaf_reflectivity=0.25,
    #     leaf_emissivity=0.92,
    #     min_stomatal_resist=160,
    # ),
    # "GRASS_DRY": EnergyMaterialVegetation(
    #     identifier="GRASS_DRY",
    #     roughness="Rough",
    #     thickness=0.1,
    #     conductivity=0.3,
    #     density=1100,
    #     specific_heat=1252,
    #     soil_thermal_absorptance=0.89,
    #     soil_solar_absorptance=0.75,
    #     soil_visible_absorptance=0.75,
    #     plant_height=0.2,
    #     leaf_area_index=1.71,
    #     leaf_reflectivity=0.19,
    #     leaf_emissivity=0.95,
    #     min_stomatal_resist=180,
    # ),
    # "SHRUBS": EnergyMaterialVegetation(
    #     identifier="GRASS_DRY",
    #     roughness="Rough",
    #     thickness=0.1,
    #     conductivity=0.35,
    #     density=1260,
    #     specific_heat=1100,
    #     soil_thermal_absorptance=0.9,
    #     soil_solar_absorptance=0.7,
    #     soil_visible_absorptance=0.7,
    #     plant_height=0.2,
    #     leaf_area_index=2.08,
    #     leaf_reflectivity=0.21,
    #     leaf_emissivity=0.95,
    #     min_stomatal_resist=180,
    # ),
}


def material_from_string(material_string: str) -> _EnergyMaterialOpaqueBase:
    """
    Return the EnergyMaterial object associated with the given string.
    """
    try:
        return MATERIALS[material_string]
    except KeyError:
        raise ValueError(
            f"Unknown material: {material_string}. Choose from one of {list(MATERIALS.keys())}."
        )


if __name__ == "__main__":
    pass