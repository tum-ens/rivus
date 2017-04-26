if __name__ == '__main__':
    from geopandas import GeoDataFrame, GeoSeries
    from shapely.geometry import Point


# Add Commodity columns filled with to the vertex DataFrame,
def vert_init_commodities(vertex_df, commodities, sources=None):
    """Add commodity columns with zeros to vertex DataFrame
        source: (Commodity, Index, Value) tuples/lists
            e.g. ('Elec', 1, 2000)
    """
    for commo in commodities:
        vertex_df[commo] = len(vertex_df) * [0]
    if sources:
        for s in sources:
            check1 = (len(s) == 3) and isinstance(s[0], str)
            check2 = isinstance(s[1], int) and isinstance(s[2], (int, float))
            if check1 and check2:
                vertex_df.set_value(index=s[1], col=s[0], value=s[2])


def extend_edge_data(edge_df, dtype='area', strat='equal', sorts=None, inits=None):
    """add various data to the edge (Geo)DataFrame"""
    # TODO data validation
    # sorts-initvals

    # How the data will be distributed among the edges
    # equal: equally, each edge has same value(s)
    # linear: TBD
    # exp: TBD
    # manual: could be cool for plug-in strategy / mask
    strat = 'equal' if strat not in ['equal', 'linear', 'exp', 'manual'] else strat

    # area: as used in the haag project
    # demand: could be used after rivus can take direct demand values
    #         could be proportional to edge length, or place in the grid?
    dtypes = ['area', 'damand']

    # Value to the distribution, and types
    sorts = ['residental'] if not sorts else sorts
    inits = [1000] * len(sorts) if not inits else inits
    if len(sorts) != len(inits):
        raise ValueError('sorts ans initvals are not equal long')

    if strat == 'equal':
        for idx, sort in enumerate(sorts):
            edge_df[sort] = [inits[idx]] * len(edge_df)
    else:
        # TODO different distributions
        pass


if __name__ == '__main__':
    # Vertex Tests
    geomv = GeoSeries([Point(p, p) for p in range(4)])
    vert = GeoDataFrame(geometry=geomv)
    print(vert)

    vert_init_commodities(vert, ('Elec', 'Gas'),
                          [('Elec', 0, 10), ('Gas', 1, 5)])
    print(vert)

    # Edge Tests
    geome = GeoSeries([Point(p, p) for p in range(4)])
    edge = GeoDataFrame(geometry=geome)
    print(edge)

    sorts = ('residential', 'other')
    inits = (1000, 800)
    extend_edge_data(edge, sorts=sorts, inits=inits)
    print(edge)
