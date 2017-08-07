"""Functions to convert tabular data to popular python graph structures
networkx:
    +/- Pure python implementation.
    + Widely used and tested.
    + Docs are quite good.
    + Easy (platform independent) installation
    - Slower than igraph (and graph-tools)
igraph:
    + C based with python wrappers.
    + Mature library package.
    + Included for speed and so for scalability.
    × Docs are OK.
    - Windows install can be somewhat tedious (with unofficial wheel files).
      But it works.
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

    comms = pmax.columns.values if comms is None else comms
    if len(edf) != len(pmax):
        # To have all rows, also the ones, where nothing was built.
        pmax = edf.join(pmax).fillna(0)

    graphs = []
    for comm in comms:
        # Graph can be created from vertices, because no isolated node is
        # in the input graph.
        g = ig.Graph(pmax[comm].index.values.tolist())
        g['Name'] = '{} capacity graph'.format(comm.upper())
        g['Commodity'] = comm
        g.vs['Label'] = vdf.index.values.tolist()
        g.vs[comm] = vdf[comm].tolist()
        g.es['Label'] = list(map(lambda v1v2: '{}-{}'.format(*v1v2),
                                 edf.index.values))
        g.es[comm] = pmax[comm].tolist()
        cap_max = pmax[comm].max()
        if cap_max == 0:
            weights = [0] * len(pmax)
        else:
            weights = pmax[comm] / cap_max
            weights = weights.tolist()
        g.es['Weight'] = weights  # Camel case for Gephi
        g.es['weight'] = weights
        if peak is not None:
            g.es[comm + '-peak'] = peak[comm].tolist()

        # For possible GeoLayout (e.g. in Gephi)
        g.vs['Longitude'] = vdf.geometry.map(lambda p: p.x).tolist()
        g.vs['Latitude'] = vdf.geometry.map(lambda p: p.y).tolist()
        # Delete demand aedges, what are not built in optimum
        g.delete_edges(g.es.select(weight_eq=0))
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
    import networkx as nx
    comms = pmax.columns.values if comms is None else comms
    if len(edf) != len(pmax):
        # To have all rows, also the ones, where nothing was built.
        _pmax = edf.join(pmax).fillna(0)
    else:
        _pmax = pmax.copy()

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
        if cap_max != 0:
            for v1v2, row in _pmax.iterrows():
                if row[comm] == 0:
                    # do not connect verticies in the graph,
                    # if the edge is not built in optimum
                    continue
                this_weight = row[comm] / cap_max
                this_label = '{}-{}'.format(*v1v2)
                g.add_edge(*v1v2, Label=this_label, Commodity=row[comm],
                           Weight=this_weight)
        graphs.append(g)

    if save_dir:
        ext = 'gml'  # TODO networkx has different functions for each format...
        if not os.path.isdir(save_dir):
            os.makedirs(save_dir)
        for graph in graphs:
            gpath = os.path.join(save_dir, '{}.{}'.format(graph['Name']), ext)
            nx.write_gml(graph, gpath)

    return graphs
