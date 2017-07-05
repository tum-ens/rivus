"""Functions to convert tabular data to popular python graph structures
igraph:
    + C based with python wrappers.
    + Included for speed and so scalability.
    × Docs are OK.
    - For windows install with unofficial wheel files. But it works.
networkx: (todo)
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
        comms (iterable, optional): Names of commodities
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
    comms = pmax.columns.values if comms == None else comms

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
        if peak != None:
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


