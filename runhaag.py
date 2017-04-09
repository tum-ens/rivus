import matplotlib.pyplot as plt
import os
import pandas as pd
import pandashp as pdshp
import rivus
try:
    import pyomo.environ
    from pyomo.opt.base import SolverFactory
    PYOMO3 = False
except ImportError:
    import coopr.environ
    from coopr.opt.base import SolverFactory
    PYOMO3 = True

base_directory = os.path.join('data', 'haag')
building_shapefile = os.path.join(base_directory, 'building')
edge_shapefile = os.path.join(base_directory, 'edge')
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


scenarios = [
    scenario_base,
    scenario_renovation]

# solver

def setup_solver(optim):
    """Change solver options to custom values."""
    if optim.name == 'gurobi':
        # reference with list of option names
        # http://www.gurobi.com/documentation/5.6/reference-manual/parameters
        optim.set_options("TimeLimit=500")  # seconds
        optim.set_options("MIPFocus=2")  # 1=feasible, 2=optimal, 3=bound
        optim.set_options("MIPGap=3e-4")  # default = 1e-4
        optim.set_options("Threads=3")  # number of simultaneous CPU threads
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
        'yes': 'other'}
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
    prob = rivus.create_model(data, vertex, edge)
    if PYOMO3:
        prob = prob.create() # no longer needed in Pyomo 4+
    optim = SolverFactory('gurobi')
    optim = setup_solver(optim)
    result = optim.solve(prob, tee=True)
    if PYOMO3:
        prob.load(result) # no longer needed in Pyomo 4+

    # create result directory if not existent
    result_dir = os.path.join('result', os.path.basename(base_directory))
    if not os.path.exists(result_dir):
        os.makedirs(result_dir)
    
    # report    
    rivus.report(prob, os.path.join(result_dir, 'report.xlsx'))
    
    # plots
    for com, plot_type in [('Elec', 'caps'), ('Heat', 'caps'), ('Gas', 'caps'),
                           ('Elec', 'peak'), ('Heat', 'peak')]:
        
        # two plot variants
        for plot_annotations in [False, True]:
            # create plot
            fig = rivus.plot(prob, com, mapscale=False, tick_labels=False, 
                             plot_demand=(plot_type == 'peak'),
                             annotations=plot_annotations)
            plt.title('')
            
            # save to file
            for ext, transp in [('png', True), ('png', False), ('pdf', True)]:
                transp_str = ('-transp' if transp and ext != 'pdf' else '')
                annote_str = ('-annote' if plot_annotations else '')
                
                # determine figure filename from scenario name, plot type, 
                # commodity, transparency, annotations and extension
                fig_filename = '{}-{}-{}{}{}.{}'.format(
                    sce, plot_type, com, transp_str, annote_str, ext) 
                fig_filename = os.path.join(result_dir, fig_filename)
                fig.savefig(fig_filename, dpi=300, bbox_inches='tight', 
                            transparent=transp)
                
    return prob
            
if __name__ == '__main__':
    for scenario in scenarios:
        prob = run_scenario(scenario)

