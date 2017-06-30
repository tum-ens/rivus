"""
    Collection of small rivus related util functions
    
    In use to avoid multiple solutions of the same
    problem.
"""
from multiprocessing import cpu_count

def setup_solver(optim, logfile='solver.log', guroTimeLimit=12000, guroMIPFocus= 2, guroMIPGap=.001, guroThreads=None):
    """Change solver options to custom values.
    
    Args:
        optim
        logfile (str, optional): Name (Path) to the logfile | default='solver.log'
        guroTimeLimit (int, optional): unit is seconds | default=12000
        guroMIPFocus (int, optional): 1=feasible, 2=optimal, 3=bound | default=2
        guroMIPGap (float, optional): default=.001
        guroThreads (None, optional): parallel solver tasks | default=None
            If None, no Threads parameter is set (gurobi takes <=CPU_count threads automatically)
            If greater than CPU_count then it is threshold to CPU_count
            If less than CPU_count then Thread is set with the parameter
    Useage:
        optim = SolverFactory('glpk')
        optim = setup_solver(optim, logfile=log_filename)
    """
    if optim.name == 'gurobi':

        # reference with list of option names
        # http://www.gurobi.com/documentation/5.6/reference-manual/parameters
        optim.set_options("logfile={}".format(logfile))
        optim.set_options("TimeLimit={}".format(guroTimeLimit))  # seconds
        optim.set_options("MIPFocus={}".format(guroMIPFocus))  # 1=feasible, 2=optimal, 3=bound
        optim.set_options("MIPGap={:.0e}".format(guroMIPGap))  # default = 1e-4
        if guroThreads != None:
            cpunum = cpu_count()
            threadnum = cpunum if guroThreads > cpunum else guroThreads  # no more threads than CPUs
            optim.set_options("Threads={}".format(threadnum))  # number of simultaneous CPU threads
    elif optim.name == 'glpk':
        # reference with list of options
        # execute 'glpsol --help'
        optim.set_options("log={}".format(logfile))
    else:
        print("Warning from setup_solver: no options set for solver "
              "'{}'!".format(optim.name))
    return optim