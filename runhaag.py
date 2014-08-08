import capmin
import coopr.environ
import pandas as pd
import pandashp as pdshp
from coopr.opt.base import SolverFactory
from operator import itemgetter

building_shapefile = 'data/haag/buildings_w_nearest'
edge_shapefile = 'data/haag/edge'
vertex_shapefile = 'data/haag/vertex'
data_spreadsheet = 'data/haag/haag.xlsx'

# load buildings and sum by type and nearest edge ID
# 1. read shapefile to DataFrame (with special geometry column)
# 2. group DataFrame by columns 'nearest' (ID of nearest edge) and 'type'
#    (residential, commercial, industrial, other)
# 3. sum by group and unstack, i.e. convert secondary index 'type' to columns
buildings = pdshp.read_shp(building_shapefile)
buildings_grouped = buildings.groupby(['nearest', 'type'])
total_area = buildings_grouped.sum()['AREA'].unstack()

# load edges (streets) and join with summed areas 
# 1. read shapefile to DataFrame (with geometry column)
# 2. join DataFrame total_area on index (=ID)
# 3. fill missing values with 0
edge = pdshp.read_shp(edge_shapefile)
edge = edge.set_index('Edge')
edge = edge.join(total_area)
edge = edge.fillna(0)

# load nodes
vertex = pdshp.read_shp(vertex_shapefile)

# load spreadsheet data
data = capmin.read_excel(data_spreadsheet)

# create & solve model
model = capmin.create_model(data, vertex, edge)
prob = model.create()
optim = SolverFactory('gurobi')
result = optim.solve(prob, tee=True)
prob.load(result)

# prepare input data similar to model for easier analysis
entity_getter = itemgetter(
    'Commodity', 'Process', 'Process-Commodity', 'Time', 'Area-Demand')
co, pro, prco, time, ad = entity_getter(data)

# read results to workspace
Pin = capmin.get_entity(prob, 'Pin').unstack().unstack()
Pot = capmin.get_entity(prob, 'Pot').unstack().unstack()
Psi = capmin.get_entity(prob, 'Psi').unstack().unstack()
Pmax = capmin.get_entity(prob, 'Pmax').unstack()
Xi = capmin.get_entity(prob, 'Xi').unstack()
Sigma = capmin.get_entity(prob, 'Sigma').unstack().unstack()
Rho = capmin.get_entity(prob, 'Rho').unstack().unstack()
Kappa_hub = capmin.get_entity(prob, 'Kappa_hub').unstack().unstack()
Epsilon_hub = capmin.get_entity(prob, 'Epsilon_hub').unstack().unstack()
Epsilon_in = capmin.get_entity(prob, 'Epsilon_in').unstack().unstack()
Epsilon_out = capmin.get_entity(prob, 'Epsilon_out').unstack().unstack()
Tau = capmin.get_entity(prob, 'Tau').unstack().unstack()
costs = capmin.get_entity(prob, 'costs')

# alias for easier model inspection
m = prob

