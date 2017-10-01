import unittest
import pyomo.environ  # although is not used direktly, is needee by pyomo
from pyomo.opt.base import SolverFactory
from rivus.main.rivus import read_excel, create_model
from rivus.main.rivus import get_timeseries, get_constants
from rivus.utils.prerun import setup_solver
from rivus.gridder.create_grid import create_square_grid as square_grid
from rivus.gridder.extend_grid import vert_init_commodities
from rivus.gridder.extend_grid import extend_edge_data
from rivus.io import db as rdb
from sqlalchemy import create_engine
import json
import os
pdir = os.path.dirname


class RivusDBTest(unittest.TestCase):

    def test_df_insert_query(self):
        """Are the stored dataframes and the retrieved ones identical?

        - Comparison form of frames is *after* create_model. (index is set)
        - Comparison form expects that input dataframes only have meaningful
          columns. (See pull request #23)
        - Only implemented dataframes are tested.

        Note
        ----
        Requires a ``config.json`` file in the root of rivus-repo with the
        database credentials. For Example:
        ::

            {
                "db" : {
                    "user" : "postgres",
                    "pass" : "postgres",
                    "host" : "localhost",
                    "base" : "rivus"
                }
            }
        """
        conf_path = os.path.join(pdir(pdir(pdir(__file__))), 'config.json')
        config = []
        with open(conf_path) as conf:
            config = json.load(conf)
        # DB connection
        _user = config['db']['user']
        _pass = config['db']['pass']
        _host = config['db']['host']
        _base = config['db']['base']
        engine_string = ('postgresql://{}:{}@{}/{}'
                         .format(_user, _pass, _host, _base))
        engine = create_engine(engine_string)

        proj_name = 'mnl'
        base_directory = os.path.join('data', proj_name)
        data_spreadsheet = os.path.join(base_directory, 'data.xlsx')
        data = read_excel(data_spreadsheet)
        # data_bup = data.copy()
        vertex, edge = square_grid()
        vert_init_commodities(vertex, ['Elec', 'Gas'], [('Elec', 0, 100000)])
        extend_edge_data(edge)
        prob = create_model(data, vertex, edge)
        solver = SolverFactory(config['solver'])
        solver = setup_solver(solver, log_to_console=False)
        solver.solve(prob, tee=True)

        test_id = rdb.init_run(engine, runner='Unittest')
        rdb.store(engine, prob, run_id=test_id)

        this_df = None
        dfs = data.keys()
        for df in dfs:
            if df == 'hub':
                continue  # is not implemented yet
            this_df = data[df]
            print(df)
            re_df = rdb.df_from_table(engine, df, test_id)
            self.assertTrue(all(this_df.fillna(0) ==
                                re_df.reindex(this_df.index).fillna(0)),
                            msg=('{}: Original and retrieved frames'
                                 ' are not identical'.format(df)))
        # Add implemented result dataframes
        cost, pmax, kappa_hub, kappa_process = get_constants(prob)
        source, _, _, _, _, = get_timeseries(prob)
        results = dict(source=source, cost=cost, pmax=pmax,
                       kappa_hub=kappa_hub, kappa_process=kappa_process)
        dfs = ['source', 'cost', 'pmax', 'kappa_hub', 'kappa_process']
        for df in dfs:
            this_df = results[df]
            print(df)
            re_df = rdb.df_from_table(engine, df, test_id)
            self.assertTrue(all(this_df.fillna(0) ==
                                re_df.reindex(this_df.index).fillna(0)),
                            msg=('{}: Original and retrieved frames'
                                 ' are not identical'.format(df)))
