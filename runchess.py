import os
from pandas import Series
from datetime import datetime
from time import time as timenow
from rivus.main import rivus
# =========================================================
# Constants - Inputs
lat, lon = [48.13512, 11.58198]  # You can copy LatLon into this list
import json
config = []
with open('./config.json') as conf:
    config = json.load(conf)
SOLVER = config['use_solver']
PLOTTER = config['make_plot']
STORE_DB = config['store_db']
# ---- Solver = True to create and solve new problem
# ---- Solver = False to load an already solved model and investigate it
# =========================================================
if SOLVER:
    try:
        from pyomo.opt.base import SolverFactory
        PYOMO3 = False
    except ImportError:
        from coopr.opt.base import SolverFactory
        PYOMO3 = True
    from rivus.utils.prerun import setup_solver
if PLOTTER:
    # import matplotlib.pyplot as plt
    from rivus.io.plot import fig3d
    from plotly.offline import plot as plot3d

if STORE_DB:
    from datetime import datetime
    from sqlalchemy import create_engine

from rivus.gridder.create_grid import create_square_grid
from rivus.gridder.extend_grid import extend_edge_data, vert_init_commodities
from rivus.io import db as rdb

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
    vertex, edge = create_square_grid(origo_latlon=(lat, lon), num_edge_x=4,
                                      dx=1000)
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
    solver = SolverFactory(config['solver'])
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

    print('Saving pickle...')
    rivuspickle = timenow()
    rivus.save(prob, os.path.join(result_dir, 'prob.pgz'))
    profile_log['save data'] = timenow() - rivuspickle
    print('Pickle saved')
    rivusreport = timenow()
    rivus.report(prob, os.path.join(result_dir, 'report.xlsx'))
    profile_log['rivus report'] = timenow() - rivusreport
else:
    print('Loading pickled modell...')
    arch_dir = os.path.join('result', 'chessboard_light')
    arch_path = os.path.join(arch_dir, 'prob.pgz')
    rivusload = timenow()
    prob = rivus.load(arch_path)
    profile_log['rivus load'] = timenow() - rivusload
    print('Loaded.')

# Plotting
# rivus.result_figures(prob, os.path.join(result_dir, 'figs/'))
if PLOTTER:
    print("Plotting...")
    myprintstart = timenow()
    plotcomms = ['Gas', 'Heat', 'Elec']
    fig = fig3d(prob, plotcomms, linescale=8, usehubs=True)
    if SOLVER:
        plot3d(fig, filename=os.path.join(result_dir, 'rivus_result.html'))
    else:
        plot3d(fig, filename=os.path.join(arch_dir, 'rivus_result.html'))
    profile_log['plotting'] = timenow() - myprintstart

if STORE_DB:
    print('Using DB')
    dbstart = timenow()

    _user = config['db']['user']
    _pass = config['db']['pass']
    _host = config['db']['host']
    _base = config['db']['base']
    engine_string = ('postgresql://{}:{}@{}/{}'
                     .format(_user, _pass, _host, _base))
    engine = create_engine(engine_string)
    # rdb.init_run(engine)
    rdb.store(engine, prob)
    # print(rdb.fetch_table(engine, 'process_commodity', 28))

    profile_log['db'] = timenow() - dbstart

print('{1} Script parts took: (sec) {1}\n{0:s}\n{1}{1}{1}{1}'.format(
    Series(profile_log, name='mini-profile').to_string(),
    '=' * 6))
