import geopandas
import pandas as pd
from ..utils import pandashp as pdshp
import shutil
import os

# Consts
inp_dir = os.path.normpath(r"C:\Users\Kristof\GIT\Masterarbeit\rivus\data\haag15")
out_dir = os.path.normpath(r"C:\Users\Kristof\GIT\Masterarbeit\rivus\data\haag15")
EPSG_XY = 32632

# IN
buildings_apath = os.path.join(inp_dir, 'building.shp')
edge_apath = os.path.join(inp_dir, 'edge.shp')

# OUT
to_edge_apath = os.path.join(out_dir, 'to_edge.shp')
buildings_mapped_apath = os.path.join(out_dir, 'building_w_nearest.shp')

# DO
# read
buildings = geopandas.read_file(buildings_apath)
edge = geopandas.read_file(edge_apath)

# buildings.head()
# edge.head()

# project to UTM zone 33N (=EPSG:32600 + zone number for north)
buildings = buildings.to_crs(epsg=EPSG_XY)
edge = edge.to_crs(epsg=EPSG_XY)

# find closest edge
to_edge = pdshp.find_closest_edge(buildings, edge, to_attr='Edge')
to_edge = geopandas.GeoDataFrame(to_edge)
to_edge.crs = edge.crs.copy()

# reproject back to geographic WGS 84 (EPSG:4326)
buildings = buildings.to_crs(epsg=4326)
edge = edge.to_crs(epsg=4326)
to_edge = to_edge.to_crs(epsg=4326)

# FINISH
to_edge.to_file(to_edge_apath)
buildings.to_file(buildings_mapped_apath)
