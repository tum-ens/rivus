import geopandas
import pandashp
import shapelytools
import skeletrontools

streets_filename = 'streets.shp'
edge_filename = 'edge.shp'
vertex_filename = 'vertex.shp'

streets = geopandas.read_file(streets_filename)
streets = streets.to_crs(epsg=32632)  # EPSG:32632 == UTM Zone 32N (Germany!)

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
edge.to_file(edge_filename)
vertex.to_file(vertex_filename)