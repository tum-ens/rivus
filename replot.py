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
    
    for pf in pickle_filenames:
        prob = rivus.from_pickle(pf)
        rivus.result_figures(prob, os.path.splitext(pf)[0])

            
if __name__ == '__main__':
    for directory in sys.argv[1:]:
        replot(directory)

