"""Functions to hold dedicated analysis runs on the graph objects.
networkx is the de-facto graph package, but igraph compatibility is also eligible.
"""
import networkx as nx
import warnings


def minimal_graph_anal(graphs, calc_spanning=True, graph_package='NX'):
    """Showcase interoperable connectivity analysis.

    Parameters
    ----------
    graphs : list
        networkx or igraph Graph objects.
        Awaited is the resulting ITERABLE of rivus.graph.to_graph functions.
    calc_spanning : bool, optional
        Default: True, sets whether to investigate:
        Is the graph of the built commodity also
        a minimal spanning tree of the street network?
    graph_package : str, optional
        Default: 'NX', Accepted: 'NX' or 'IGRAPH'.
        To ease the decision of which package is used.

    Returns
    -------
    list of dicts per graph
        + commodity
        + is_connected
        + connected_components (number of them)
        + is_minimal (if ``calc_spanning`` is True)
    """
    if len(graphs) < 1:
        warnings.info("Empty graph list was input to analyzer!")

    if graph_package not in ['NX', 'IGRAPH']:
        try:
            if graphs[0]['name'] != '':
                graph_package = 'IGRAPH'
        except KeyError:
            graph_package = 'NX'

    graphs_data = []
    for G in graphs:
        # print('Analyzing <{}> graph'.format(G.graph['Commodity']))
        if graph_package == 'NX':
            g_data = {
                'commodity': G.graph['Commodity'],
                'is_connected': nx.is_connected(G),
                'connected_components': nx.number_connected_components(G)}
            if calc_spanning:
                spanner = nx.minimum_spanning_tree(G)
                g_data['is_minimal'] = nx.is_isomorphic(G, spanner)
        elif graph_package == 'IGRAPH':
            # TODO Check this with igraph
            g_data = {
                'commodity': G['Commodity'],
                'is_connected': G.is_connected(),
                'connected_components': len(G.clusters())}
            if calc_spanning:
                spanner = G.spanning_tree(weights=G.es['weight'])
                g_data['is_minimal'] = G.isomorphic(spanner)
        graphs_data.append(g_data)
    return graphs_data
