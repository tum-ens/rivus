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
from pandas import DataFrame, read_sql

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


def _fill_table(engine, prob, table, run_id):
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
    if table == 'commodity':
        df = prob.params[table]
        sql_df = df.rename(columns=col_map)
        sql_df['run_id'] = run_id
        sql_df.to_sql(table, engine, if_exists='append', index_label=table)
    elif table == 'process':
        df = prob.params[table]
        sql_df = df.loc[:, 'cost-inv-fix':'cap-max'].rename(columns=col_map)
        sql_df['run_id'] = run_id
        sql_df.to_sql(table, engine, if_exists='append', index_label=table)
    elif table == 'edge':
        df = prob.params[table]
        sql_df = df.loc[:, ('Edge', 'geometry')]
        _handle_geoframe(engine, table, sql_df, run_id)
    elif table == 'vertex':
        df = prob.params[table]
        sql_df = df.geometry.to_frame()
        _handle_geoframe(engine, table, sql_df, run_id)
        df = df.loc[:, [c for c in df.columns.values if c != 'geometry']]
        connection = engine.raw_connection()
        try:
            for ver, row in df.iterrows():
                for comm, val in row.iteritems():
                    values = dict(vertex=ver, commodity=comm,
                                  value=val, run_id=run_id)
                    with connection.cursor() as curs:
                        curs.execute(
                            """
                            INSERT INTO vertex_source
                            (vertex_id, commodity_id, value)
                            VALUES (
                                (SELECT vertex_id FROM vertex
                                 WHERE run_id = %(run_id)s AND
                                       vertex_num = %(vertex)s),
                                (SELECT commodity_id FROM commodity
                                 WHERE run_id = %(run_id)s AND
                                       commodity LIKE %(commodity)s),
                                %(value)s;
                            """, values)
                        connection.commit()
        finally:
            connection.close()
    elif table == 'time':
        df = prob.params[table]
        sql_df = df.loc[:, 'weight'].to_frame()
        sql_df['run_id'] = run_id
        sql_df.to_sql(table, engine, if_exists='append',
                      index_label='time_step')
        df = df.loc[:, [c for c in df.columns.values if c != 'weight']]
        connection = engine.raw_connection()
        try:
            for ver, row in df.iterrows():
                for comm, val in row.iteritems():
                    values = dict(vertex=ver, commodity=comm,
                                  value=val, run_id=run_id)
                    with connection.cursor() as curs:
                        curs.execute(
                            """
                            INSERT INTO vertex_source
                            (vertex_id, commodity_id, value)
                            VALUES (
                                (SELECT vertex_id FROM vertex
                                 WHERE run_id = %(run_id)s AND
                                       vertex_num = %(vertex)s),
                                (SELECT commodity_id FROM commodity
                                 WHERE run_id = %(run_id)s AND
                                       commodity LIKE %(commodity)s),
                                %(value)s;
                            """, values)
                        connection.commit()
        finally:
            connection.close()
    elif table == 'area_demand':
        df = prob.params[table]
        area_types = df.unstack(level='Commodity').index.values
        sql_df = DataFrame(dict(building_type=area_types,
                                run_id=[run_id] * len(area_types)))
        sql_df.to_sql('area', engine, if_exists='append', index=False)
        connection = engine.raw_connection()
        try:
            for key, row in df.iterrows():
                values = dict(row, area=key[0], commodity=key[1], run_id=run_id)
                with connection.cursor() as curs:
                    curs.execute(
                        """
                        INSERT INTO area_demand
                        (area_id, commodity_id, peak)
                        VALUES (
                            (SELECT area_id FROM area
                             WHERE run_id = %(run_id)s AND
                                   building_type LIKE %(area)s),
                            (SELECT commodity_id FROM commodity
                             WHERE run_id = %(run_id)s AND
                                   commodity LIKE %(commodity)s),
                            %(peak)s);
                        """, values)
                    connection.commit()
        finally:
            connection.close()
    elif table == 'process_commodity':
        df = prob.params[table]
        connection = engine.raw_connection()
        try:
            for key, row in df.iterrows():
                values = dict(row, process=key[0], commodity=key[1],
                              direction=key[2].lower(), run_id=run_id)
                with connection.cursor() as curs:
                    curs.execute(
                        """
                        INSERT INTO process_commodity
                        (process_id, commodity_id, direction, ratio)
                        VALUES (
                            (SELECT process_id FROM process
                             WHERE run_id = %(run_id)s AND
                                   process LIKE %(process)s),
                            (SELECT commodity_id FROM commodity
                             WHERE run_id = %(run_id)s AND
                                   commodity LIKE %(commodity)s),
                            %(direction)s,
                            %(ratio)s);
                        """, values)
                    connection.commit()
        finally:
            connection.close()
    else:
        pass
    return


def store(engine, prob, run_data=None, run_id=None, plot_data=None, graph=None):
    if run_id is not None:
        run_id = int(run_id)
    else:
        run_id = init_run(engine, **run_data) if run_data else init_run(engine)
    print('store params for run <{}>'.format(run_id))

    # Parameter DataFrames=====================================================
    # The order does matter.
    # `process_commodity` after `process` and `commodity`
    # `vertex` after `commodity`
    # `time` after `commodity`
    tables = ['commodity', 'process', 'edge', 'vertex', 'time', 'area_demand',
              'process_commodity', 'vertex_source']
    for table in tables:
        _fill_table(engine, prob, table, run_id)
    return


def fetch_table(engine, table, run_id):
    if table == 'process_commodity':
        sql = """
            SELECT P.process AS "Process", C.commodity AS "Commodity",
                   PC.direction AS "Direction", PC.ratio AS ratio
            FROM process_commodity AS PC
            INNER JOIN commodity AS C ON PC.commodity_id = C.commodity_id
            INNER JOIN process AS P ON PC.process_id = P.process_id
            where P.run_id = %s;
            """
        df = read_sql(sql, engine, params=(run_id,),
                      index_col=['Process', 'Commodity', 'Direction'])
    else:
        df = DataFrame()
    return df


def load(engine, run_id):
    """Summary

    Args:
        engine (TYPE): Description
        run_id (TYPE): Description
    """
    # Create Process-Commodity DataFrame
    print("""
        SELECT P.process AS "Process", C.commodity AS "Commodity",
               PC.direction AS "Direction", PC.ratio AS ratio
        FROM process_commodity AS PC
        INNER JOIN commodity AS C ON PC.commodity_id=C.commodity_id
        INNER JOIN process AS P ON PC.process_id=P.process_id
        where P.run_id = 28;
        """)

    pass

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
