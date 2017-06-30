try:
    import pyomo.environ
    from pyomo.opt.base import SolverFactory
    PYOMO3 = False
except ImportError:
    import coopr.environ
    from coopr.opt.base import SolverFactory
    PYOMO3 = True
import os
import matplotlib.pyplot as plt
from datetime import datetime
from pyproj import Proj, transform
from plotly.offline import plot as plot3d
from time import time as timenow
from pandas import Series

from rivus.main import rivus
from rivus.gridder import create_square_grid, extend_edge_data, vert_init_commodities
from rivus.utils.prerun import setup_solver
from rivus.io.plot import fig3d


# Constants - Inputs
lat, lon = [48.13512, 11.58198]  # You can copy LatLon into this list
SOLVER = False
# ---- Solver = True to create and solve new problem
# ---- Solver = False to load an already solved model and investigate it

# Files Access
datenow = datetime.now().strftime('%y%m%dT%H%M')
proj_name = 'chessboard'
base_directory = os.path.join('data', proj_name)
data_spreadsheet = os.path.join(base_directory, 'data.xlsx')
result_dir = os.path.join('result', '{}-{}'.format(proj_name, datenow))
prob_dir = os.path.join('result', proj_name)
profile_log = {}



if SOLVER:
    # Create Rivus Inputs
    creategrid = timenow()
    vertex, edge = create_square_grid(origo_latlon=(lat, lon), num_edge_x=4, dx=1000)
    profile_log['grid creation'] = round(timenow() - creategrid, 2)
    
    extendgrid = timenow()
    extend_edge_data(edge)  # only residential, with 1000 kW init
    vert_init_commodities(vertex, ('Elec', 'Gas', 'Heat'),
                          [('Elec', 0, 100000), ('Gas', 0, 5000)])
    profile_log['grid data'] = timenow() - extendgrid
    # ---- load spreadsheet data
    excelread = timenow()
    data = rivus.read_excel(data_spreadsheet)
    profile_log['excel read'] = timenow() - excelread

    # Create and solve model
    rivusmain = timenow()
    prob = rivus.create_model(data, vertex, edge)
    profile_log['rivus main'] = timenow() - rivusmain

    if PYOMO3:
        prob = prob.create()  # no longer needed in Pyomo 4<
    solver = SolverFactory('gurobi')
    solver = setup_solver(solver)
    startsolver = timenow()
    result = solver.solve(prob, tee=True)
    if PYOMO3:
        prob.load(result)  # no longer needed in Pyomo 4<
    profile_log['solver'] = timenow() - startsolver

    # Handling results
    # ---- create result directory if not existing already
    if not os.path.exists(result_dir):
        os.makedirs(result_dir)

    print('Saving pickle...'); rivuspickle = timenow()
    rivus.save(prob, os.path.join(result_dir, 'prob.pgz'))
    profile_log['save data'] = timenow() - rivuspickle
    print('Pickle saved')
    rivusreport = timenow()
    rivus.report(prob, os.path.join(result_dir, 'report.xlsx'))
    profile_log['rivus report'] = timenow() - rivusreport
else:
    print('Loading pickled modell...')
    arch_dir = os.path.join('result', 'chessboard-170626T1331')
    arch_path = os.path.join(arch_dir, 'prob.pgz')
    rivusload = timenow()
    prob = rivus.load(arch_path)
    profile_log['rivus load'] = timenow() - rivusload
    print('Loaded.')

# Plotting
# rivus.result_figures(prob, os.path.join(result_dir, 'figs/'))
print("Plotting..."); myprintstart = timenow()
plotcomms = ['Gas', 'Heat', 'Elec']
fig = fig3d(prob, plotcomms, linescale=8, usehubs=True)
if SOLVER:
    plot3d(fig, filename=os.path.join(result_dir, 'rivus_result.html'))
else:
    plot3d(fig, filename=os.path.join(arch_dir, 'rivus_result.html'))
profile_log['plotting'] = timenow() - myprintstart

print('{1} Script parts took: (sec) {1}\n{0:s}\n{1}{1}{1}{1}'.format(
    Series(profile_log, name='mini-profile').to_string(),
    '=' * 6))