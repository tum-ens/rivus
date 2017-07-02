# rivus

rivus is a [mixed integer linear programming](https://en.wikipedia.org/wiki/Integer_programming) optimisation model for capacity planning for energy infrastructure networks. Its name, latin for stream or canal, stems from its origin as a companion model for [urbs](https://github.com/tum-ens/urbs), an optimisation model for urban energy systems. This model shares the same structure as urbs, so please refer to its introduction/tutorial for now or dive directly into the code.  

## Features

  * rivus is a mixed integer linear programming model for multi-commodity energy infrastructure networks systems with a focus on high spatial resolution.
  * It finds the minimum cost energy infrastructure networks to satisfy a given energy distribution for possibly multiple commodities (e.g. electricity, heating, cooling, ...).
  * Time is represented by a (small) set of weighted time steps that represent peak or typical loads  
  * Spatial data can be provided in form of shapefiles, while technical parameters can be edited in a spreadsheet.
  * The model itself is written using [Pyomo](https://software.sandia.gov/trac/coopr/wiki/Pyomo) and includes reporting and plotting functionality. 

## Screenshots

Electricity network capacities|  Heat network capacities    |  Gas network capacities
:----------------------------:|:---------------------------:|:---------------------------:
![](doc/img/caps-elec.png)    |  ![](doc/img/caps-heat.png) |  ![](doc/img/caps-gas.png)

## Installation

### Windows

1. [**Anaconda (Python 3.6)**](http://continuum.io/downloads). Choose the 64-bit installer if possible.

2. **Pyomo** and **GLPK**
   1. Launch a new command prompt (Win+R, type "cmd", Enter)
   2. Type `conda install -c conda-forge pyomo glpk`, hit Enter.

3. Add **shapefile support**:
   ```
   conda install -c conda-forge pyshp shapely basemap
   ```

4. Get **geopandas** and its dependencies:
   ```
   conda install -c conda-forge pyproj fiona geopy geopandas
   ```

## Documentation / Tutorials

  * [Official documentation](http://rivus.readthedocs.io/en/latest/) (still a skeleton only)
  * List of helpful IPython notebooks on handling geographic input data:
    + [join data from building.shp and edge.shp](https://gist.github.com/lnksz/6edcd0a877997e9365e808146e9b51fe)
    + [OSM street data to vertex.shp and edge.shp](https://gist.github.com/lnksz/7977c4cff9c529ca137b67b6774c60d7)
    + [Square grid to vertex.shp and edge.shp](https://gist.github.com/lnksz/bd8ce0a79e499479b61ea7b45d5c661d)

## Copyright

Copyright (C) 2015-2017  Johannes Dorfner

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
