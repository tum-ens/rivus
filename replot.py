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
    glob_pattern = os.path.join(directory, '*.pickle')
    pickle_filenames = glob.glob(glob_pattern)
    
    print(pickle_filenames)
    
    # if directory = 'result/moosh' try to find a suitable building shapefile
    # in 'data/moosh'
    buildings = None
    building_filename = os.path.join('data', 
                                     os.path.basename(directory), 
                                     'building')
    if os.path.exists(building_filename+'.shp'):
        buildings = building_filename
    
    for pf in pickle_filenames:
        prob = rivus.from_pickle(pf)
        rivus.result_figures(prob, os.path.splitext(pf)[0], 
                             buildings=buildings)

            
if __name__ == '__main__':
    for directory in sys.argv[1:]:
        replot(directory)

