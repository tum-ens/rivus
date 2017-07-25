"""Functions to convert tabular data to popular python graph structures
igraph:
    + C based with python wrappers.
    + Included for speed and so scalability.
    × Docs are OK.
    - For windows install with unofficial wheel files. But it works.
networkx:
    +/- Pure python implementation.
    + Widely used and tested.
    + Docs are quite good.
    + Easy (platform independent) installation
    - Slower than igraph (and graph-tools)
graph-tools: (maybe added in the future)
    + Self proclaimed: fastest in graph analyses
    - Not really windows user friendly (docker install should be tested)
"""
import os


def to_igraph(vdf, edf, pmax, comms=None, peak=None, save_dir=None, ext='gml'):
    """Convert Data from (Geo)DataFrames to igraph(s)
    Each commodity gets its own graph
    Weights are derived from built capacity.

    Args:
        vdf ([Geo]DataFrame): Holding Vertex Data id=Vertex
            and Commodity Sources as columns
        edf ([Geo]DataFrame): Holding (V1,V2) Multi-indexed Edge data
            To be sure, that all edges are created.
        pmax (DataFrame): Commodities as columns with max capacity per edge
            returned by rivus.get_constants()
        comms (iterable, optional): Names of the commodities from which we
            build the graphs. (Each as separate graph.) If omitted, the columns
            of pmax will be used.
        peak (DataFrame, optional): Commodities as columns with demands
            in t_peak time-step. Calculated in main.rivus
        save_dir (path string, optional): Path to a dir to save graphs as `ext`
            Path preferably constructed using the os.path module.
            If dir does not exit yet, it will be created.
        ext (string) file extension, supported by igraph.save()
            If not one of the following, the default 'gml' will be applied.
            'adjacency', 'dimacs', 'dot', 'graphviz', 'edgelist', 'edges',
            'edge', 'gml', 'graphml', 'graphmlz', 'gw', 'leda', 'lgl', 'lgr',
            'ncol', 'net', 'pajek', 'pickle', 'picklez', 'svg'

    Returns:
        List of igraph.Graph objects in order of `comms`
    """
    import igraph as ig
    ext_list = ['adjacency', 'dimacs', 'dot', 'graphviz', 'edgelist', 'edges',
                'edge', 'gml', 'graphml', 'graphmlz', 'gw', 'leda', 'lgl',
                'lgr', 'ncol', 'net', 'pajek', 'pickle', 'picklez', 'svg']
    if ext not in ext_list:
        ext = 'gml'
    if len(edf) != len(pmax):
        pmax = edf.join(pmax).fillna(0)
    comms = pmax.columns.values if comms is None else comms

    graphs = []
    for comm in comms:
        # Graph can be created from vertices, because no isolated node is
        # in the input graph.
        g = ig.Graph(edf.index.values.tolist())
        g['Name'] = '{} capacity graph'.format(comm.upper())
        g['Commodity'] = comm
        g.vs['Label'] = vdf.index.values.tolist()
        g.vs[comm] = vdf[comm].tolist()
        g.es['Label'] = list(map(lambda v1v2: '{}-{}'.format(*v1v2),
                                 edf.index.values))
        g.es[comm] = pmax[comm].tolist()
        weights = pmax[comm] / pmax[comm].max()
        g.es['Weight'] = weights.tolist()
        if peak is not None:
            g.es[comm + '-peak'] = peak[comm].tolist()
        # For possible GeoLayout (e.g. in Gephi)
        g.vs['Longitude'] = vdf.geometry.map(lambda p: p.x).tolist()
        g.vs['Latitude'] = vdf.geometry.map(lambda p: p.y).tolist()
        graphs.append(g)

    if save_dir:
        if not os.path.isdir(save_dir):
            os.makedirs(save_dir)
        for graph in graphs:
            gpath = os.path.join(save_dir, '{}.{}'.format(graph['Name']), ext)
            with open(gpath, 'w') as fhandle:
                graph.save(fhandle, ext)
    return graphs


def to_nx(vdf, edf, pmax, comms=None, save_dir=None):
    """Convert to networkx graph representation

    Args:
        vdf ([Geo]DataFrame): Holding Vertex Data id=Vertex
            and Commodity Sources as columns
        edf ([Geo]DataFrame): Holding (V1,V2) Multi-indexed Edge data
            To be sure, that all edges are created.
        pmax (DataFrame): Commodities as columns with max capacity per edge
            returned by rivus.get_constants()
        comms (iterable, optional): Names of the commodities from which we
            build the graphs. (Each as separate graph.) If omitted, the columns
            of pmax will be used.
        save_dir (path string, optional): Path to a dir to save graphs as GML.
            Path preferably constructed using the `os.path` module
            If dir does not exit yet, it will be created.

    Returns:
        list of nx_graph object per in accordance with input `comms`
        or commodities found in pmax.columns

    Note:
        nx.from_pandas_dataframe() was also investigated, but it is a bit
        slower and does not improve code quality in my opinion.
    """
    import networks as nx
    if len(edf) != len(pmax):
        _pmax = edf.join(pmax).fillna(0)
    else:
        _pmax = pmax.copy()
    comms = _pmax.columns.values if comms is None else comms

    graphs = []
    for comm in comms:
        g = nx.Graph(Name='{} capacity graph'.format(comm.upper()),
                     Commodity=comm)
        g.add_nodes_from(vdf.index.values.tolist())
        for x, row in vdf.iterrows():
            g.node[x]['Label'] = x
            g.node[x][comm] = row[comm]
            g.node[x]['Longitude'] = row.geometry.x
            g.node[x]['Latitude'] = row.geometry.y
        cap_max = _pmax[comm].max()
        for v1v2, row in _pmax.iterrows():
            this_weight = row[comm] / cap_max
            this_label = '{}-{}'.format(*v1v2)
            g.add_edge(*v1v2, Label=this_label, Commodity=row[comm],
                       Weight=this_weight)
        graphs.append(g)

    if save_dir:
        ext = 'gml'  # TODO networkx has different function to do this...
        if not os.path.isdir(save_dir):
            os.makedirs(save_dir)
        for graph in graphs:
            gpath = os.path.join(save_dir, '{}.{}'.format(graph['Name']), ext)
            nx.write_gml(graph, gpath)

    return graphs
