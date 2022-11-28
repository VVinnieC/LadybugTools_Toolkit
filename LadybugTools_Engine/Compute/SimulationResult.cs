/*
 * This file is part of the Buildings and Habitats object Model (BHoM)
 * Copyright (c) 2015 - 2022, the respective contributors. All rights reserved.
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

using BH.Engine.Python;
using BH.oM.Python;
using BH.oM.Base.Attributes;
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Linq;
using BH.oM.Base;
using System.IO;
using BH.oM.LadybugTools;
using BH.Engine.Serialiser;

namespace BH.Engine.LadybugTools
{
    public static partial class Compute
    {
        [Description("Run a simulation and return results.")]
        [Input("epwFile", "An EPW file.")]
        [Input("groundMaterial", "A ground material.")]
        [Input("shadeMaterial", "A shade material.")]
        [Output("simulationResult", "An simulation result object containing simulation results.")]
        public static SimulationResult SimulationResult(string epwFile, ILBTMaterial groundMaterial, ILBTMaterial shadeMaterial)
        {
            // construct the base object
            SimulationResult simulationResult = new SimulationResult()
            {
                EpwFile = Path.GetFullPath(epwFile).Replace(@"\", "/"),
                GroundMaterial = groundMaterial,
                ShadeMaterial = shadeMaterial,
                Identifier = Create.SimulationId(epwFile, groundMaterial, shadeMaterial)
            };

            // send to Python to simulate/load
            string simulationResultJsonStr = System.Text.RegularExpressions.Regex.Unescape(simulationResult.ToJson());
            BH.oM.Python.PythonEnvironment env = Compute.InstallPythonEnv_LBT(true);
            string pythonScript = string.Join("\n", new List<string>()
            {
                "try:",
                "    import json",
                "    from ladybugtools_toolkit.external_comfort.simulate import SimulationResult",
                $"    simulation_result = SimulationResult.from_json('{simulationResultJsonStr}').run()",
                "    print(simulation_result.to_json())",
                "except Exception as exc:",
                "    print(json.dumps({'error': str(exc)}))",
            });
            string output = env.RunPythonString(pythonScript).Trim().Split(new string[] { "\r\n", "\r", "\n" }, StringSplitOptions.None).Last();

            // reload from Python results
            return (SimulationResult)Serialiser.Convert.FromJson(output);
        }
    }
}
