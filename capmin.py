""" CAPMIN: optimization model for distributed urban energy systems

CAPMIN optimizes topology and size of urban energy networks, energy conversion
and [to be done] energy storage.

"""
import coopr.pyomo as pyomo
import pandas as pd
import pyomotools

def create_model(filename, node, edge):
    """Return a CAPMIN model instance from input file""" 
    m = pyomo.ConcreteModel()
    m.name = 'CAPMIN'
    
    # DataFrames
    dfs = pyomotools.read_xls(filename)
    commodity = dfs['Commodity']    
    process = dfs['Process']
    process_commodity = dfs['Process-Commodity']
    #storage = dfs['Storage']
    time = dfs['Time']
    area_demand = dfs['Area-Demand']   
    
    # process input/output ratios
    r_in = process_commodity.xs('In', level='Direction')['ratio']
    r_out = process_commodity.xs('Out', level='Direction')['ratio']
    
    # energy hubs
    # are processes that satisfy three conditions:
    # 1. fixed investment costs == 0
    # 2. minimum capacity == 0
    # 3. has only one input commodity
    # In contrast to generic processes, which are at nodes, 
    # hubs are located in edges
    has_cost_inv_fix_0 = process['cost-inv-fix'] == 0
    has_cap_min_0 = process['cap-min'] == 0
    has_one_input = r_in.groupby(level='Process').count() == 1
    hub = process[ has_cost_inv_fix_0 & has_cap_min_0 & has_one_input ]
    
    # derive peak and demand of edges
    # use intersection to only leave area types existing both in edges and in
    # column 
    area_types = list(area_demand.index.levels[0])
    edge_areas = edge[edge.columns.intersection(area_types)]
   
    # helper function: calculates outer product of column in table area_demand
    # with specified series, which is applied to the  area columns of edge_areas
    def multiply_by_area_demand(series, column):
        return area_demand[column] \
               .ix[series.name] \
               .apply(lambda x: x*series) \
               .stack()
    
    # peak(edge, commodity) in kW
    peak = edge_areas.apply(lambda x: multiply_by_area_demand(x, 'peak')) \
                     .sum(axis=1) \
                     .unstack('Commodity')
    # demand(edge, commodity) in GWh [due to /1e6]
    demand = edge_areas.apply(lambda x: multiply_by_area_demand(x, 'demand')) \
                       .sum(axis=1) \
                       .unstack('Commodity') / 1e6
    
    # MODEL
    
    # Sets
    m.commodity = pyomo.Set(initialize=commodity.index)
    m.process = pyomo.Set(initialize=process.index)
    m.hub = pyomo.Set(initialize=hub.index, within=m.process)
    m.time = pyomo.Set(initialize=time.index)
    #m.storage = pyomo.Set(initialize=storage.index.levels[
    #                                 storage.index.names.index('Storage')])
    
    # Parameters
    # few should be needed
    
    # Variables
    
    # Constraints
    
    # Objective
    
    return m

    

