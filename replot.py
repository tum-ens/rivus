import glob
import os
import rivus
import sys

def replot(directory):
    """Recreate result figures for all pickled rivus results in directory
    
    Args:
        directory: a directory with 1 or multiple pickled rivus instances
        
    Returns:
        Nothing
    """
    glob_pattern = os.path.join(directory, '*.pgz')
    pickle_filenames = glob.glob(glob_pattern)
    
    data_dir = os.path.join('data', os.path.basename(directory))
    # if directory = 'result/moosh' try to find a suitable building shapefile
    # in 'data/moosh'
    buildings = None
    building_filename = os.path.join(data_dir, 'building')
    if os.path.exists(building_filename+'.shp'):
        buildings = (building_filename, False)  # if True, color buildings
        
    # if data/.../to_edge exists, paint it
    shapefiles = None
    to_edge_filename = os.path.join(data_dir, 'to_edge')
    if os.path.exists(to_edge_filename+'.shp'):
        shapefiles = [{'name': 'to_edge',
                       'color': rivus.to_rgb(192, 192, 192),
                       'shapefile': to_edge_filename,
                       'zorder': 1,
                       'linewidth': 0.1}]

    for pf in pickle_filenames:
        prob = rivus.load(pf)
        figure_basename = os.path.splitext(pf)[0]
        if buildings:
            figure_basename += '_bld'
        rivus.result_figures(prob, figure_basename, 
                             buildings=buildings,
                             shapefiles=shapefiles)

            
if __name__ == '__main__':
    for directory in sys.argv[1:]:
        replot(directory)

