try:
    import pyomo.environ
    from pyomo.opt.base import SolverFactory
    PYOMO3 = False
except ImportError:
    import coopr.environ
    from coopr.opt.base import SolverFactory
    PYOMO3 = True
import matplotlib.pyplot as plt
import os
from pyproj import Proj, transform
from rivus.main import rivus
from rivus.gridder.create_grid import create_square_grid as SquareGrid
from rivus.gridder.extend_grid import extend_edge_data, vert_init_commodities
from rivus.utils import pandashp

# Constants - Inputs
GLOB_EPSG = 4326  # WGS84 (OSM, GoogleMaps)
PROJ_EPSG = 32632  # Munich
lat, lon = [48.13512, 11.58198]  # You can copy LatLon into this list
LONLAT_O = (lon, lat)
WGS84 = Proj(init='epsg:4326')
UTMXX = Proj(init='epsg:{}'.format(PROJ_EPSG))
ORIGOXY = transform(WGS84, UTMXX, *LONLAT_O)


# Files Access
base_directory = os.path.join('data', 'chessboard')
data_spreadsheet = os.path.join(base_directory, 'data.xlsx')

# Get Rivus Inputs
vertex, edge = SquareGrid(origo_xy=ORIGOXY, epsg=PROJ_EPSG)
pandashp.match_vertices_and_edges(vertex, edge)
vertex, edge = [gdf.to_crs(epsg=GLOB_EPSG) for gdf in (vertex, edge)]
sorts = ['residential', 'industrial']
inits = [1000, 0]
extend_edge_data(edge, sorts=sorts, inits=inits)
vert_init_commodities(vertex, ('Elec', 'Gas', 'Heat'),
                      [('Elec', 0, 100000), ('Gas', 1, 50000)])

print(edge)
print(vertex)

if True:
    # load spreadsheet data
    data = rivus.read_excel(data_spreadsheet)

    # create and solve model
    prob = rivus.create_model(data, vertex, edge)
    if PYOMO3:
        prob = prob.create()  # no longer needed in Pyomo 4<
    solver = SolverFactory('glpk')
    result = solver.solve(prob, tee=True)
    if PYOMO3:
        prob.load(result)  # no longer needed in Pyomo 4<

    # load results
    costs, Pmax, Kappa_hub, Kappa_process = rivus.get_constants(prob)
    source, flows, hub_io, proc_io, proc_tau = rivus.get_timeseries(prob)


    result_dir = os.path.join('result', os.path.basename(base_directory))

    # create result directory if not existing already
    if not os.path.exists(result_dir):
        os.makedirs(result_dir)

    rivus.save(prob, os.path.join(result_dir, 'prob.pgz'))
    rivus.report(prob, os.path.join(result_dir, 'report.xlsx'))

    # plot all caps (and demands if existing)
    for com, plot_type in [('Elec', 'caps'), ('Heat', 'caps'), ('Gas', 'caps'),
                           ('Elec', 'peak'), ('Heat', 'peak')]:
        # create plot
        fig = rivus.plot(prob, com, mapscale=False, tick_labels=False,
                         plot_demand=(plot_type == 'peak'))
        plt.title('')
        # save to file
        for ext in ['png', 'pdf']:

            # determine figure filename from plot type, commodity and extension
            fig_filename = os.path.join(
                result_dir, '{}-{}.{}').format(plot_type, com, ext)
            fig.savefig(fig_filename, dpi=300, bbox_inches='tight',
                        transparent=(ext == 'pdf'))
