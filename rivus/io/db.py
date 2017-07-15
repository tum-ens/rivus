"""Postgres helpers
Of course after you established a connection to the database, you can do
whatever you are capable of with your SQL-skills.
However, to spare some effort, I added these helpers to avoid repetition of
common tasks. Hopefully, this makes database integration easier in the future.
Leading to better structured results.

For specific information on the entity relationschip of the expected DB visit:
[rivus_db](https://github.com/lnksz/rivus_db)
"""

import psycopg2 as psql
from datetime import datetime
from pandas import DataFrame

# from psycopg2 import sql

# cur.execute(
#     sql.SQL("insert into {} values (%s, %s)")
#         .format(sql.Identifier('my_table')),
#     [10, 20])


def _get_insert(table, df):
    if table == 'edge':
        # also include edge_demand TODO
        cols = ['run_id', 'edge_num', 'vertex1', 'vertex2', 'geometry']
    elif table == 'vertex':
        # also include vertex_source TODO
        # ['vertex_id', 'commodity_id', 'value']
        cols = ['run_id', 'vertex_num', 'geometry']
    elif table == 'process':
        cols = ['run_id', 'process', 'cost_inv_fix', 'cost_inv_var',
                'cost_fix', 'cost_var', 'cost_min', 'cost_max']
    elif table == 'commodity':
        cols = ['run_id', 'commodity', 'unit', 'cost_inv_fix', 'cost_inv_var',
                'cost_fix', 'cost_var', 'loss_fix', 'loss_var', 'allowed_max']
    elif table == 'process_commodity':
        cols = ['process_id', 'commodity_id', 'direction', 'ratio']
    elif table == 'time':
        # time_demand
        # ['time_id', 'commodity_id', 'scale']
        cols = ['run_id', 'time_step', 'weight']
    elif table == 'area_demand':
        # area
        # ['area_id', 'run_id', 'building_type']
        cols = ['area_id', 'commodity_id', 'peak']
    else:
        # Not implemented or non-existent table
        return None

    cols = ','.join(cols)
    vals = ','.join(['%s'] * len(cols))
    string_query = """
        INSERT INTO {0} ({1})
        VALUES ({2});
        """.format(table, cols, vals)
    return string_query


def init_run(engine, runner='Havasi', start_ts=None, status='prepared',
             outcome='not_run'):
    try:
        ts = datetime.strptime(start_ts, '%Y-%m-%d %H:%M:%S')
    except:
        ts = datetime.now()
    finally:
        start_ts = ts.strftime('%Y-%m-%d %H:%M:%S')

    run_id = None
    connection = engine.raw_connection()
    try:
        with connection.cursor() as curs:
            curs.execute(
                """
                INSERT INTO run (runner, start_ts, status, outcome)
                VALUES (%s, TIMESTAMP %s, %s, %s)
                RETURNING run_id;
                """, (runner, start_ts, status, outcome))
            run_id = curs.fetchone()[0]
            connection.commit()
    finally:
        connection.close()
    return run_id


def _handle_geoframe(engine, table, df, run_id):
    if table == 'vertex':
        cols = ['run_id', 'vertex_num', 'geometry']
        vals = '%s, %s, ST_GeogFromText(%s)'
    if table == 'edge':
        cols = ['run_id', 'edge_num', 'vertex1', 'vertex2', 'geometry']
        vals = '%s, %s, %s, %s, ST_GeogFromText(%s)'

    cols = ','.join(cols)
    string_query = """
        INSERT INTO {0} ({1})
        VALUES ({2});
        """.format(table, cols, vals)

    connection = engine.raw_connection()
    try:
        for key, row in df.iterrows():
            wkt = row['geometry'].wkt
            with connection.cursor() as curs:
                if table == 'vertex':
                    curs.execute(string_query, (run_id, int(key), wkt))
                if table == 'edge':
                    v1, v2 = key
                    curs.execute(string_query, (run_id, row['Edge'],
                                                v1, v2, wkt))
                # run_id = curs.fetchone()[0]
                connection.commit()
    finally:
        connection.close()
    return


def store(engine, prob, run_data=None, run_id=None, plot_data=None, graph=None):
    if run_id is not None:
        run_id = int(run_id)
    else:
        run_id = init_run(engine, **run_data) if run_data else init_run(engine)
    print('store params for run <{}>'.format(run_id))
    col_map = {
        'Edge': 'edge_num',
        'allowed-max': 'allowed_max',
        'cap-max': 'cap_max',
        'cap-min': 'cap_min',
        'cost-fix': 'cost_fix',
        'cost-inv-fix': 'cost_inv_fix',
        'cost-inv-var': 'cost_inv_var',
        'cost-var': 'cost_var',
        'loss-fix': 'loss_fix',
        'loss-var': 'loss_var',
    }

    # PARAMETERS
    # para_names = ['edge', 'vertex', 'process', 'hub', 'commodity',
    #               'process_commodity', 'time', 'area_demand']
    for para in prob.params:
        df = prob.params[para]
        print('para has <{}>'.format(para))

        if para == 'commodity':
            sql_df = df.rename(columns=col_map)
            sql_df['run_id'] = run_id
            sql_df.to_sql(para, engine, if_exists='append',
                          index_label=para)
        if para == 'process':
            sql_df = df.loc[:, 'cost-inv-fix':'cap-max'].rename(columns=col_map)
            sql_df['run_id'] = run_id
            sql_df.to_sql(para, engine, if_exists='append',
                          index_label=para)
        if para == 'edge':
            sql_df = df.loc[:, ('Edge', 'geometry')]
            _handle_geoframe(engine, para, sql_df, run_id)
            # sql_df.to_sql(para, engine, if_exists='append',
            #               index_label=('vertex1', 'vertex2'))
        if para == 'vertex':
            sql_df = df.geometry.to_frame()
            _handle_geoframe(engine, para, sql_df, run_id)
            # sql_df.to_sql(para, engine, if_exists='append',
            #               index_label='vertex_num')
        if para == 'area_demand':
            area_types = df.unstack(level='Commodity').index.values
            sql_df = DataFrame({
                'building_type': area_types,
                'run_id': [run_id] * len(area_types)
            })
            sql_df.to_sql('area', engine, if_exists='append', index=False)
            # TODO table `area_demand`
        if para == 'process_commodity':
            pass
        if para == 'time':
            sql_df = df.loc[:, 'weight'].to_frame()
            sql_df['run_id'] = run_id
            sql_df.to_sql(para, engine, if_exists='append',
                          index_label='time_step')
        # sql_str = _get_insert(para, prob.params[para])
        # with connection.cursor() as curs:
        #     curs.executemany(sql_str, )
    return

if __name__ == '__main__':
    def tester(prob=None):
        connection = psql.connect(database='rivus', user="postgres")
        # cursor = connection.cursor()
        # cursor.execute("""
        #     SELECT relname FROM pg_class
        #     WHERE relkind='r' and relname !~ '^(pg_|sql_)';
        #     """)
        run_obj = {
            'runner': 'Havasi',
            'start_ts': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'status': 'prepared',
            'outcame': 'not_run',
        }
        run_id = init_run(connection, **run_obj)
        print(run_id)

        connection.close()

    tester()
