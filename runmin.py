import capmin
import pandashp as pdshp

# load buildings and sum by type and nearest edge ID
# 1. read shapefile to DataFrame (with special geometry column)
# 2. group DataFrame by columns 'nearest' (ID of nearest edge) and 'type'
#    (residential, commercial, industrial, other)
# 3. sum by group and unstack, i.e. convert secondary index 'type' to columns
buildings = pdshp.read_shp('data/min/min_building')
buildings_grouped = buildings.groupby(['nearest', 'type'])
total_area = buildings_grouped.sum()['total_area'].unstack()

# load edges (streets) and join with summed areas 
# 1. read shapefile to DataFrame (with special geometry column)
# 2. join DataFrame total_area by IDs
# 3. fill missing values with 0
edges = pdshp.read_shp('data/min/min_edge')
edges_w_area = edges.join(total_area)
edges_w_area = edges_w_area.fillna(0)

# load nodes
nodes = pdshp.read_shp('data/min/min_node')

# create model
model = capmin.create_model('data/min/min.xlsx', nodes, edges_w_area)
instance = model.create()

