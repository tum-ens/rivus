""" CAPMIN: optimization model for distributed urban energy systems

CAPMIN optimizes topology and size of urban energy networks, energy conversion
and [to be done] energy storage.

"""
import coopr.pyomo as pyomo
import itertools
import pandas as pd
import pyomotools
import pdb

def create_model(filename, vertex, edge):
    """Return a CAPMIN model instance from input file""" 
    m = pyomo.ConcreteModel()
    m.name = 'CAPMIN'
    
    # DataFrames
    dfs = pyomotools.read_xls(filename)
    commodity = dfs['Commodity']    
    process = dfs['Process']
    process_commodity = dfs['Process-Commodity']
    #storage = dfs['Storage']
    time = dfs['Time']
    area_demand = dfs['Area-Demand']   
    
    # process input/output ratios
    m.r_in = process_commodity.xs('In', level='Direction')['ratio']
    m.r_out = process_commodity.xs('Out', level='Direction')['ratio']
    
    # energy hubs
    # are processes that satisfy three conditions:
    # 1. fixed investment costs == 0
    # 2. minimum capacity == 0
    # 3. has only one input commodity
    # 4. the input commodity ratio has value 1
    # In contrast to generic processes, which are at nodes, 
    # hubs are located in edges
    has_cost_inv_fix_0 = process['cost-inv-fix'] == 0
    has_cap_min_0 = process['cap-min'] == 0
    has_one_input = m.r_in.groupby(level='Process').count() == 1
    has_r_in_1 = m.r_in.groupby(level='Process').sum() == 1
    hub = process[ has_cost_inv_fix_0 & has_cap_min_0 & has_one_input & has_r_in_1]   
    
    # derive peak and demand of edges
    # use intersection to only leave area types existing both in edges and in
    # column 
    area_types = list(area_demand.index.levels[0])
    edge_areas = edge[edge.columns.intersection(area_types)]
   
    # helper function: calculates outer product of column in table area_demand
    # with specified series, which is applied to the columns of edge_areas
    def multiply_by_area_demand(series, column):
        return area_demand[column] \
               .ix[series.name] \
               .apply(lambda x: x*series) \
               .stack()
    
    # peak(edge, commodity) in kW
    m.peak = edge_areas.apply(lambda x: multiply_by_area_demand(x, 'peak')) \
                       .sum(axis=1) \
                       .unstack('Commodity')
    # demand(edge, commodity) in GWh [due to /1e6]
    m.demand = edge_areas.apply(lambda x: multiply_by_area_demand(x, 'demand')) \
                         .sum(axis=1) \
                         .unstack('Commodity') / 1e6
    
    edge.set_index(['Vertex1', 'Vertex2'], inplace=True)
    arcs = [arc for (v1, v2) in edge.index for arc in ((v1, v2), (v2, v1))]
    
    # derive list of neighbours for each vertex
    m.neighbours = {}
    for (v1, v2) in arcs:
        m.neighbours.setdefault(v1, [])
        m.neighbours[v1].append(v2)

    # MODEL
    
    # Sets
    m.commodity = pyomo.Set(initialize=commodity.index)
    m.process = pyomo.Set(initialize=process.index)
    m.hub = pyomo.Set(initialize=hub.index, within=m.process)
    m.time = pyomo.Set(initialize=time.index)
    #m.storage = pyomo.Set(initialize=storage.index.levels[
    #                                 storage.index.names.index('Storage')])
    m.vertex = pyomo.Set(initialize=vertex.index)
    m.edge = pyomo.Set(within=m.vertex*m.vertex, initialize=edge.index)
    m.arc = pyomo.Set(within=m.vertex*m.vertex, initialize=arcs)
    
    m.cost_type = pyomo.Set(initialize=['Inv', 'Fix', 'Var', 'Fuel'])
    
    # Parameters
    # no or few will be needed
    
    # Variables
    
    # edges and arcs
    m.Sigma = pyomo.Var(m.edge, m.commodity, m.time, within=pyomo.NonNegativeReals)
    m.Pin = pyomo.Var(m.arc, m.commodity, m.time, within=pyomo.NonNegativeReals)
    m.Pot = pyomo.Var(m.arc, m.commodity, m.time, within=pyomo.NonNegativeReals)
    m.Psi = pyomo.Var(m.arc, m.commodity, m.time, within=pyomo.Binary)
    m.Pmax = pyomo.Var(m.edge, m.commodity, within=pyomo.NonNegativeReals)
    m.Xi = pyomo.Var(m.edge, m.commodity, within=pyomo.Binary)
    
    # vertices
    m.Rho = pyomo.Var(m.vertex, m.commodity, m.time, within=pyomo.NonNegativeReals)

    # hubs
    m.Kappa_hub = pyomo.Var(m.edge, m.hub, within=pyomo.NonNegativeReals)
    m.Epsilon_hub = pyomo.Var(m.edge, m.hub, m.time, within=pyomo.NonNegativeReals)

    # processes
    m.Kappa_process = pyomo.Var(m.vertex, m.process, within=pyomo.NonNegativeReals)
    m.Tau = pyomo.Var(m.vertex, m.process, m.time)
    m.Epsilon_in = pyomo.Var(m.vertex, m.process, m.commodity, m.time, within=pyomo.NonNegativeReals)
    m.Epsilon_out = pyomo.Var(m.vertex, m.process, m.commodity, m.time, within=pyomo.NonNegativeReals)
    
    # costs
    m.costs = pyomo.Var(m.cost_type, within=pyomo.NonNegativeReals)
    
    # Constraints
    
    # edges/arcs
    def peak_satisfaction_rule(m, e, co, t):
        if not co in m.co_demand:
            return pyomo.Constraint.Skip
        else:
            provided_power = hub_balance(m, e, co, t)
            return m.peak[e,c,t] * time.loc[t]['scale'] <= provided_power
            
    def edge_supply_rule(m, e, co, t):
        needed_power = - hub_balance(m, e, co, t)
        return m.Sigma(e, co, t) >= needed_power
    
    def edge_equation_rule(m, e, co, t):
        (a, b) = create_arc_pair(e)
        length = edge.loc[e]['geometry'].length
        
        flow_in = ( 1 - length * commodity.loc[co]['loss-var']) \
                * ( m.Pin[a, co, t] - m.Pin[b, co, t] )
        flow_out =  m.Pot[a, co, t] - m.Pot[b, co, t]
        fixed_losses = ( m.Psi[a, co, t] + m.Psi[b, co, t] ) \
                     * length * commodity.loc[co]['loss-fix']
        
        return m.Sigma(e, co, t) <= flow_in - flow_out - fixed_losses 
        
    def arc_flow_by_capacity_rule(m, a, co, t):
        e = find_matching_edge(m, a)        
        return m.Pin[a, co, t] <= m.Psi[a, co, t] * m.Pmax[e, co]
        
    def arc_unidirectionality_rule(m, a, co, t):
        b = reverse_arc(a)
        return m.Psi[a, co, t] + m.Psi[b, co, t] <= 1
        
    def edge_capacity_rule(m, e, co):
        return m.Pmax[e, co] <= m.Xi[e, co] * commodity.loc[co]['cap-max']
        
    # hubs
    def hub_output_by_capacity_rule(m, e, h, t):
        return m.Epsilon_hub[e, h, t] <= m.Kappa_hub[e, h]
        
    def hub_capacity(m, e, h):
        return m.Kappa_hub[e, h] <= hub.loc[h]['cap-max']
        
    # vertex
    def vertex_equation_rule(m, v, co, t):
        flow_required = - flow_balance(m, v, co, t)
        process_required = - process_balance(m, v, co, t)
        return m.Rho[v, co, t] >= flow_required + process_required # + storage_required
    
    def process_throughput_rule(m, v, p, t):
        return m.Tau[v, p, t] == throughput_sum(m, v, p, t)
        
    def process_throughput_by_capacity_rule(m, v, p, t):
        return m.Tau[v, p, t] <= m.Kappa_process[v, p]
    
    def process_capacity_rule(m, v, p):
        return m.Kappa_process[v, p] <= process.loc[p]['cap-max']
        
    def process_input_rule(m, v, p, co, t):
        return m.Epsilon_in[v, p, co, t] == m.Tau[v, p, t] * r_in.loc[p, co]
        
    def process_output_rule(m, v, p, co, t):
        return m.Epsilon_out[v, p, co, t] == m.Tau[v, p, t] * r_out.loc[p, co]
    
    # Objective
    def obj_rule(m):
        return pyomo.summation(m.costs)
    
    # Equation declarations
    
    # edges/arcs
    m.peak_satisfaction = pyomo.Constraint(m.edge, m.commodity, m.time)
    m.edge_supply = pyomo.Constraint(m.edge, m.commodity, m.time)
    m.edge_equation = pyomo.Constraint(m.edge, m.commodity, m.time)
    m.arc_flow_by_capacity = pyomo.Constraint(m.arc, m.commodity, m.time)
    m.arc_unidirectionality = pyomo.Constraint(m.arc, m.commodity, m.time)
    m.edge_capacity = pyomo.Constraint(m.edge, m.commodity)

    # hubs
    m.hub_output_by_capacity = pyomo.Constraint(m.edge, m.hub, m.time)
    m.hub_capacity = pyomo.Constraint(m.edge, m.hub)
    
    # vertex
    m.vertex_equation = pyomo.Constraint(m.vertex, m.commodity, m.time)
    
    # process
    m.process_throughput = pyomo.Constraint(m.vertex, m.process, m.time)
    m.process_throughput_by_capacity = pyomo.Constraint(m.vertex, m.process, m.time)
    m.process_capacity = pyomo.Constraint(m.vertex, m.process)
    m.process_input = pyomo.Constraint(m.vertex, m.process, m.commodity, m.time)
    m.process_output = pyomo.Constraint(m.vertex, m.process, m.commodity, m.time)

    # costs
    m.def_costs = pyomo.Constraint(m.cost_type)
    m.obj = pyomo.Objective(sense=pyomo.minimize)
    
    return m




def hub_balance(m, e, co, t):
    """ Calculate commodity balance in an edge from/to hubs. """
    balance = 0
    for h in m.hub:
        if co in m.r_in.loc[h].index:
            balance -= m.Epsilon_hub(e, h, t) * m.r_in.loc[h, co]
        if co in m.r_out.loc[h].index:
            balance += m.Epsilon_hub(e, h, t) * m.r_out.loc[h, co]
    return balance
    
def flow_balance(m, v, co, t):
    """ Calculate commodity flow balance in a vertex from/to arcs. """
    balance = 0
    for w in m.neighbours[v]:        
        balance += m.Pot[(w, v), co, t]
        balance -= m.Pin[(v, w), co, t]
    return balance
        
def process_balance(m, v, co, t):
    """ Calculate commodity balance in a vertex from/to processes. """
    balance = 0
    for p in m.process:
        if co in m.r_in.loc[p].index:
            balance -= m.Epsilon_in[v, p, co, t]
        if co in m.r_out.loc[p].index:
            balance += m.Epsilon_out[v, p, co, t]
    return balance

def throughput_sum(m, v, p, t):
    """ Calculate process throughput as sum of inputs. """
    throughput = 0
    for co in m.commodity:
        if co in m.r_in.loc[p].index:
            throughput += m.Epsilon_in[v, p, co, t] * m.r_rin.loc[p, co]
    return throughput

def find_matching_edge(m, a):
    """ Return edge for a given arc. """
    if a in m.edge:
        return (a[0], a[1])
    else:
        return (a[1], a[0])

def create_arc_pair(e):
    """ Return pair of arcs for a given edge. """
    a = (e[0], e[1])
    b = (e[1], e[0])
    return (a, b)
    
def reverse_arc(a):
    """ Return direction-inverted version of a given arc. """
    return (a[1], a[0])
    

