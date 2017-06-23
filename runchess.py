try:
    import pyomo.environ
    from pyomo.opt.base import SolverFactory
    PYOMO3 = False
except ImportError:
    import coopr.environ
    from coopr.opt.base import SolverFactory
    PYOMO3 = True
import os
from datetime import datetime
from pyproj import Proj, transform
import matplotlib.pyplot as plt
from plotly.offline import plot as plot3d

from rivus.main import rivus
from rivus.gridder import create_square_grid, extend_edge_data, vert_init_commodities
from rivus.utils.prerun import setup_solver
from rivus.io.plot import fig3d


# Constants - Inputs
GLOB_EPSG = 4326  # WGS84 (OSM, GoogleMaps, rivus.main)
PROJ_EPSG = 32632  # Munich
lat, lon = [48.13512, 11.58198]  # You can copy LatLon into this list
LONLAT_O = (lon, lat)
WGS84 = Proj(init='epsg:4326')
# UTMXX = Proj(init='epsg:{}'.format(PROJ_EPSG))
# UTMXX = Proj(proj='utm', zone='32', ellps='WGS84')
UTMXX = Proj("+proj=utm +zone=32U, +north +ellps=WGS84 +datum=WGS84 +units=m +no_defs")
# ORIGOXY = transform(WGS84, UTMXX, *LONLAT_O)
ORIGOXY = UTMXX(*LONLAT_O)


# Files Access
now = datetime.now().strftime('%y%m%dT%H%M')
proj_name = 'chessboard'
base_directory = os.path.join('data', proj_name)
data_spreadsheet = os.path.join(base_directory, 'data.xlsx')
result_dir = os.path.join('result', '{}-{}'.format(proj_name, now))
prob_dir = os.path.join('result', proj_name)
# create result directory if not existing already
if not os.path.exists(result_dir):
    os.makedirs(result_dir)

# Solve[True] or Load[False] an already solved model
SOLVER = False

if SOLVER:
    # Get Rivus Inputs
    vertex, edge = create_square_grid(origo_xy=ORIGOXY, epsg=PROJ_EPSG, num_edge_x=4)
    vertex, edge = [gdf.to_crs(epsg=GLOB_EPSG) for gdf in (vertex, edge)]
    # sorts = ['residential']
    # inits = [100]
    # extend_edge_data(edge, sorts=sorts, inits=inits)
    extend_edge_data(edge)  # only residential, with 1000 kW init
    vert_init_commodities(vertex, ('Elec', 'Gas', 'Heat'),
                          [('Elec', 6, 100000), ('Gas', 6, 5000)])
    # load spreadsheet data
    data = rivus.read_excel(data_spreadsheet)

    # create and solve model
    prob = rivus.create_model(data, vertex, edge)
    if PYOMO3:
        prob = prob.create()  # no longer needed in Pyomo 4<
    solver = SolverFactory('gurobi')
    solver = setup_solver(solver)
    result = solver.solve(prob, tee=True)
    if PYOMO3:
        prob.load(result)  # no longer needed in Pyomo 4<
    
    print('Saving pickle...')
    rivus.save(prob, os.path.join(result_dir, 'prob.pgz'))
    print('Pickle saved')
    rivus.report(prob, os.path.join(result_dir, 'report.xlsx'))
else:
    print('Loading pickled modell...')
    prob = rivus.load(os.path.join(prob_dir, 'prob.pgz'))
    print('Loaded.')

# Plotting
# rivus.result_figures(prob, os.path.join(result_dir, 'figs/'))
print("Plotting...")
plotcomms = ['Gas', 'Heat', 'Elec']
fig = fig3d(prob, plotcomms, linescale=7)
plot3d(fig, filename=os.path.join(result_dir, 'rivus_result.html'))
print("Plotted")
