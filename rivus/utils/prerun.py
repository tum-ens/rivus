"""
    Collection of small rivus related util functions
    
    In use to avoid multiple solutions of the same
    problem.
"""
from multiprocessing import cpu_count

def setup_solver(optim, logfile='solver.log'):
    """Change solver options to custom values.
        Useage:
        optim = SolverFactory('glpk')
        optim = setup_solver(optim, logfile=log_filename)
    """
    if optim.name == 'gurobi':
        # reference with list of option names
        # http://www.gurobi.com/documentation/5.6/reference-manual/parameters
        optim.set_options("logfile={}".format(logfile))
        optim.set_options("TimeLimit=12000")  # seconds
        optim.set_options("MIPFocus=2")  # 1=feasible, 2=optimal, 3=bound
        optim.set_options("MIPGap=1e-3")  # default = 1e-4
        optim.set_options("Threads={}".format(cpu_count()))  # number of simultaneous CPU threads
    elif optim.name == 'glpk':
        # reference with list of options
        # execute 'glpsol --help'
        optim.set_options("log={}".format(logfile))
    else:
        print("Warning from setup_solver: no options set for solver "
              "'{}'!".format(optim.name))
    return optim