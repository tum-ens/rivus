"""Collection of small rivus related helper functions
    
In use to avoid multiple solutions of the same task, like:
    + Setting up the solver.
    - Todo: Create needed directories
"""
from multiprocessing import cpu_count


def setup_solver(optim, logfile='solver.log', guroTimeLimit=12000,
                 guroMIPFocus=2, guroMIPGap=.001, guroThreads=None):
    """Change solver options to custom values.

    Args:
        optim: (pyomo Solver object): See usage for example
        logfile (str, optional): default='solver.log'
            Name (Path) to the logfile
        guroTimeLimit (int, optional): unit is seconds | default=12000
        guroMIPFocus (int, optional): default=2
            1=feasible, 2=optimal, 3=bound
        guroMIPGap (float, optional): our default=.001 (gurobi's default: 1e-4)
        guroThreads (None, optional): parallel solver tasks | default=None
            If None, no Threads parameter is set 
                (gurobi takes <=CPU_count threads automatically)
            If greater than CPU_count then it is threshold to CPU_count
            If less than CPU_count then Thread is set with the parameter
    Usage:
        optim = SolverFactory('glpk')
        optim = setup_solver(optim, logfile=log_filename)
    """
    if optim.name == 'gurobi':
        # reference with list of option names
        # http://www.gurobi.com/documentation/5.6/reference-manual/parameters
        optim.set_options("logfile={}".format(logfile))
        optim.set_options("TimeLimit={}".format(guroTimeLimit))  # seconds
        optim.set_options("MIPFocus={}".format(guroMIPFocus))
        optim.set_options("MIPGap={:.0e}".format(guroMIPGap))  # default = 1e-4
        if guroThreads != None:
            CPUNum = cpu_count()
            # No more threads than CPUs
            threadNum = CPUNum if guroThreads > CPUNum else guroThreads
            optim.set_options("Threads={}".format(threadNum))
    elif optim.name == 'glpk':
        # reference with list of options
        # execute 'glpsol --help'
        optim.set_options("log={}".format(logfile))
    else:
        print("Warning from setup_solver: no options set for solver "
              "'{}'!".format(optim.name))
    return optim
