try:
    import pyomo.environ
    from pyomo.opt.base import SolverFactory
    PYOMO3 = False
except ImportError:
    import coopr.environ
    from coopr.opt.base import SolverFactory
    PYOMO3 = True
import geopandas
import os
import pandashp as pdshp
import rivus
from datetime import datetime

base_directory = os.path.join('data', 'haag15')
building_shapefile = os.path.join(base_directory, 'building')
edge_shapefile = os.path.join(base_directory, 'edge')
to_edge_shapefile = os.path.join(base_directory, 'to_edge')
vertex_shapefile = os.path.join(base_directory, 'vertex')
data_spreadsheet = os.path.join(base_directory, 'data.xlsx')

# scenarios

def scenario_base(data, vertex, edge):
    """Base scenario: change nothing-"""
    return data, vertex, edge
    
def scenario_no_heat_pump(data, vertex, edge):
    """No heat pump: not allowed"""
    process = data['process']
    process.loc['Heat pump domestic', 'cap-min'] = 0
    process.loc['Heat pump domestic', 'cap-max'] = 0
    process.loc['Heat pump plant', 'cap-min'] = 0
    process.loc['Heat pump plant', 'cap-max'] = 0
    return data, vertex, edge
    
def scenario_no_electric_heating(data, vertex, edge):
    """No electric heating at all"""
    process = data['process']
    process.loc['Heat pump domestic', 'cap-min'] = 0
    process.loc['Heat pump domestic', 'cap-max'] = 0
    process.loc['Heat pump plant', 'cap-min'] = 0
    process.loc['Heat pump plant', 'cap-max'] = 0
    process.loc['Elec heating domestic', 'cap-max'] = 0
    return data, vertex, edge

def scenario_high_demand(data, vertex, edge):
    """High demand: increase demand by 100%"""
    data['area_demand'] *= 2
    return data, vertex, edge

def scenario_renovation(data, vertex, edge):
    """Renovation: reduce heat demand of residential/commercial by 50%"""
    area_demand = data['area_demand']
    area_demand.ix[('residential', 'Heat'), 'peak'] *= 0.5
    area_demand.ix[('house', 'Heat'), 'peak'] *= 0.5
    area_demand.ix[('commercial', 'Heat'), 'peak'] *= 0.5
    area_demand.ix[('office', 'Heat'), 'peak'] *= 0.5
    area_demand.ix[('other', 'Heat'), 'peak'] *= 0.5
    return data, vertex, edge

def scenario_dh_cheap(data, vertex, edge):
    """DH cheap: reduce cost of DH pipe by 50%"""
    commodity = data['commodity']
    commodity.loc['Heat', 'cost-inv-fix'] *= 0.5
    commodity.loc['Heat', 'cost-inv-var'] *= 0.5
    return data, vertex, edge

def scenario_gas_expensive(data, vertex, edge):
    """Gas expensive: increase gas price by 50%"""
    commodity = data['commodity']
    commodity.loc['Gas', 'cost-var'] *= 1.5
    return data, vertex, edge
    
def scenario_gas_cheap(data, vertex, edge):
    """Gas cheap: decrease gas price by 50%"""
    commodity = data['commodity']
    commodity.loc['Gas', 'cost-var'] *= 0.5
    return data, vertex, edge

def scenario_elec_expensive(data, vertex, edge):
    """Elec expensive: increase electricity price by 100%"""
    commodity = data['commodity']
    commodity.loc['Elec', 'cost-var'] *= 2
    return data, vertex, edge
    
def scenario_dh_plant_cheap(data, vertex, edge):
    """DH plant cheap: decrease cost of DH plant by 50%"""
    process = data['process']
    process.loc['District heating plant', 'cost-inv-fix'] *= 0.5
    process.loc['District heating plant', 'cost-inv-var'] *= 0.5
    return data, vertex, edge
    
def scenario_heat_pump_better(data, vertex, edge):
    """Heat pump better: increase output ratio by 50%"""
    pro_co = data['process_commodity']
    pro_co.loc[('Heat pump domestic', 'Heat', 'Out'), 'ratio'] *= 1.5
    pro_co.loc[('Heat pump plant', 'Heat', 'Out'), 'ratio'] *= 1.5
    return data, vertex, edge
    
def scenario_heat_pump_expensive(data, vertex, edge):
    """Heat pump expensive: increase investment costs by 100%"""
    pro = data['process']
    pro.loc['Heat pump domestic', 'cost-inv-fix'] *= 2
    pro.loc['Heat pump domestic', 'cost-inv-var'] *= 2
    pro.loc['Heat pump plant', 'cost-inv-fix'] *= 2
    pro.loc['Heat pump plant', 'cost-inv-var'] *= 2
    return data, vertex, edge
    
def scenario_elec_very_expensive(data, vertex, edge):
    """Elec very expensive: increase electricity price by 400%"""
    commodity = data['commodity']
    commodity.loc['Elec', 'cost-var'] *= 5
    return data, vertex, edge
    
def scenario_elec_very_very_expensive(data, vertex, edge):
    """Elec very expensive: increase electricity price tenfold """
    commodity = data['commodity']
    commodity.loc['Elec', 'cost-var'] *= 10
    return data, vertex, edge

# solver

def setup_solver(optim, logfile='solver.log'):
    """Change solver options to custom values."""
    if optim.name == 'gurobi':
        # reference with list of option names
        # http://www.gurobi.com/documentation/5.6/reference-manual/parameters
        optim.set_options("logfile={}".format(logfile)) 
        optim.set_options("TimeLimit=12000")  # seconds
        optim.set_options("MIPFocus=2")  # 1=feasible, 2=optimal, 3=bound
        optim.set_options("MIPGap=1e-3")  # default = 1e-4
        optim.set_options("Threads=48")  # number of simultaneous CPU threads
    elif optim.name == 'glpk':
        # reference with list of options
        # execute 'glpsol --help'
        optim.set_options("log={}".format(logfile))
    else:
        print("Warning from setup_solver: no options set for solver "
            "'{}'!".format(optim.name))
    return optim

# helper functions
def prepare_result_directory(result_name):
    """ create a time stamped directory within the result folder """
    # timestamp for result directory
    now = datetime.now().strftime('%y%m%dT%H%M')

    # create result directory if not existent
    result_dir = os.path.join('result', '{}-{}'.format(result_name, now))
    if not os.path.exists(result_dir):
        os.makedirs(result_dir)

    return result_dir

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



def run_scenario(scenario, result_dir):
    # scenario name
    sce = scenario.__name__
    sce_nice_name = sce.replace('_', ' ').title()

    # prepare input data
    data = rivus.read_excel(data_spreadsheet)
    vertex = pdshp.read_shp(vertex_shapefile)
    edge = prepare_edge(edge_shapefile, building_shapefile)

    # apply scenario function to input data
    data, vertex, edge = scenario(data, vertex, edge)

    log_filename = os.path.join(result_dir, sce+'.log')

    # create & solve model
    prob = rivus.create_model(data, vertex, edge)
    if PYOMO3:
        prob = prob.create() # no longer needed in Pyomo 4+
    optim = SolverFactory('glpk')
    optim = setup_solver(optim, logfile=log_filename)
    result = optim.solve(prob, tee=True)
    if PYOMO3:
        prob.load(result) # no longer needed in Pyomo 4+

    # report
    rivus.save(prob, os.path.join(result_dir, sce+'.pgz'))
    rivus.report(prob, os.path.join(result_dir, sce+'.xlsx'))
    
    # plot without buildings
    rivus.result_figures(prob, os.path.join(result_dir, sce))
    
    # plot with buildings and to_edge lines
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
    # prepare result directory 
    result_name = os.path.basename(base_directory)
    result_dir = prepare_result_directory(result_name)  # name + time stamp

    scenarios = [
        scenario_base, 
        scenario_no_electric_heating,
        scenario_renovation, 
        scenario_no_heat_pump,
        scenario_dh_cheap, 
        scenario_high_demand,
        scenario_gas_expensive, 
        scenario_gas_cheap,
        scenario_elec_expensive,
        scenario_dh_plant_cheap, 
        scenario_heat_pump_better,
        scenario_heat_pump_expensive,
        scenario_elec_very_expensive,
        scenario_elec_very_very_expensive]

    for scenario in scenarios[-1:]:
        prob = run_scenario(scenario, result_dir)

