import os
import geopandas
from ..utils import pandashp
from ..utils import shapelytools
from ..utils import skeletrontools

# Consts
work_dir = os.path.normpath(r"C:\Users\Kristof\GIT\Masterarbeit\rivus\data\haag15")
EPSG_XY = 32632

# IN
streets_filename = 'streets.shp'
streets_filename_abs = os.path.join(work_dir, 'streets.shp')

# OUT
edge_apath = os.path.join(work_dir, 'edgeout.shp')
vertex_apath = os.path.join(work_dir, 'vertexout.shp')


streets = geopandas.read_file(streets_filename)
streets = streets.to_crs(epsg=EPSG_XY)  # EPSG:32632 == UTM Zone 32N (Germany!)

# filter away roads by type
road_types = ['motorway', 'motorway_link', 'primary', 'primary_link',
              'secondary', 'secondary_link', 'tertiary', 'tertiary_link',
              'residential', 'living_street', 'service', 'unclassified']
streets = streets[streets['type'].isin(road_types)]


skeleton = skeletrontools.skeletonize(streets,
                                      buffer_length=30,
                                      dissolve_length=15,
                                      simplify_length=30)
skeleton = shapelytools.one_linestring_per_intersection(skeleton)


skeleton = shapelytools.snappy_endings(skeleton, max_distance=100)
skeleton = shapelytools.one_linestring_per_intersection(skeleton)
skeleton = shapelytools.prune_short_lines(skeleton, min_length=55)

# convert back to GeoPandas
edge = geopandas.GeoDataFrame(geometry=skeleton, crs=streets.crs)
edge = edge.to_crs(epsg=4326)  # World Geodetic System (WGS84)
edge['Edge'] = edge.index

# derive vertex points
vertices = shapelytools.endpoints_from_lines(edge.geometry)
vertex = geopandas.GeoDataFrame(geometry=vertices, crs=edge.crs)
vertex['Vertex'] = vertex.index

pandashp.match_vertices_and_edges(vertex, edge)

# drop loops
edge = edge[~(edge['Vertex1'] == edge['Vertex2'])]

# if there are >1 edges that connect the same vertex pair, drop one of them
edge = edge.drop_duplicates(subset=['Vertex1', 'Vertex2'])

# write to file
edge.to_file(edge_apath)
vertex.to_file(vertex_apath)
