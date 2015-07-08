# rivus

rivus is a [mixed integer linear programming](https://en.wikipedia.org/wiki/Integer_programming) optimisation model for capacity planning for energy infrastructure networks. Its name, latin for stream or canal, stems from its origin as a companion model for [urbs](https://github.com/tum-ens/urbs), an optimisation model for urban energy systems. This model shares the same structure as urbs, so please refer to its introduction/tutorial for now or dive directly into the code.  

## Features

  * rivus is a mixed integer linear programming model for multi-commodity energy infrastructure networks systems with a focus on high spatial resolution.
  * It finds the minimum cost energy infrastructure networks to satisfy a given energy distribution for possibly multiple commodities (e.g. electricity, heating, cooling, ...).
  * Time is represented by a (small) set of weighted time steps that represent peak or typical loads  
  * Spatial data can be provided in form of shapefiles, while technical parameters can be edited in a spreadsheet.
  * The model itself is written using  [Coopr](https://software.sandia.gov/trac/coopr)/[Pyomo](https://software.sandia.gov/trac/coopr/wiki/Pyomo) and includes reporting and plotting functionality. 

## Screenshots

<a href="doc/img/caps-elec.png"><img src="doc/img/caps-elec.png" alt="Electricity network capacities" style="width:400px"></a>
<a href="doc/img/caps-heat.png"><img src="doc/img/caps-heat.png" alt="Heat network capacities" style="width:400px"></a>
<a href="doc/img/caps-gas.png"><img src="doc/img/caps-gas.png" alt="Gas network capacities" style="width:400px"></a>

  
## Dependencies
  
  * [Python 2.7](https://python.org/download). On Windows, use [Anaconda](http://continuum.io/anaconda) and its `conda` packet manager (use `pip` only if a package cannot be found or is outdated in `conda` repository)
  * Coopr/Pyomo version 3.5.x (version 4 support planned): `pip install coopr==3.5.8787`
  * SciPy stack (NumPy, SciPy, matplotlib) (included in Anaconda)
  * [pandas](http://pandas.pydata.org/), including xlrd, xlwt, openpyxl for Excel I/O (included in Anaconda)
  * [mpl_toolkit.basemap](http://matplotlib.org/basemap/) (for result map generation)
  * Any solver supported by Pyomo (recommended: [Gurobi](http://gurobi.com/))

  
## Copyright

Copyright (C) 2015  Johannes Dorfner

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>