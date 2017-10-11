if __name__ == '__main__':
    from geopandas import GeoDataFrame, GeoSeries
    from shapely.geometry import Point


def vert_init_commodities(vertex_df, commodities, sources=None, inplace=True):
    """Add commodity columns to the vertex DataFrame
    with zeros to vertices without commodity source and
    source capacity at the vertices provided by `sources`.

    Parameters
    ----------
    vertex_df : (Geo)DataFrame
        vertex dataframe input
    commodities : list of str
        Like ('Elec', 'Gas', 'Heat')
    sources : list of tuples, optional
        Init the source nodes.
        Tuple form:(Commodity, Index, Value)
    inplace : Boolean, default: True
        If False, vertex_df is not changed and the result is returned.

    Returns
    -------
    None or DataFrame
        DataFrame if inplace == False

    Raises
    ------
    ValueError
        If parameters differ from awaited

    Example
    --------
    ::

        comms = ('Elec', 'Gas')
        sources = [('Elec', 0, 1000), ('Gas', 1, 500)]
        vert_init_commodities(vert, comms, sources)
    """
    if inplace:
        vdf = vertex_df
    else:
        vdf = vertex_df.copy()

    for commo in commodities:
        vdf[commo] = len(vdf) * [0]
    if sources:
        for s in sources:
            is_well_typed = (isinstance(s[0], str) and
                             abs(s[1]) >= 0 and
                             abs(s[2]) >= 0)
            has_good_dims = (len(s) == 3) and s[1] < len(vdf)
            if is_well_typed and has_good_dims:
                vdf.set_value(index=s[1], col=s[0], value=s[2])
            else:
                raise ValueError('Parameter problem in function call.\n' +
                                 'Type is good: {}\n'.format(is_well_typed) +
                                 'Dims are good: {}\n'.format(has_good_dims) +
                                 'Source: {}'.format(s))
        if not inplace:
            return vdf


def extend_edge_data(edge_df, sorts=None, inits=None, strat='equal',
                     strat_param=None):
    """Add demand data to the edges in a (Geo)DataFrame

    Parameters
    ----------
    edge_df : (Geo)DataFrame
        edge dataframe to be extended
    sorts : list of str, optional
        The names of new columns (extensions)
        Defaults to ['residential']
    inits : list of int/float , optional
        The parameter values, matching to sorts argument.
        Defaults to [1000] for each sort.
    strat : str, optional
        **TODO now only 'equal' has an effect**
        How the data values will be created
        + 'equal' - all edge demand is the same
        + 'linear' - linearly decreasing
        + 'exp' - exponentially decreasing
        + 'manual' - provide mapper in strat_param
    strat_param : optional
        **TODO not implemented yet**
        Parameter for linear | exp | manual strategies.
        + 'equal' - None - no effect
        + 'linear' - minimum (lowest demand)
        + 'exp' - minimum (lowest demand)
        + 'manual' - function/dict to fetch value per edge

    Example
    -------
    ::

        sorts = ('residential', 'other')
        inits = (1000, 800)
        extend_edge_data(edge, sorts=sorts, inits=inits)

    Raises
    ------
    ValueError
        If inputs differ from awaited

    """

    # How the data will be distributed among the edges
    strat = 'equal' if strat not in [
        'equal', 'linear', 'exp'] else strat

    # Value to the distribution, and types
    sorts = ['residential'] if not sorts else sorts
    inits = [1000] * len(sorts) if not inits else inits
    if len(sorts) != len(inits):
        raise ValueError('sorts and initvals do not have same length.')

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
