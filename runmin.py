import capmin
import pandas as pd
import pandashp as pdshp
import pandaspyomo as pdpo
import pyomotools
import pdb
from coopr.opt.base import SolverFactory
from operator import itemgetter

building_shapefile = 'data/mnl/mnl_building'
edge_shapefile = 'data/mnl/mnl_edge'
vertex_shapefile = 'data/mnl/mnl_vertex'
data_spreadsheet = 'data/mnl/mnl.xlsx'

solver_name = 'gurobi' # possible (if licensed and binary in path): cplex, gurobi 

# load buildings and sum by type and nearest edge ID
# 1. read shapefile to DataFrame (with special geometry column)
# 2. group DataFrame by columns 'nearest' (ID of nearest edge) and 'type'
#    (residential, commercial, industrial, other)
# 3. sum by group and unstack, i.e. convert secondary index 'type' to columns
buildings = pdshp.read_shp(building_shapefile)
buildings_grouped = buildings.groupby(['nearest', 'type'])
total_area = buildings_grouped.sum()['total_area'].unstack()

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

# load spreadsheet
data = capmin.read_excel(data_spreadsheet)

# create and solve model
model = capmin.create_model(data, vertex, edge)
instance = model.create()
solver = SolverFactory(solver_name)
result = solver.solve(instance, tee=True)
instance.load(result)

# prepare input data similar to model for easier analysis
ig=itemgetter('Commodity', 'Process', 'Process-Commodity', 'Time', 'Area-Demand')
dfs = pyomotools.read_xls(data_spreadsheet)
commodity, process, process_commodity, time, area_demand = ig(dfs)

# read results to workspace
Pin = pdpo.get_entity(instance, 'Pin').unstack().unstack()
Pot = pdpo.get_entity(instance, 'Pot').unstack().unstack()
Psi = pdpo.get_entity(instance, 'Psi').unstack().unstack()
Pmax = pdpo.get_entity(instance, 'Pmax').unstack()
Xi = pdpo.get_entity(instance, 'Xi').unstack()
Sigma = pdpo.get_entity(instance, 'Sigma').unstack().unstack()
Rho = pdpo.get_entity(instance, 'Rho').unstack().unstack()
Kappa_hub = pdpo.get_entity(instance, 'Kappa_hub').unstack().unstack()
Epsilon_hub = pdpo.get_entity(instance, 'Epsilon_hub').unstack().unstack()
Epsilon_in = pdpo.get_entity(instance, 'Epsilon_in').unstack().unstack()
Epsilon_out = pdpo.get_entity(instance, 'Epsilon_out').unstack().unstack()
Tau = pdpo.get_entity(instance, 'Tau').unstack().unstack()
costs = pdpo.get_entity(instance, 'costs')

# alias for easier model inspection
m = instance

