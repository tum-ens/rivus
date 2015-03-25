import glob
import os
import pandas as pd
import rivus
import sys

def reanalyse(directory):
    """Return constants for all pickled rivus results in directory
    
    Args:
        directory: a directory with 1 or multiple pickled rivus instances
        
    Returns:
        tuple (demand, cost, Pmax, Kappa_hub, Kappa_process) of concatenated
        DataFrames
    """
    glob_pattern = os.path.join(directory, '*.pgz')
    pickle_filenames = glob.glob(glob_pattern)
    
    demand = {}
    cost = {}
    Pmax = {} 
    Kappa_hub = {}
    Kappa_process = {}
    
    for pf in pickle_filenames:
        # load original problem object including solution
        prob = rivus.load(pf)
        
        # truncate directory name and extension from pickle filename
        # remove 'scenario_' prefix, if present
        scenario_name = os.path.splitext(os.path.basename(pf))[0]
        scenario_name = scenario_name.replace('scenario_', '')
        
        # retrieve costs and capacities from result
        constants = rivus.get_constants(prob)
        
        # assign dict values per scenario
        cost[scenario_name] = constants[0]
        Pmax[scenario_name] = constants[1]
        Kappa_hub[scenario_name] = constants[2]
        Kappa_process[scenario_name] = constants[3]
        demand[scenario_name] = prob.peak
        
    # merge into single dataframe
    demand = pd.concat(demand, axis=1)
    cost = pd.concat(cost, axis=1)
    Pmax = pd.concat(Pmax, axis=1)
    Kappa_hub = pd.concat(Kappa_hub, axis=1)
    Kappa_process = pd.concat(Kappa_process, axis=1)
    
    return demand, cost, Pmax, Kappa_hub, Kappa_process
            
if __name__ == '__main__':
    for directory in sys.argv[1:]:
        demand, cost, Pmax, Kappa_hub, Kappa_process = reanalyse(directory)

