if __name__ == '__main__':
    from geopandas import GeoDataFrame, GeoSeries
    from shapely.geometry import Point


# Add Commodity columns filled with to the vertex DataFrame,
def vert_init_commodities(vertex_df, commodities, sources=None):
    """Add commodity columns with zeros to vertex DataFrame
    source: (Commodity, Index, Value) tuples/lists
        e.g. ('Elec', 1, 2000)

    Args:
        vertex_df ((Geo)DataFrame): vertex dataframe input
        commodities (lis of str): Like ('Elec', 'Gas', 'Heat')
        sources (list of tuples, optional): Init the source nodes
            Like [('Elec', 0, 100000), ('Gas', 1, 50000)]
    """
    for commo in commodities:
        vertex_df[commo] = len(vertex_df) * [0]
    if sources:
        for s in sources:
            check1 = (len(s) == 3) and isinstance(s[0], str)
            check2 = isinstance(s[1], int) and isinstance(s[2], (int, float)) and \
                s[1] < len(vertex_df)
            if check1 and check2:
                vertex_df.set_value(index=s[1], col=s[0], value=s[2])
            else:
                raise ValueError('Parameter problem in function call. ch1: {}, ch2: {}'.format(check1, check2))


def extend_edge_data(edge_df, dtype='area', strat='equal', sorts=None, inits=None):
    """Add various data to the edge (Geo)DataFrame
        Normally used to add demand data
    
    Parameters
    ----------
    edge_df : (Geo)DataFrame
        edge dataframe to be extended
    dtype : str, optional
        Type of data whit wich we extend (todo)
    strat : str, optional
        How the data values will be created
    sorts : list of str, optional
        The names of new columns (extensions)
    inits : list of int/float , optional
        The parameter values,
        matching to sorts argument.
    
    Raises
    ------
    ValueError
    If input is not like awaited
    """

    # TODO data validation
    # sorts-initvals

    # How the data will be distributed among the edges
    # equal: equally, each edge has same value(s)
    # linear: TBD
    # exp: TBD
    # manual: could be cool for plug-in strategy / mask
    strat = 'equal' if strat not in [
        'equal', 'linear', 'exp', 'manual'] else strat

    # area: as used in the haag project
    # demand: could be used after rivus can take direct demand values
    #         could be proportional to edge length, or place in the grid?
    dtypes = ['area', 'damand']

    # Value to the distribution, and types
    sorts = ['residential'] if not sorts else sorts
    inits = [1000] * len(sorts) if not inits else inits
    if len(sorts) != len(inits):
        raise ValueError('sorts and initvals are not equal long')

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
