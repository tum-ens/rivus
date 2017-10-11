"""Collection of small rivus related helper functions

In use to avoid multiple solutions of the same task, like:

+ Setting up the solver.
+ Todo: Create needed directories

"""
from multiprocessing import cpu_count


def setup_solver(optim, logfile='solver.log', guro_time_lim=12000,
                 guro_mip_focus=2, guro_mip_gap=.001, guro_threads=None,
                 log_to_console=True):
    """Change solver options to custom values.

    Parameters
    ----------
    optim : SolverFactory
        pyomo Solver object from pyomo.opt.base
    logfile : str, optional
        default='solver.log'
        Name (Path) to the logfile
    guro_time_lim : int, optional
        unit is seconds | default=12000
    guro_mip_focus : int, optional
        default=2
        1=feasible, 2=optimal, 3=bound
    guro_mip_gap : float, optional
        our default=.001
        (gurobi's default: 1e-4)
    guro_threads : None, optional
        parallel solver tasks | default=None
        If None, no Threads parameter is set
        (gurobi takes <=CPU_count threads automatically)
        If greater than CPU_count then it is threshold to CPU_count
        If less than CPU_count then Thread is set with the parameter
    log_to_console : bool, optional
        Description
    log_to_console (Boolean, optional) If False, the output of the solver
        is not piped to the stdout.

    Example
    -------
    ::


        optim = SolverFactory('glpk')
        optim = setup_solver(optim, logfile=log_filename)

    Returns
    -------
    SolverFactory
        With applied modifications
    """
    if optim.name == 'gurobi':
        # reference with list of option names
        # http://www.gurobi.com/documentation/5.6/reference-manual/parameters
        to_console = 1 if log_to_console else 0
        optim.set_options("LogToConsole={}".format(to_console))
        optim.set_options("logfile={}".format(logfile))
        # guro_time_lim in seconds
        optim.set_options("TimeLimit={}".format(guro_time_lim))
        optim.set_options("MIPFocus={}".format(guro_mip_focus))
        # guro_mip_gap default = 1e-4
        optim.set_options("MIPGap={:.0e}".format(guro_mip_gap))
        if guro_threads is not None:
            CPUNum = cpu_count()
            # No more threads than CPUs
            thread_num = CPUNum if guro_threads > CPUNum else guro_threads
            optim.set_options("Threads={}".format(thread_num))
    elif optim.name == 'glpk':
        # reference with list of options
        # execute 'glpsol --help'
        if log_to_console:
            optim.set_options("log={}".format(logfile))
        else:
            optim.set_options("y={}".format(logfile))
    else:
        print("Warning from setup_solver: no options set for solver "
              "'{}'!".format(optim.name))
    return optim
