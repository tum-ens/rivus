import coopr.environ
import geopandas
import matplotlib.pyplot as plt
import os
import pandas as pd
import pandashp as pdshp
import rivus
from coopr.opt.base import SolverFactory

base_directory = os.path.join('data', 'haag15')
building_shapefile = os.path.join(base_directory, 'building_w_nearest')
edge_shapefile = os.path.join(base_directory, 'edge')
to_edge_shapefile = os.path.join(base_directory, 'to_edge')
vertex_shapefile = os.path.join(base_directory, 'vertex')
data_spreadsheet = os.path.join(base_directory, 'data.xlsx')

# scenarios

def scenario_base(data, vertex, edge):
    """Base scenario: change nothing-"""
    return data, vertex, edge

def scenario_renovation(data, vertex, edge):
    """Renovation: reduce heat demand of residential/other by 50%"""
    area_demand = data['area_demand']
    area_demand.ix[('residential', 'Heat'), 'peak'] *= 0.5
    area_demand.ix[('other', 'Heat'), 'peak'] *= 0.5
    return data, vertex, edge

def scenario_dh_cheap(data, vertex, edge):
    """DH cheap: reduce cost of DH pipe by 50%"""
    commodity = data['commodity']
    commodity.loc['Heat', 'cost-inv-fix'] *= 0.5
    commodity.loc['Heat', 'cost-inv-var'] *= 0.5
    return data, vertex, edge

def scenario_gas_expensive(data, vertex, edge):
    commodity = data['commodity']
    commodity.loc['Gas', 'cost-var'] *= 1.5
    return data, vertex, edge

def scenario_elec_expensive(data, vertex, edge):
    commodity = data['commodity']
    commodity.loc['Elec', 'cost-var'] *=2
    return data, vertex, edge
    
scenarios = [scenario_base, scenario_renovation, scenario_dh_cheap, 
             scenario_gas_expensive, scenario_elec_expensive]

# solver

def setup_solver(optim):
    """Change solver options to custom values."""
    if optim.name == 'gurobi':
        # reference with list of option names
        # http://www.gurobi.com/documentation/5.6/reference-manual/parameters
        optim.set_options("TimeLimit=14400")  # seconds
        optim.set_options("MIPFocus=2")  # 1=feasible, 2=optimal, 3=bound
        optim.set_options("MIPGap=5e-4")  # default = 1e-4
        optim.set_options("Threads=48")  # number of simultaneous CPU threads
    elif optim.name == 'glpk':
        # reference with list of options
        # execute 'glpsol --help'
        pass
    else:
        print("Warning from setup_solver: no options set for solver "
            "'{}'!".format(optim.name))
    return optim

# helper functions

def prepare_edge(edge_shapefile, building_shapefile):
    """Create edge graph with grouped building demands.
    """
    # load buildings and sum by type and nearest edge ID
    # 1. read shapefile to DataFrame (with special geometry column)
    # 2. group DataFrame by columns 'nearest' (ID of nearest edge) and 'type'
    #    (residential, commercial, industrial, other)
    # 3. sum by group and unstack, i.e. convert secondary index 'type' to columns
    buildings = geopandas.read_file(building_shapefile+'.shp')
    buildings = buildings.convert_objects(convert_numeric=True)
    building_type_mapping = {
        'basin': 'other', 'chapel': 'other', 'church': 'other',
        'farm_auxiliary': 'other', 'greenhouse': 'other',
        'school': 'public',
        'office': 'commercial', 'restaurant': 'commercial',
        'yes': 'residential', 'house': 'residential'}
    buildings.replace(to_replace={'type': building_type_mapping}, inplace=True)
    buildings = buildings.to_crs(epsg=32632)
    buildings['AREA'] = buildings.area
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
    return edge



def run_scenario(scenario):
    # scenario name
    sce = scenario.__name__
    sce_nice_name = sce.replace('_', ' ').title()

    # prepare input data
    data = rivus.read_excel(data_spreadsheet)
    vertex = pdshp.read_shp(vertex_shapefile)
    edge = prepare_edge(edge_shapefile, building_shapefile)

    # apply scenario function to input data
    data, vertex, edge = scenario(data, vertex, edge)

    # create & solve model
    model = rivus.create_model(data, vertex, edge)
    prob = model.create()
    optim = SolverFactory('gurobi')
    optim = setup_solver(optim)
    result = optim.solve(prob, tee=True)
    prob.load(result)

    # create result directory if not existent
    result_dir = os.path.join('result', os.path.basename(base_directory))
    if not os.path.exists(result_dir):
        os.makedirs(result_dir)

    # report
    rivus.save_log(result, os.path.join(result_dir, sce+'.log'))
    rivus.save(prob, os.path.join(result_dir, sce+'.pgz'))
    rivus.report(prob, os.path.join(result_dir, sce+'.xlsx'))
    
    # plot without buildings
    rivus.result_figures(prob, os.path.join(result_dir, sce))
    
    # plot with buildings and to_edge
    more_shapefiles = [{'name': 'to_edge',
                        'color': rivus.to_rgb(192, 192, 192),
                        'shapefile': to_edge_shapefile,
                        'zorder': 1,
                        'linewidth': 0.1}]
    rivus.result_figures(prob, os.path.join(result_dir, sce+'_bld'), 
                         buildings=(building_shapefile, False),
                         shapefiles=more_shapefiles)


    return prob

if __name__ == '__main__':
    for scenario in scenarios:
        prob = run_scenario(scenario)

