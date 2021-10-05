﻿/*
 * This file is part of the Buildings and Habitats object Model (BHoM)
 * Copyright (c) 2015 - 2021, the respective contributors. All rights reserved.
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

using BH.oM.LadybugTools;
using BH.oM.Reflection.Attributes;

using System.Collections.Generic;
using System.ComponentModel;
using System.IO;

namespace BH.Engine.LadybugTools
{
    public static partial class Query
    {
        [Description("Create an AnnualResult object from a file containing value-per-timestep-per-point results generated using Honeybee-Radiance.")]
        [Input("illFile", "A file containing timestep results (one value-per-timestep-per-point), generated by a Radiance simulation.")]
        [Input("sunUpHoursFile", "A file containing integers denoting the hours of the year represented in the illFile.")]
        [Output("annualResult", "An AnnualResult object.")]
        public static AnnualRadianceResult AnnualRadianceResult(string illFile, string sunUpHoursFile)
        {
            AnnualRadianceResult annualResult = new AnnualRadianceResult
            {
                Name = Path.GetFileNameWithoutExtension(illFile)
            };

            List<int> sunUpHours = new List<int>();
            foreach (string line in File.ReadAllLines(sunUpHoursFile))
            {
                sunUpHours.Add((int)System.Math.Floor(double.Parse(line)));
            }

            foreach (string line in File.ReadAllLines(illFile))
            {
                List<double> sensorValues = new List<double>();
                int n = 0;
                string[] vals = line.Split(new char[] { '\t', ',', ' ' }, System.StringSplitOptions.RemoveEmptyEntries);
                for (int i = 0; i < 8760; i++)
                {
                    if (sunUpHours.Contains(i))
                    {
                        sensorValues.Add(double.Parse(vals[n]));
                        n++;
                    }
                    else
                    {
                        sensorValues.Add(0);
                    }
                }
                annualResult.Results.Add(sensorValues);
            }

            return annualResult;
        }
    }
}
