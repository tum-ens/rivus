# GENERAL
import os
from copy import deepcopy
from time import time as timenow
from datetime import datetime
from numpy import arange
from pandas import Series

# SOLVER
import pyomo.environ  # although it is not used directly, it is needed by pyomo
from pyomo.opt.base import SolverFactory
from pyomo.opt import SolverStatus
from pyomo.opt import TerminationCondition
from rivus.utils.prerun import setup_solver
# GRID (STREET STRUCTURE)
from rivus.gridder.create_grid import create_square_grid
from rivus.gridder.extend_grid import extend_edge_data
from rivus.gridder.extend_grid import vert_init_commodities
from rivus.gridder.create_grid import get_source_candidates
# PARAMETER-SPACE
from rivus.utils.runmany import parameter_range
# PLOT
from rivus.io.plot import fig3d
# DATABASE
from sqlalchemy import create_engine
from rivus.io import db as rdb
# GRAPH
from rivus.graph.to_graph import to_nx
from rivus.graph.analysis import minimal_graph_anal
from rivus.main.rivus import read_excel, create_model, get_constants
# EMAIL NOTIFICATION
from rivus.utils.notify import email_me
# =========================================================
# Constants - Inputs
import json
config = []
with open('./config.json') as conf:
    config = json.load(conf)


def _source_variations(vertex, dim_x, dim_y):
    """Generate vertex dataframe variations with difference locations for the
    source vertices.
    Todo?: Here maybe also extend_edge_data()?

    Parameters
    ----------
    vertex : DataFrame
        Typical vertex dataframe, as returned by create_square_grid()
    dim_x : int
        Number of vertices alongside the x-axis
    dim_y : int
        Number of vertices alongside the y-axis

    Yields
    ------
    Dataframe
        Ready to be fed into the create_model() function as parameter.
    """

    # max commodity capacity, the source can generate
    MAX_ELEC = 160000
    MAX_GAS = 500000

    src_inds = get_source_candidates(vertex, dim_x, dim_y, logic='sym')
    if False:
        source_setups = [[('Elec', S, MAX_ELEC), ('Gas', S, MAX_GAS)]
                         for S in src_inds]
    else:
        source_setups = []

    if True:
        flip = src_inds.copy()
        flip.reverse()
        src_pairs_opposite = zip(src_inds, flip)
        for E, G in src_pairs_opposite:
            this_srcs = [('Elec', E, MAX_ELEC), ('Gas', G, MAX_GAS)]
            if this_srcs not in source_setups:
                source_setups.append(this_srcs)

    if False:
        src_corners = get_source_candidates(
            vertex, dim_x, dim_y, logic='extrema')
        for E, G in src_corners:
            this_srcs = [('Elec', E, MAX_ELEC), ('Gas', G, MAX_GAS)]
            if this_srcs not in source_setups:
                source_setups.append(this_srcs)

    for sources in source_setups:
        print('\nCurrent sources: \n{}'.format(sources))
        variant = vert_init_commodities(vertex, ('Elec', 'Gas', 'Heat'),
                                        sources=sources, inplace=False)
        yield variant


def run_bunch(use_email=False):
    """Run a bunch of optimizations and analysis automated. """
    # Files Access | INITs
    proj_name = 'runbunch'
    base_directory = os.path.join('data', proj_name)
    data_spreadsheet = os.path.join(base_directory, 'data.xlsx')
    profile_log = Series(name='{}-profiler'.format(proj_name))

    # Email connection
    email_setup = {
        'sender': config['email']['s_user'],
        'send_pass': config['email']['s_pass'],
        'recipient': config['email']['r_user'],
        'smtp_addr': config['email']['smtp_addr'],
        'smtp_port': config['email']['smtp_port']
    }

    # DB connection
    _user = config['db']['user']
    _pass = config['db']['pass']
    _host = config['db']['host']
    _base = config['db']['base']
    engine_string = ('postgresql://{}:{}@{}/{}'
                     .format(_user, _pass, _host, _base))
    engine = create_engine(engine_string)

    # Input Data
    # ----------
    # Spatial
    street_lengths = arange(50, 300, 100)
    num_edge_xs = [5, ]
    # Non-spatial
    data = read_excel(data_spreadsheet)
    original_data = deepcopy(data)
    interesting_parameters = [
        {'df_name': 'commodity',
         'args': {'index': 'Heat',
                  'column': 'cost-inv-fix',
                  'lim_lo': 0.5, 'lim_up': 1.6, 'step': 0.5}},
        {'df_name': 'commodity',
         'args': {'index': 'Heat',
                  'column': 'cost-fix',
                  'lim_lo': 0.5, 'lim_up': 1.6, 'step': 0.5}}
        # {'df_name': 'commodity',
        #  'args': {'index': 'Elec',
        #           'column': 'cost-var',
        #           'step': 0.1}}
    ]
    # Model Creation
    solver = SolverFactory(config['solver'])
    solver = setup_solver(solver, log_to_console=False, guro_time_lim=14400)
    # Solve | Analyse | Store | Change | Repeat
    for dx in street_lengths:
        for len_x, len_y in [(dx, dx), (dx, dx / 2)]:
            run_summary = 'Run with x:{}, y:{}'.format(len_x, len_y)
            for num_edge_x in num_edge_xs:
                vdf, edf = create_square_grid(num_edge_x=num_edge_x, dx=len_x,
                                              dy=len_y)
                extend_edge_data(edf)
                dim_x = num_edge_x + 1
                dim_y = dim_x
                for _vdf in _source_variations(vdf, dim_x, dim_y):
                    for param in interesting_parameters:
                        para_name = param['args']['column']
                        print('{0}\n{3}x{3} grid\t'
                              'dx:{1}, dy:{2}, #e:{3}, src:-, par:{4}\n'
                              .format('=' * 10, len_x, len_y, num_edge_x, para_name))
                        counter = 1
                        for variant in parameter_range(data[param['df_name']],
                                                       **param['args']):
                            changed = (variant.loc[param['args']['index']]
                                       [param['args']['column']])
                            print('variant <{0}>:{1}'.format(counter, changed))
                            counter = counter + 1
                            # Use temporal local versions.
                            # As create_model is destructive. See Issue #31.
                            __vdf = deepcopy(_vdf)
                            __edf = deepcopy(edf)
                            __data = data.copy()
                            __data[param['df_name']] = variant
                            print('\tcreating model')
                            _p_model = timenow()
                            prob = create_model(__data, __vdf, __edf)
                            profile_log['model_creation'] = (
                                timenow() - _p_model)
                            _p_solve = timenow()
                            print('\tsolving...')
                            try:
                                results = solver.solve(prob, tee=True)
                            except Exception as solve_error:
                                print(solve_error)
                                if use_email:
                                    sub = run_summary + '[rivus][solve-error]'
                                    email_me(solve_error, subject=sub,
                                             **email_setup)
                            if (results.solver.status != SolverStatus.ok):
                                status = 'error'
                                outcome = 'error'
                            else:
                                status = 'run'
                                if (results.solver.termination_condition !=
                                        TerminationCondition.optimal):
                                    outcome = 'optimum_not_reached'
                                else:
                                    outcome = 'optimum'
                            profile_log['solve'] = (timenow() - _p_solve)
                            # Plot
                            _p_plot = timenow()
                            plotcomms = ['Gas', 'Heat', 'Elec']
                            try:
                                fig = fig3d(prob, plotcomms, linescale=8,
                                            use_hubs=True)
                            except Exception as plot_error:
                                print(plot_error)
                                if use_email:
                                    sub = run_summary + '[rivus][plot-error]'
                                    email_me(plot_error, subject=sub,
                                             **email_setup)
                            profile_log['3d_plot_prep'] = (timenow() - _p_plot)
                            # Graph
                            _p_graph = timenow()
                            try:
                                _, pmax, _, _ = get_constants(prob)
                                graphs = to_nx(_vdf, edf, pmax)
                                graph_results = minimal_graph_anal(graphs)
                            except Exception as graph_error:
                                print(graph_error)
                                if use_email:
                                    sub = run_summary + '[rivus][graph-error]'
                                    email_me(graph_error, subject=sub,
                                             **email_setup)
                            profile_log['all_graph_related'] = (
                                timenow() - _p_graph)
                            # Store
                            this_run = {
                                'comment': config['run_comment'],
                                'status': status,
                                'outcome': outcome,
                                'runner': 'lnksz',
                                'plot_dict': fig,
                                'profiler': profile_log}
                            try:
                                rdb.store(engine, prob, run_data=this_run,
                                          graph_results=graph_results)
                            except Exception as db_error:
                                print(db_error)
                                if use_email:
                                    sub = run_summary + '[rivus][db-error]'
                                    email_me(db_error, subject=sub,
                                             **email_setup)
                            del __vdf
                            del __edf
                            del __data
                            print('\tRun ended with: <{}>\n'.format(outcome))

                        data = original_data
                if use_email:
                    status_txt = ('Finished iteration with edge number {}\n'
                                  'did: [source-var, param-seek]\n'
                                  'from [street-length, dim-shift, source-var,'
                                  ' param-seek]'
                                  'dx:{}, dy:{}'
                                  .format(num_edge_x, len_x, len_y))
                    sub = run_summary + '[rivus][finish-a-src]'
                    email_me(status_txt, subject=sub, **email_setup)
        if use_email:
            status_txt = ('Finished iteration with street lengths {}-{}\n'
                          'did: [dim-shift, source-var, param-seek]\n'
                          'from [street-length, dim-shift, source-var,'
                          ' param-seek]'
                          .format(len_x, len_y))
            sub = run_summary + '[rivus][finish-a-len-combo]'
            email_me(status_txt, subject=sub, **email_setup)
    if use_email:
        status_txt = ('Finished run-bunch at {}\n'
                      'did: [street-length, dim-shift, source-var, param-seek]'
                      .format(datetime.now().strftime('%y%m%dT%H%M')))
        sub = run_summary + '[rivus][finish-run]'
        email_me(status_txt, subject=sub, **email_setup)
    print('End of runbunch.')


if __name__ == '__main__':
    run_bunch(use_email=True)
