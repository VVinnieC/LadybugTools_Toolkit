/*
 * This file is part of the Buildings and Habitats object Model (BHoM)
 * Copyright (c) 2015 - 2023, the respective contributors. All rights reserved.
 *
 * Each contributor holds copyright over their respective contributions.
 * The project versioning (Git) records all such contribution source information.
 *                                           
 *                                                                              
 * The BHoM is free software: you can redistribute it and/or modify         
 * it under the terms of the GNU Lesser General Public License as published by  
 * the Free Software Foundation, either version 3.0 of the License, or          
 * (at your option) any later version.                                          
 *                                                                              
 * The BHoM is distributed in the hope that it will be useful,              
 * but WITHOUT ANY WARRANTY; without even the implied warranty of               
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the                 
 * GNU Lesser General Public License for more details.                          
 *                                                                            
 * You should have received a copy of the GNU Lesser General Public License     
 * along with this code. If not, see <https://www.gnu.org/licenses/lgpl-3.0.html>.      
 */


using BH.oM.Base;
using System.ComponentModel;

namespace BH.oM.LadybugTools
{
    public class OpaqueVegetationMaterial : ILadybugToolsMaterial
    {
        [Description("The name of this EnergyMaterialVegetation.")]
        public virtual string Identifier { get; set; } = "Generic Opaque Vegetation Material";
        
        [Description("The source for this object and it's properties.")]
        public virtual string Source { get; set; } = string.Empty;

        [Description("The roughness of the material.")]
        public virtual Roughness Roughness { get; set; } = Roughness.MediumRough;

        [Description("Thickness of material (m).")]
        public virtual double Thickness { get; set; } = 0.1;

        [Description("Conductivity of material (W/mK).")]
        public virtual double Conductivity { get; set; } = 0.35;

        [Description("Density of material (kg/m3).")]
        public virtual double Density { get; set; } = 1100;

        [Description("Specific heat capacity of material (J/kgK).")]
        public virtual double SpecificHeat { get; set; } = 1200;

        [Description("A number between 0 and 1 for the fraction of incident long wavelength radiation that is absorbed by the soil material.")]
        public virtual double SoilThermalAbsorptance { get; set; } = 0.9;

        [Description("A number between 0 and 1 for the fraction of incident solar radiation absorbed by the soil material.")]
        public virtual double SoilSolarAbsorptance { get; set; } = 0.7;

        [Description("A number between 0 and 1 for the fraction of incident visible wavelength radiation absorbed by the soil material.")]
        public virtual double SoilVisibleAbsorptance { get; set; } = 0.7;

        [Description("A number between 0.005 and 1.0 for the height of plants in the vegetation layer [m].")]
        public virtual double PlantHeight { get; set; } = 0.2;

        [Description("A number between 0.001 and 5.0 for the projected leaf area per unit area of soil surface (aka. Leaf Area Index or LAI). Note that the fraction of vegetation cover is calculated directly from LAI using an empirical relation.")]
        public virtual double LeafAreaIndex { get; set; } = 1.0;

        [Description("A number between 0.05 and 0.5 for the fraction of incident solar radiation that is reflected by the leaf surfaces. Solar radiation includes the visible spectrum as well as infrared and ultraviolet wavelengths. Typical values are 0.18 to 0.25.")]
        public virtual double LeafReflectivity { get; set; } = 0.22;

        [Description("A number between 0.8 and 1.0 for the ratio of thermal radiation emitted from leaf surfaces to that emitted by an ideal black body at the same temperature.")]
        public virtual double LeafEmissivity { get; set; } = 0.95;

        [Description("A number between 50 and 300 for the resistance of the plants to moisture transport [s/m]. Plants with low values of stomatal resistance will result in higher evapotranspiration rates than plants with high resistance.")]
        public virtual double MinStomatalResist { get; set; } = 180;
    }
}

