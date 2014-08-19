import capmin
import coopr.environ
import pandas as pd
import pandashp as pdshp
from coopr.opt.base import SolverFactory
from operator import itemgetter

building_shapefile = 'data/haag_wgs84/building'
edge_shapefile = 'data/haag_wgs84/edge'
vertex_shapefile = 'data/haag_wgs84/vertex'
data_spreadsheet = 'data/haag/haag.xlsx'


def setup_solver(optim):
    """Change solver options to custom values."""
    if optim.name == 'gurobi':
        # reference with list of option names
        # http://www.gurobi.com/documentation/5.6/reference-manual/parameters
        optim.set_options("TimeLimit=600")  # seconds
        optim.set_options("MIPFocus=1")  # 1=feasible, 2=optimal, 3=bound
        optim.set_options("MIPGap=1e-4")  # default = 1e-4
        optim.set_options("Threads=2")  # 
    elif optim.name == 'glpk':
        # reference with list of options
        # execute 'glpsol --help'
        pass
    else:
        print("Warning from setup_solver: no options set for solver "
            "'{}'!".format(optim.name))
    return optim

# load buildings and sum by type and nearest edge ID
# 1. read shapefile to DataFrame (with special geometry column)
# 2. group DataFrame by columns 'nearest' (ID of nearest edge) and 'type'
#    (residential, commercial, industrial, other)
# 3. sum by group and unstack, i.e. convert secondary index 'type' to columns
buildings = pdshp.read_shp(building_shapefile)
building_type_mapping = { 
'church': 'other', 
'farm': 'other',
'hospital': 'residential',  
'hotel': 'commercial',
'house': 'residential',
'office': 'commercial',
'retail': 'commercial', 
'school': 'commercial',  
'yes': 'other',
}
buildings.replace(to_replace={'type': building_type_mapping}, inplace=True)
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
optim = setup_solver(optim)
result = optim.solve(prob, tee=True)
prob.load(result)

# prepare input data similar to model for easier analysis
entity_getter = itemgetter(
    'commodity', 'process', 'process_commodity', 'time', 'area_demand')
commodity, process, process_commodity, time, area_demand = entity_getter(data)


costs, Pmax, Kappa_hub, Kappa_process = capmin.get_constants(prob)
source, flows, hubs, proc_io, proc_tau = capmin.get_timeseries(prob)

#
edge_w_caps = edge.join(Pmax).fillna(0)
pdshp.write_shp('data/haag_wgs84/edge_w_caps', edge_w_caps)

edge_w_peak = edge.join(prob.peak).fillna(0)
pdshp.write_shp('data/haag_wgs84/edge_w_peak', edge_w_peak)
