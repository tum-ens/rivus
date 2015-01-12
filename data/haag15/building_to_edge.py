import pandas as pd
import pandashp as pdshp
import shutil

# IN
buildings_filename = 'building' 
edge_filename = 'edge'

# OUT
to_edge_filename = 'to_edge'
blds_w_near_filename = 'building_w_nearest'

# DO
buildings = pdshp.read_shp(buildings_filename)
edge = pdshp.read_shp(edge_filename)
to_edge = pdshp.find_closest_edge(buildings, edge, to_attr='Edge')

# FINISH
pdshp.write_shp(to_edge_filename, to_edge)
pdshp.write_shp(blds_w_near_filename, buildings, write_index=False)

shutil.copyfile(edge_filename+'.prj', to_edge_filename+'.prj')
shutil.copyfile(buildings_filename+'.prj', blds_w_near_filename+'.prj') 