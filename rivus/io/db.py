"""Postgres helpers
Of course after you established a connection to the database, you can do
whatever you are capable of with your SQL-skills.
However, to spare some effort, I added these helpers to avoid repetition of
common tasks. Hopefully, this makes database integration easier in the future.
Leading to better structured results.

For specific information on the entity relationship of the expected DB visit:
    [rivus_db](https://github.com/lnksz/rivus_db)
"""

from datetime import datetime
from pandas import DataFrame, read_sql
from ..main.rivus import get_timeseries, get_constants


def init_run(engine, runner='Havasi', start_ts=None, status='prepared',
             outcome='not_run'):
    """Initialize the `run` table with basic info.

    Parameters
    ----------
    engine : sqlalchemy engine whit psycopg2 driver
        For managing connection to the DB.
    runner : str, optional
        Person's name/identifier who created(executed) the data(process).
    start_ts : datetime.datetime, optional
        Timezone-less datetime object.
        If omitted, .now() will be used.
    status : str, optional
        One of the following strings:
        | 'prepared' (default) | 'run' | 'error'
    outcome : str, optional
        One of the following strings:
        | 'not_run'  (default) | 'optima' | 'no_optima' | 'error'

    Returns
    -------
    int
        run_id of the initialized run row in the DB.
    """
    if start_ts is None:
        start_ts = datetime.now()

    run_id = None
    connection = engine.raw_connection()
    try:
        with connection.cursor() as curs:
            curs.execute("""
                INSERT INTO run (runner, start_ts, status, outcome)
                VALUES (%s, %s, %s, %s)
                RETURNING run_id;
                """, (runner, start_ts, status, outcome))
            run_id = curs.fetchone()[0]
            connection.commit()
    finally:
        connection.close()
    return run_id


def _purge_table(engine, table, run_id):
    """Delete rows in `table` which are related to `run_id`.

    Parameters
    ----------
    engine : sqlalchemy engine whit psycopg2 driver
        For managing connection to the DB.
    table : str
        An existing table in database 'rivus_db'
        See: [rivus_db](https://github.com/lnksz/rivus_db)
    run_id : int
        run_id of the initialized run row in the DB.
        Used to identify related data to be removed:
        directly (table has `run_in` as FK) and
        indirectly (table has FK of an Entity with `run_id` FK)

    Returns
    ------------------
    None
    """
    if table in ['process', 'commodity', 'edge', 'vertex', 'area', 'time']:
        # These have run_id as FK
        connection = engine.raw_connection()
        try:
            with connection.cursor() as curs:
                curs.execute("""
                    DELETE FROM "{}"
                    WHERE run_id = %s;
                    """.format(table), [run_id, ])
                connection.commit()
        finally:
            connection.close()
    elif table in ['process_commodity', 'vertex_source', 'area_demand',
                   'time_demand']:
        # These have commodity_id as FK
        connection = engine.raw_connection()
        try:
            with connection.cursor() as curs:
                curs.execute("""
                    DELETE FROM {0} USING commodity
                    WHERE {0}.commodity_id = commodity.commodity_id AND
                          commodity.run_id = %s;
                    """.format(table), (run_id, ))
                connection.commit()
        finally:
            connection.close()
    elif table == 'edge_demand':
        # This has edge_id as FK
        connection = engine.raw_connection()
        try:
            with connection.cursor() as curs:
                curs.execute("""
                    DELETE FROM {0} USING edge
                    WHERE {0}.edge_id = edge.edge_id AND
                          edge.run_id = %s;
                    """.format(table), (run_id, ))
                connection.commit()
        finally:
            connection.close()
    else:
        pass


def purge_run(engine, run_id):
    """Delete all rows related to run_id across all tables.

    Parameters
    ----------
    engine : sqlalchemy engine whit psycopg2 driver
        For managing connection to the DB.
    run_id : int
        run_id of the initialized run row in the DB.
        Used to identify related data to be removed:
        directly (table has `run_in` as FK) and
        indirectly (table has FK of an Entity with `run_id` FK)

    Returns
    -------
    None
    """
    # Table order matters: reverse of `store()` logic.
    second_gen = ['process_commodity', 'vertex_source', 'edge_demand',
                  'area_demand', 'time_demand']
    first_gen = ['edge', 'vertex', 'area', 'time', 'process', 'commodity']
    tables = second_gen + first_gen
    for table in tables:
        _purge_table(engine, table, run_id)


def _handle_geoframe(engine, frame, df, run_id):
    """Before inserting to the DB, convert `geometries` column to WKT.

    Parameters
    ----------
    engine : sqlalchemy engine whit psycopg2 driver
        For managing connection to the DB.
    frame : str
        Name of the DataFrame as in `prob.params[]`
    df : GeoDataFrame
        as retrieved from ˙prog.param[]`
    run_id : int
        run_id of the initialized run row in the DB.

    Returns
    -------
    None
    """
    if frame == 'vertex':
        cols = ['run_id', 'vertex_num', 'geometry']
        vals = '%s, %s, ST_GeogFromText(%s)'
    elif frame == 'edge':
        cols = ['run_id', 'edge_num', 'vertex1', 'vertex2', 'geometry']
        vals = '%s, %s, %s, %s, ST_GeogFromText(%s)'

    cols = ','.join(cols)
    string_query = """
        INSERT INTO {0} ({1})
        VALUES ({2});
        """.format(frame, cols, vals)

    connection = engine.raw_connection()
    try:
        for key, row in df.iterrows():
            wkt = row['geometry'].wkt
            with connection.cursor() as curs:
                if frame == 'vertex':
                    curs.execute(string_query, (run_id, int(key), wkt))
                if frame == 'edge':
                    v1, v2 = key
                    curs.execute(string_query, (run_id, row['Edge'],
                                                v1, v2, wkt))
                # run_id = curs.fetchone()[0]
                connection.commit()
    finally:
        connection.close()


def _fill_table(engine, frame, df, run_id):
    """Insert data to db.table from dataframe.

    Parameters
    ----------
    engine : sqlalchemy engine whit psycopg2 driver
        For managing connection to the DB.
    frame : str
        Name of the DataFrame from which data will be exported to DB.
    df : DataFrame
        Expected is a DataFrame, which is an input or output of the rivus
        ConcreteModel. (create_model(), solve(), ...)
    run_id : int
        run_id of the initialized run row in the DB.

    Returns
    -------
    TYPE
        Description
    """
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
    if frame == 'commodity':
        sql_df = df.rename(columns=col_map)
        sql_df['run_id'] = run_id
        sql_df.to_sql(frame, engine, if_exists='append', index_label=frame)
    elif frame == 'process':
        sql_df = df.loc[:, 'cost-inv-fix':'cap-max'].rename(columns=col_map)
        sql_df['run_id'] = run_id
        sql_df.to_sql(frame, engine, if_exists='append', index_label=frame)
    elif frame == 'edge':
        sql_df = df.loc[:, ('Edge', 'geometry')]
        _handle_geoframe(engine, frame, sql_df, run_id)
        df = df.loc[:, [c for c in df.columns.values if c != 'geometry']]
        connection = engine.raw_connection()
        try:
            for _, row in df.iterrows():
                for col, demand in row.iteritems():
                    if col == 'Edge':
                        continue
                    values = dict(edge=int(row['Edge']), building=col,
                                  demand=int(demand), run_id=run_id)
                    with connection.cursor() as curs:
                        curs.execute("""
                            INSERT INTO edge_demand
                            (edge_id, area_id, value)
                            VALUES (
                                (SELECT edge_id FROM edge
                                 WHERE run_id = %(run_id)s AND
                                       edge_num = %(edge)s),
                                (SELECT area_id FROM "area"
                                 WHERE run_id = %(run_id)s AND
                                       building_type LIKE %(building)s),
                                %(demand)s);
                            """, values)
                        connection.commit()
        finally:
            connection.close()
    elif frame == 'vertex':
        sql_df = df.geometry.to_frame()
        _handle_geoframe(engine, frame, sql_df, run_id)
        df = df.loc[:, [c for c in df.columns.values if c != 'geometry']]
        connection = engine.raw_connection()
        try:
            for ver, row in df.iterrows():
                for comm, val in row.iteritems():
                    values = dict(vertex=int(ver), commodity=comm,
                                  value=int(val), run_id=run_id)
                    with connection.cursor() as curs:
                        curs.execute("""
                            INSERT INTO vertex_source
                            (vertex_id, commodity_id, value)
                            VALUES (
                                (SELECT vertex_id FROM vertex
                                 WHERE run_id = %(run_id)s AND
                                       vertex_num = %(vertex)s),
                                (SELECT commodity_id FROM commodity
                                 WHERE run_id = %(run_id)s AND
                                       commodity LIKE %(commodity)s),
                                %(value)s);
                            """, values)
                        connection.commit()
        finally:
            connection.close()
    elif frame == 'time':
        sql_df = df.loc[:, 'weight'].to_frame()
        sql_df['run_id'] = run_id
        sql_df.to_sql(frame, engine, if_exists='append',
                      index_label='time_step')
        df = df.loc[:, [c for c in df.columns.values if c != 'weight']]
        connection = engine.raw_connection()
        try:
            for ts, row in df.iterrows():
                for comm, val in row.iteritems():
                    values = dict(time_step=ts, commodity=comm,
                                  value=float(val), run_id=run_id)
                    with connection.cursor() as curs:
                        curs.execute("""
                            INSERT INTO time_demand
                            (time_id, commodity_id, scale)
                            VALUES (
                                (SELECT time_id FROM "time"
                                 WHERE run_id = %(run_id)s AND
                                       time_step = %(time_step)s),
                                (SELECT commodity_id FROM commodity
                                 WHERE run_id = %(run_id)s AND
                                       commodity LIKE %(commodity)s),
                                %(value)s);
                            """, values)
                        connection.commit()
        finally:
            connection.close()
    elif frame == 'area_demand':
        area_types = df.unstack(level='Commodity').index.values
        sql_df = DataFrame(dict(building_type=area_types,
                                run_id=[run_id] * len(area_types)))
        sql_df.to_sql('area', engine, if_exists='append', index=False)
        connection = engine.raw_connection()
        try:
            for key, row in df.iterrows():
                values = dict(row, area=key[0], commodity=key[1],
                              run_id=run_id)
                with connection.cursor() as curs:
                    curs.execute("""
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
    elif frame == 'process_commodity':
        connection = engine.raw_connection()
        try:
            for key, row in df.iterrows():
                values = dict(row, process=key[0], commodity=key[1],
                              direction=key[2].lower(), run_id=run_id)
                with connection.cursor() as curs:
                    curs.execute("""
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
    elif frame == 'source':
        connection = engine.raw_connection()
        try:
            for (vertex, comm), row in df.iterrows():
                for time_step, val in row.iteritems():
                    values = dict(run_id=run_id, vertex=vertex, commodity=comm,
                                  time_step=time_step, value=float(val))
                    with connection.cursor() as curs:
                        curs.execute("""
                            INSERT INTO {0}
                            (vertex_id, commodity_id, time_id, capacity)
                            VALUES (
                                (SELECT vertex_id FROM vertex
                                 WHERE run_id = %(run_id)s AND
                                       vertex_num = %(vertex)s),
                                (SELECT commodity_id FROM commodity
                                 WHERE run_id = %(run_id)s AND
                                       commodity LIKE %(commodity)s),
                                (SELECT time_id FROM "time"
                                 WHERE run_id = %(run_id)s AND
                                       time_step = %(time_step)s),
                                %(value)s);
                            """.format(frame), values)
                        connection.commit()
        finally:
            connection.close()
    elif frame in ['flow', 'hub', 'proc_io', 'proc_tau']:
        # TODO if needed
        pass
    elif frame == 'cost':
        series = df.rename(dict(Inv='investment', Fix='fix', Var='variable'))
        values = {k: int(v) for k, v in series.iteritems()}
        values['run_id'] = run_id
        connection = engine.raw_connection()
        try:
            with connection.cursor() as curs:
                curs.execute("""
                    INSERT INTO {0} (run_id, variable, investment, fix)
                    VALUES (%(run_id)s, %(variable)s, %(investment)s, %(fix)s);
                    """.format(frame), values)
                connection.commit()
        finally:
            connection.close()
    elif frame == 'pmax':
        connection = engine.raw_connection()
        try:
            for (v1, v2), row in df.iterrows():
                for comm, val in row.iteritems():
                    values = dict(va=v1, vb=v2, commodity=comm, val=int(val),
                                  run_id=run_id)
                    with connection.cursor() as curs:
                        curs.execute("""
                            INSERT INTO {0} (edge_id, commodity_id, capacity)
                            VALUES (
                                (SELECT edge_id FROM edge
                                 WHERE run_id = %(run_id)s AND
                                       vertex1 = %(va)s AND vertex2 = %(vb)s),
                                (SELECT commodity_id from commodity
                                 WHERE run_id = %(run_id)s AND
                                       commodity LIKE %(commodity)s),
                                %(val)s);
                            """.format(frame), values)
                        connection.commit()
        finally:
            connection.close()
    elif frame == 'kappa_hub':
        connection = engine.raw_connection()
        try:
            for (v1, v2), row in df.iterrows():
                for hub, val in row.iteritems():
                    values = dict(va=v1, vb=v2, hub=hub, val=int(val),
                                  run_id=run_id)
                    with connection.cursor() as curs:
                        curs.execute("""
                            INSERT INTO {0} (edge_id, process_id, capacity)
                            VALUES (
                                (SELECT edge_id FROM edge
                                 WHERE run_id = %(run_id)s AND
                                       vertex1 = %(va)s AND vertex2 = %(vb)s),
                                (SELECT process_id from process
                                 WHERE run_id = %(run_id)s AND
                                       process LIKE %(hub)s),
                                %(val)s);
                            """.format(frame), values)
                        connection.commit()
        finally:
            connection.close()
    elif frame == 'kappa_process':
        connection = engine.raw_connection()
        try:
            for ver, row in df.iterrows():
                for proc, val in row.iteritems():
                    values = dict(vertex=ver, process=proc, val=int(val),
                                  run_id=run_id)
                    with connection.cursor() as curs:
                        curs.execute("""
                            INSERT INTO {0} (vertex_id, process_id, capacity)
                            VALUES (
                                (SELECT vertex_id FROM vertex
                                 WHERE run_id = %(run_id)s AND
                                       vertex_num = %(vertex)s),
                                (SELECT process_id from process
                                 WHERE run_id = %(run_id)s AND
                                       process LIKE %(process)s),
                                %(val)s);
                            """.format(frame), values)
                        connection.commit()
        finally:
            connection.close()
    else:
        pass
    return


def store(engine, prob, run_id=None, plot_obj=None, graph_df=None,
          run_data=None, time_series=None, constants=None):
    """Store I/O plus extras of a rivus model into a postgres DB.

    Parameters
    ----------
    engine : sqlalchemy engine whit psycopg2 driver
        For managing connection to the DB.
    prob : pyomo ConcreteModel
        Created by rivus.create_model()
    run_id : int, optional
        run_id of an initialized run row in the DB.
        If omitted: init_run() will be called with `run_data`.
    plot_obj : dict, optional
        TODO
        Result of rivus.io.plot.fig3d(). It will be stored as JSONb.
    graph_df : DataFrame, optional
        TODO
        Results of the graph analysis
    run_data : dict, optional
        Keyword arguments to be passed to init_run().
        runner, start_ts, status, outcome
    time_series : None, optional
        Description
    constants : None, optional
        Description

    Returns
    -------
    None

    Raises
    ------
    Exception caught during data export.
    """
    if run_id is not None:
        run_id = int(run_id)
    else:
        run_id = init_run(engine, **run_data) if run_data else init_run(engine)
    print('Store params for run <{}>'.format(run_id))

    try:
        # Parameter DataFrames
        # --------------------
        # The order of frames -> table does matter.
        # Followings apply to `frames`:
        # `process_commodity` after `process` and `commodity`
        # `vertex`, `area_demand` and `time` after `commodity`
        # `edge` after `area_demand`
        frames = ['commodity', 'process', 'process_commodity', 'area_demand',
                  'vertex', 'time', 'edge']
        for frame in frames:
            # frame should be the same as df.name... but GeoDataFrames does not
            # have a name etc..
            df = prob.params[frame]
            _fill_table(engine, frame, df, run_id)

        # Result DataFrames
        # -----------------
        series_names = ['source', 'flow', 'hub', 'proc_io', 'proc_tau']
        series = get_timeseries(prob)  # source, flows, hubs, proc_io, proc_tau
        consts_names = ['cost', 'pmax', 'kappa_hub', 'kappa_process']
        consts = get_constants(prob)  # costs, Pmax, Kappa_hub, Kappa_process

        for df, name in zip(series+consts, series_names+consts_names):
            if not df.empty:
                _fill_table(engine, name, df, run_id)
    except Exception as e:
        # TODO this is basically a quick'n'dirty transaction rollback.
        # One could dig into sqlalchemy.session to make it better.
        purge_run(engine, run_id)
        raise e

    # Results DataFrames=======================================================


def fetch_table(engine, table, run_id):
    """Extract data form the database into a dataframe in a form, that is common
    during the rivus workflow.
    Implemented dataframes:
        - rivus_model.params[] dataframes:
            - process
            - commodity
            - process_commodity

    Args:
        engine (sqlalchemy engine whit psycopg2 driver):
            For managing connection to the DB.
        table (TYPE): Description
        run_id (TYPE): Description

    Returns:
        TYPE: Description
    """
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
    elif table == 'process':
        sql = """
            SELECT process AS "Process", unit,
                   cost_inv_fix AS "cost-inv-fix",
                   cost_inv_var AS "cost-inv-var",
                   cost_fix AS "cost-fix",
                   cost_var AS "cost-var",
                   cap_min AS "cap-min",
                   cap_max AS "cap-max"
            FROM process WHERE run_id = %s;
            """
        df = read_sql(sql, engine, params=(run_id,),
                      index_col='Process')
    elif table == 'commodity':
        sql = """
            SELECT commodity AS "Commodity", unit,
                   cost_inv_fix AS "cost-inv-fix",
                   cost_inv_var AS "cost-inv-var",
                   cost_fix AS "cost-fix",
                   cost_var AS "cost-var",
                   loss_fix AS "loss-fix",
                   loss_var AS "loss-var",
                   cap_max AS "cap-max",
                   allowed_max AS "allowed-max"
            FROM commodity WHERE run_id = %s;
            """
        df = read_sql(sql, engine, params=(run_id,),
                      index_col='Commodity')
    elif table == 'edge':
        # TODO
        # https://www.postgresql.org/docs/9.1/static/tablefunc.html
        # select * from edge_demand as ED
        # join edge AS E ON E.edge_id=ED.edge_id
        # join area AS A ON A.area_id=ED.area_id
        # where E.run_id=2;
        # sql = """
        #     SELECT
        #         (SELECT vertex1 AS "Vertex1", vertex2 AS "Vertex2", geometry,
        #                 edge_num AS "Edge"
        #          FROM edge WHERE run_id = %s),

        #     SELECT *
        #     FROM edge_demand AS ED
        #     INNER JOIN edge AS E ON ED.edge_id = ED.edge_id
        #     INNER JOIN commodity AS C ON ED.commodity_id = C.commodity_id
        #     WHERE P.run_id = %s;
        #     """
        # df = read_sql(sql, engine, params=(run_id,),
        #               index_col=['Process', 'Commodity', 'Direction'])
    elif table == 'vertex':
        pass
    elif table == 'time':
        pass
    elif table == 'area_demand':
        pass
    elif table == 'source':
        pass
    elif table == 'cost':
        pass
    elif table == 'pmax':
        pass
    elif table == 'kappa_hub':
        pass
    elif table == 'kappa_process':
        pass
    elif table in ['flow', 'hub', 'proc_io', 'proc_tau']:
        df = DataFrame()
    else:
        df = DataFrame()
    return df


def load(engine, run_id):
    """TODO

    Args:
        engine (sqlalchemy engine whit psycopg2 driver):
            For managing connection to the DB.
        run_id (TYPE): Description

    Returns:
        TYPE: Description
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

    return
