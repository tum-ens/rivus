import coopr.environ
import matplotlib.pyplot as plt
import os
import pandas as pd
import pandashp as pdshp
import rivus
from coopr.opt.base import SolverFactory

base_directory = os.path.join('data', 'mnl')
building_shapefile = os.path.join(base_directory, 'mnl_building')
edge_shapefile = os.path.join(base_directory, 'mnl_edge')
vertex_shapefile = os.path.join(base_directory, 'mnl_vertex')
data_spreadsheet = os.path.join(base_directory, 'mnl.xlsx')


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

# load spreadsheet data
data = rivus.read_excel(data_spreadsheet)

# create and solve model
model = rivus.create_model(data, vertex, edge)
prob = model.create()
solver = SolverFactory('gurobi')
result = solver.solve(prob, tee=True)
prob.load(result)

# load results
costs, Pmax, Kappa_hub, Kappa_process = rivus.get_constants(prob)
source, flows, hub_io, proc_io, proc_tau = rivus.get_timeseries(prob)


result_dir = os.path.join('result', os.path.basename(base_directory))

# create result directory if not existing already
if not os.path.exists(result_dir):
    os.makedirs(result_dir)
    

rivus.report(prob, os.path.join(result_dir, 'report.xlsx'))

# plot all caps (and demands if existing)
for com, plot_type in [('Elec', 'caps'), ('Heat', 'caps'), ('Gas', 'caps'),
                       ('Elec', 'peak'), ('Heat', 'peak')]:
    
    # create plot
    fig = rivus.plot(prob, com, mapscale=False, tick_labels=False, 
                      plot_demand=(plot_type == 'peak'))
    plt.title('')
    # save to file
    for ext in ['png', 'pdf']:
            
        # determine figure filename from plot type, commodity and extension
        fig_filename = os.path.join(
            result_dir, '{}-{}.{}').format(plot_type, com, ext)
        fig.savefig(fig_filename, dpi=300, bbox_inches='tight', 
                    transparent=(ext=='pdf'))
