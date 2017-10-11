import pandas as pd
from . import shapelytools
import warnings
from shapely.geometry import LineString
from geopandas import GeoDataFrame


def match_vertices_and_edges(vertices, edges, vertex_cols=('Vertex1', 'Vertex2')):
    """Add columns to edges DataFrame, with the corresponding vertex IDS per edge.

    Identifies, which nodes coincide with the endpoints of edges and creates
    matching IDs for matching points, thus creating a node-edge graph whose
    edges are encoded purely by node ID pairs. The optional argument
    vertex_cols specifies which DataFrame columns of edges are added, default
    is 'Vertex1' and 'Vertex2'.

    Args:
        vertices (DataFrame): pandas DataFrame with geometry column of type Point
        edges: pandas DataFrame with geometry column of type LineString
        vertex_cols (indexable): tuple of 2 strings for the IDs numbers

    Returns:
        Nothing, the matching IDs are added to the columns vertex_cols in
        argument edges

    Note:
        Although different column names than ``Vertex1`` and ``Vertex2`` are possible,
        if you want to work with ``rivus.main`` then you should use these as these
        are pretty much hart coded into the other functions...
    """

    vertex_indices = []
    for e, line in enumerate(edges.geometry):
        edge_endpoints = []
        for k, vertex in enumerate(vertices.geometry):
            if line.touches(vertex) or line.intersects(vertex):
                edge_endpoints.append(vertices.index[k])
            # For imperfectly drawn vector layers: TODO CRS-relevant radius
            # if (vertex.buffer(0.001).intersects(line) or
            #         line.intersects(vertex)):
            #     edge_endpoints.append(vertices.index[k])

        if len(edge_endpoints) == 0:
            warnings.warn("edge " + str(e) +
                          " has no endpoints: " + str(edge_endpoints))
        elif len(edge_endpoints) == 1:
            warnings.warn("edge " + str(e) +
                          " has only 1 endpoint: " + str(edge_endpoints))

        vertex_indices.append(edge_endpoints)

    edges[vertex_cols[0]] = pd.Series([min(n1n2) for n1n2 in vertex_indices],
                                      index=edges.index)
    edges[vertex_cols[1]] = pd.Series([max(n1n2) for n1n2 in vertex_indices],
                                      index=edges.index)


def find_closest_edge(polygons, edges, to_attr='index', column='nearest'):
    """Find closest edge for centroid of polygons.

    Args:
        polygons (GeoDataFrame): GeoDataFrame with Polygons
        edges (GeoDataFrame): GeoDataFrame with LineStrings
        to_attr (str): a column name in GeoDataFrame edges (default: index)
        column (str): a column name to be added/overwrite in ``polygons`` with
                the value of column ``to_attr`` from the nearest edge in edges

    Returns:
        a list of LineStrings connecting polygons' centroids with the nearest
        point in in edges. Side effect: polygons receives new column with the
        attribute value of nearest edge. Warning: if column exists, it is
        overwritten.
    """

    connecting_lines = []
    nearest_indices = []
    centroids = [b.centroid for b in polygons['geometry']]

    for centroid in centroids:
        nearest_edge, _, nearest_index = shapelytools.closest_object(
            edges['geometry'], centroid)
        nearest_point = shapelytools.project_point_to_object(
            centroid, nearest_edge)

        connecting_lines.append(
            LineString(tuple(centroid.coords) + tuple(nearest_point.coords)))

        nearest_indices.append(edges[to_attr][nearest_index])

    polygons[column] = pd.Series(nearest_indices, index=polygons.index)

    return GeoDataFrame(geometry=connecting_lines, crs=polygons.crs)


def total_bounds(gdf):
    """Return bounding box (minx, miny, maxx, maxy) of all geometries.

    Parameters
    ----------
    gdf : GeoDataFrame
        Any GeoDataFrame, in rivus usually vertex or edge.

    Returns
    -------
    Tuple
        global (minx, miny, maxx, maxy)
    """
    b = gdf.bounds
    return (b['minx'].min(),
            b['miny'].min(),
            b['maxx'].max(),
            b['maxy'].max())
