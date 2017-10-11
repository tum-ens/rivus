"""Playground script with the features added by lnksz"""

import os
from pandas import Series
from datetime import datetime
from time import time as timenow
# =========================================================
# Constants - Inputs
import json
config = []
with open('./config.json') as conf:
    config = json.load(conf)
SOLVER = config['use_solver']
SAVE_PICKLE = config['use_pickle']
SAVE_REPORT = config['use_report']
STORE_DB = config['store_db']
PLOTTER = config['make_plot']
GRAPHS = config['g_analysis']
SPANNER = config['calc_minimal']
# ---- Solver = True to create and solve new problem
# ---- Solver = False to load an already solved model and investigate it
# =========================================================
if SOLVER:
    import pyomo.environ  # although is not used directly, is needed by Pyomo
    from pyomo.opt.base import SolverFactory

    from rivus.utils.prerun import setup_solver
    from rivus.main.rivus import read_excel, create_model
    from rivus.gridder.create_grid import create_square_grid
    from rivus.gridder.extend_grid import extend_edge_data
    from rivus.gridder.extend_grid import vert_init_commodities
else:
    from rivus.main.rivus import load
    # Here you can add the path to the archive to load data from:
    arch_dir = os.path.join('result', 'chessboard_light')
    arch_path = os.path.join(arch_dir, 'prob.pgz')
if SAVE_PICKLE:
    from rivus.main.rivus import save
if SAVE_REPORT:
    from rivus.main.rivus import report
if PLOTTER:
    from rivus.io.plot import fig3d
    from plotly.offline import plot as plot3d
if STORE_DB:
    from sqlalchemy import create_engine
    from rivus.io import db as rdb
if GRAPHS:
    import networkx as nx
    from rivus.graph.to_graph import to_nx
    from rivus.main.rivus import get_constants


# General input
profile_log = Series(name='runchess-profiler')  # minimal profiler
DX, DY = 250, 125  # Grid block sizes

if SOLVER:
    proj_name = 'chessboard'
    datenow = datetime.now().strftime('%y%m%dT%H%M')
    result_dir = os.path.join('result', '{}-{}'.format(proj_name, datenow))
    # Origin of grid creation
    lat, lon = [48.13512, 11.58198]
    base_directory = os.path.join('data', proj_name)

    # Spatial inputs from the gridder module
    creategrid = timenow()
    vertex, edge = create_square_grid(origo_latlon=(lat, lon), num_edge_x=2,
                                      dx=DX, dy=DY, noise_prop=0.1)
    profile_log['grid_creation'] = round(timenow() - creategrid, 2)

    extendgrid = timenow()
    extend_edge_data(edge)  # only residential, with 1000 kW init
    vert_init_commodities(vertex, ('Elec', 'Gas', 'Heat'),
                          [('Elec', 0, 100000), ('Gas', 0, 5000)])
    profile_log['grid_data'] = timenow() - extendgrid

    # Non spatial input
    data_spreadsheet = os.path.join(base_directory, 'data.xlsx')
    excelread = timenow()
    data = read_excel(data_spreadsheet)
    profile_log['excel_read'] = timenow() - excelread

    # Create and solve model
    rivusmain = timenow()
    prob = create_model(data, vertex, edge)
    profile_log['rivus_main'] = timenow() - rivusmain

    solver = SolverFactory(config['solver'])
    solver = setup_solver(solver)

    startsolver = timenow()
    result = solver.solve(prob, tee=True)
    profile_log['solver'] = timenow() - startsolver

    # Handling results
    if not os.path.exists(result_dir):
        os.makedirs(result_dir)

    if SAVE_PICKLE:
        print('Saving pickle...')
        rivuspickle = timenow()
        save(prob, os.path.join(result_dir, 'prob.pgz'))
        profile_log['save_data'] = timenow() - rivuspickle
        print('Pickle saved')

    if SAVE_REPORT:
        rivusreport = timenow()
        report(prob, os.path.join(result_dir, 'report.xlsx'))
        profile_log['rivus_report'] = timenow() - rivusreport
else:
    print('Loading pickled model...')
    rivusload = timenow()
    prob = load(arch_path)
    profile_log['rivus_load'] = timenow() - rivusload
    print('Loaded.')

if PLOTTER:
    print("Plotting...")
    myprintstart = timenow()
    plotcomms = ['Gas', 'Heat', 'Elec']
    fig = fig3d(prob, linescale=8, comms=plotcomms, use_hubs=True, dz=(.25*DX))
    if SOLVER:
        plot3d(fig, filename=os.path.join(result_dir, 'rivus_result.html'))
    else:
        plot3d(fig, filename=os.path.join(arch_dir, 'rivus_result.html'))
    profile_log['plotting'] = timenow() - myprintstart

if GRAPHS:
    print('Graph handling.')
    graph_prep = timenow()
    _, pmax, _, _ = get_constants(prob)
    graphs = to_nx(prob.params['vertex'], prob.params['edge'], pmax)
    profile_log['graph_prep'] = timenow() - graph_prep

    graph_anal_sum = timenow()
    graph_data = []
    for G in graphs:
        print('Analyzing <{}> graph'.format(G.graph['Commodity']))
        g_data = {
            'commodity': G.graph['Commodity'],
            'is_connected': nx.is_connected(G),
            'connected_components': nx.number_connected_components(G)}
        if SPANNER:
            spanner = nx.minimum_spanning_tree(G)
            g_data['is_minimal'] = nx.is_isomorphic(G, spanner)
        graph_data.append(g_data)
    profile_log['graph_anal_sum'] = timenow() - graph_anal_sum

if STORE_DB:
    print('Using DB')
    dbstart = timenow()
    # Load credentials from untracked file
    _user = config['db']['user']
    _pass = config['db']['pass']
    _host = config['db']['host']
    _base = config['db']['base']
    engine_string = ('postgresql://{}:{}@{}/{}'
                     .format(_user, _pass, _host, _base))
    engine = create_engine(engine_string)
    this_run = dict(comment='testing graph table and features with networkx',
                    profiler=profile_log)
    if GRAPHS:
        rdb.store(engine, prob, run_data=this_run, graph_results=graph_data)
    else:
        rdb.store(engine, prob, run_data=this_run)

    profile_log['db'] = timenow() - dbstart

print('{1} Script parts took: (sec) {1}\n{0:s}\n{1}{1}{1}{1}'
      .format(profile_log.to_string(), '=' * 6))
