""" CAPMIN: optimization model for distributed urban energy systems

CAPMIN optimizes topology and size of urban energy networks, energy conversion.

"""
import coopr.pyomo as pyomo
import itertools
import pandas as pd
import pyomotools
import pdb

def create_model(filename, vertex, edge):
    """Return a CAPMIN model instance from input file and spatial input. """ 
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
    
    # reindex edges to vertex tuple index
    vertex.set_index('Vertex', inplace=True)
    edge.set_index(['Vertex1', 'Vertex2'], inplace=True)
    m.peak.index = edge.index
    
    # construct arc set of directed (i,j), (j,i) edges
    arcs = [arc for (v1, v2) in edge.index for arc in ((v1, v2), (v2, v1))]
    
    # derive list of neighbours for each vertex
    m.neighbours = {}
    for (v1, v2) in arcs:
        m.neighbours.setdefault(v1, [])
        m.neighbours[v1].append(v2)
        
    # find all commodities for which there exists demand
    co_demand = set(area_demand.index.get_level_values('Commodity'))

    # MODEL
    
    # Sets
    m.commodity = pyomo.Set(initialize=commodity.index,
                            doc='Commodities')
    m.co_demand = pyomo.Set(within=m.commodity, 
                            initialize=co_demand,
                            doc='Commodities that have demand in edges')
    m.process = pyomo.Set(initialize=process.index,
                          doc='')
    m.process_input_tuples = pyomo.Set(within=m.process*m.commodity, 
                                       initialize=m.r_in.index,
                                       doc='Commodities consumed by processes')
    m.process_output_tuples = pyomo.Set(within=m.process*m.commodity, 
                                        initialize=m.r_out.index,
                                        doc='Commodities emitted by processes')
    m.hub = pyomo.Set(within=m.process,
                      initialize=hub.index,
                      doc='Hub processes')
    m.time = pyomo.Set(initialize=time.index, doc='Timesteps')
    #m.storage = pyomo.Set(initialize=storage.index.levels[
    #                                 storage.index.names.index('Storage')])
    m.vertex = pyomo.Set(initialize=vertex.index)
    m.edge = pyomo.Set(within=m.vertex*m.vertex, initialize=edge.index)
    m.arc = pyomo.Set(within=m.vertex*m.vertex, initialize=arcs)
    
    m.cost_type = pyomo.Set(initialize=['Inv', 'Fix', 'Var'])
    
    # Parameters
    # no or few will be needed
    
    # Variables
    
    # edges and arcs
    m.Sigma = pyomo.Var(m.edge, m.commodity, m.time, 
                        within=pyomo.NonNegativeReals, 
                        doc='supply (kW) of commodity in edge at time')
    m.Pin = pyomo.Var(m.arc, m.commodity, m.time, 
                      within=pyomo.NonNegativeReals,
                      doc='power flow (kW) of commodity into arc at time')
    m.Pot = pyomo.Var(m.arc, m.commodity, m.time, 
                      within=pyomo.NonNegativeReals,
                      doc='power flow (kW) of commodity out of arc at time')
    m.Psi = pyomo.Var(m.arc, m.commodity, m.time, 
                      within=pyomo.Binary,
                      doc='1 if (directed!) arc is used at time, 0 else')
    m.Pmax = pyomo.Var(m.edge, m.commodity, 
                       within=pyomo.NonNegativeReals,
                       doc='power flow capacity (kW) for commodity in edge')
    m.Xi = pyomo.Var(m.edge, m.commodity, 
                     within=pyomo.Binary,
                     doc='1 if (undirected!) edge is used for commodity at all, 0 else')
    
    # vertices
    m.Rho = pyomo.Var(m.vertex, m.commodity, m.time, 
                      within=pyomo.NonNegativeReals,
                      doc='source stream (kW) of commodity from vertex')

    # hubs
    m.Kappa_hub = pyomo.Var(m.edge, m.hub, 
                            within=pyomo.NonNegativeReals,
                            doc='capacity (kW) of hub process in an edge')
    m.Epsilon_hub = pyomo.Var(m.edge, m.hub, m.time, 
                              within=pyomo.NonNegativeReals,
                              doc='acitvity (kW) of hub process in edge at time')

    # processes
    m.Kappa_process = pyomo.Var(m.vertex, m.process, 
                                within=pyomo.NonNegativeReals,
                                doc='capacity (kW) of process in vertex')
    m.Phi = pyomo.Var(m.vertex, m.process, 
                      within=pyomo.Binary,
                      doc='1 if process in vertex has Kappa_process > 0, 0 else')
    m.Tau = pyomo.Var(m.vertex, m.process, m.time, 
                      within=pyomo.NonNegativeReals,
                      doc='power flow (kW) through process')
    m.Epsilon_in = pyomo.Var(m.vertex, m.process, m.commodity, m.time, 
                             within=pyomo.NonNegativeReals,
                             doc='power flow (kW) of commodity into process')
    m.Epsilon_out = pyomo.Var(m.vertex, m.process, m.commodity, m.time, 
                              within=pyomo.NonNegativeReals,
                              doc='power flow (kW) of commodity out of process')
    
    # costs
    m.costs = pyomo.Var(m.cost_type, 
                        within=pyomo.NonNegativeReals,
                        doc='costs (EUR) by cost type')
    
    # Constraints
    
    # edges/arcs
    def peak_satisfaction_rule(m, i, j, co, t):
        provided_power = hub_balance(m, i, j, co, t) + m.Sigma[i,j,co,t]
        return provided_power > m.peak.loc[i,j][co] * time.loc[t]['scale']
    
    def edge_equation_rule(m, i, j, co, t):
        length = edge.loc[i, j]['geometry'].length
        
        flow_in = ( 1 - length * commodity.loc[co]['loss-var']) * \
                  ( m.Pin[i,j,co,t] + m.Pin[j,i,co,t] )
        flow_out =  m.Pot[i,j,co,t] + m.Pot[j,i,co,t]
        fixed_losses = ( m.Psi[i,j,co,t] + m.Psi[j,i,co,t] ) * \
                       length * commodity.loc[co]['loss-fix']
        
        return m.Sigma[i,j,co,t] <= flow_in - flow_out - fixed_losses
        
    def arc_flow_by_capacity_rule(m, i, j, co, t):
        (v1, v2) = find_matching_edge(m, i, j)        
        return m.Pin[i,j,co,t] <= m.Pmax[v1, v2, co]
        
    def arc_unidirectionality_rule(m, i, j, co, t):
        return m.Psi[i,j,co,t] + m.Psi[j,i,co,t] <= 1
        
    def edge_capacity_rule(m, i, j, co):
        return m.Pmax[i,j,co] <= m.Xi[i,j,co] * commodity.loc[co]['cap-max']
        
    # hubs
    def hub_output_by_capacity_rule(m, i, j, h, t):
        return m.Epsilon_hub[i,j,h,t] <= m.Kappa_hub[i,j,h]
        
    def hub_capacity_rule(m, i, j, h):
        return m.Kappa_hub[i,j,h] <= hub.loc[h]['cap-max']
        
    # vertex
    def vertex_equation_rule(m, v, co, t):
        flow_required = - flow_balance(m, v, co, t)
        process_required = - process_balance(m, v, co, t)
        return m.Rho[v,co,t] >= flow_required + process_required # + storage_required
    
    def process_throughput_rule(m, v, p, t):
        return m.Tau[v,p,t] == throughput_sum(m, v, p, t)
        
    def process_throughput_by_capacity_rule(m, v, p, t):
        return m.Tau[v,p,t] <= m.Kappa_process[v, p]
    
    def process_capacity_min_rule(m, v, p):
        return m.Kappa_process[v, p] >= m.Phi[v, p] * process.loc[p]['cap-min']
        
    def process_capacity_max_rule(m, v, p):
        return m.Kappa_process[v, p] <= m.Phi[v, p] * process.loc[p]['cap-max']
        
    def process_input_rule(m, v, p, co, t):
        return m.Epsilon_in[v, p, co, t] == m.Tau[v, p, t] * m.r_in.loc[p, co]
        
    def process_output_rule(m, v, p, co, t):
        return m.Epsilon_out[v, p, co, t] == m.Tau[v, p, t] * m.r_out.loc[p, co]
    
    # Objective
    
    def def_costs_rule(m, cost_type):
        if cost_type == 'Inv':
            return m.costs['Inv'] == \
                sum(m.Kappa_hub[i,j,h] * hub.loc[h]['cost-inv-var'] 
                    for (i,j) in m.edge for h in m.hub) + \
                sum(m.Kappa_process[v,p] * process.loc[p]['cost-inv-var'] + 
                    m.Phi[v,p] * process.loc[p]['cost-inv-fix']
                    for v in m.vertex for p in m.process) + \
                sum(m.Pmax[i,j,co] * commodity.loc[co]['cost-inv-var'] + 
                    m.Xi[i,j,co] * commodity.loc[co]['cost-inv-fix']
                    for (i,j) in m.edge for co in m.co_demand)
                    
        elif cost_type == 'Fix':
            return m.costs['Fix'] == m.costs['Inv'] * 0.05
            
        elif cost_type == 'Var':
            return m.costs['Var'] == \
                sum(m.Epsilon_hub[i,j,h,t] * hub.loc[h]['cost-var'] * time.loc[t]['weight']
                    for (i,j) in m.edge for h in m.hub for t in m.time) + \
                sum(m.Tau[v,p,t] * process.loc[p]['cost-var'] * time.loc[t]['weight']
                    for v in m.vertex for p in m.process for t in m.time) + \
                sum(m.Rho[v,co,t] * commodity.loc[co]['cost-var'] * time.loc[t]['weight']
                    for v in m.vertex for co in m.co_demand for t in m.time)
            
        else:
            raise NotImplementedError("Unknown cost type!")
    
    def obj_rule(m):
        return pyomo.summation(m.costs)
    
    # Equation declarations
    
    # edges/arcs
    m.peak_satisfaction = pyomo.Constraint(m.edge, m.co_demand, m.time,
        doc='peak must be satisfied by Sigma and hub process output')
    m.edge_equation = pyomo.Constraint(m.edge, m.co_demand, m.time,
        doc='Sigma is provided by arc flow difference Pin-Pot in either direction')
    m.arc_flow_by_capacity = pyomo.Constraint(m.arc, m.co_demand, m.time,
        doc='Pin <= Pmax')
    m.arc_unidirectionality = pyomo.Constraint(m.arc, m.co_demand, m.time,
        doc='Psi[i,j,t] + Psi[j,i,t] <= 1')
    m.edge_capacity = pyomo.Constraint(m.edge, m.co_demand, 
        doc='Pmax <= Cmax * Xi')

    # hubs
    m.hub_output_by_capacity = pyomo.Constraint(m.edge, m.hub, m.time,
        doc='Epsilon_hub <= Kappa_hub')
    m.hub_capacity = pyomo.Constraint(m.edge, m.hub,
        doc='Kappa_hub <= Cmax')
    
    # vertex
    m.vertex_equation = pyomo.Constraint(m.vertex, m.commodity, m.time, 
        doc='Rho >= Process balance + Arc flow balance')
    
    # process
    m.process_throughput = pyomo.Constraint(m.vertex, m.process, m.time,
        doc='process throughput (Tau) is equal to sum of process inputs flows')
    m.process_throughput_by_capacity = pyomo.Constraint(m.vertex, m.process, m.time,
        doc='Tau <= Kappa_process')
    m.process_capacity_min = pyomo.Constraint(m.vertex, m.process,
        doc='Kappa_process >= Cmin * Phi')
    m.process_capacity_max = pyomo.Constraint(m.vertex, m.process,
        doc='Kappa_process <= Cmax * Phi')
    m.process_input = pyomo.Constraint(m.vertex, m.process_input_tuples, m.time,
        doc='Epsilon_in = Tau * r_in')
    m.process_output = pyomo.Constraint(m.vertex, m.process_output_tuples, m.time,
        doc='Epsilon_out = Tau * r_out')

    # costs
    m.def_costs = pyomo.Constraint(m.cost_type, doc='Costs = sum of activities')
    m.obj = pyomo.Objective(sense=pyomo.minimize, doc='Sum costs by cost type')
    
    return m




def hub_balance(m, i, j, co, t):
    """ Calculate commodity balance in an edge {i,j} from/to hubs. """
    balance = 0
    for h in m.hub:
        if co in m.r_in.loc[h].index:
            balance -= m.Epsilon_hub[i,j,h,t] * m.r_in.loc[h,co]
        if co in m.r_out.loc[h].index:
            balance += m.Epsilon_hub[i,j,h,t] * m.r_out.loc[h,co]
    return balance
    
def flow_balance(m, v, co, t):
    """ Calculate commodity flow balance in a vertex from/to arcs. """
    balance = 0
    for w in m.neighbours[v]:        
        balance += m.Pot[w,v,co,t]
        balance -= m.Pin[v,w,co,t]
    return balance
        
def process_balance(m, v, co, t):
    """ Calculate commodity balance in a vertex from/to processes. """
    balance = 0
    for p in m.process:
        if co in m.r_in.loc[p].index:
            balance -= m.Epsilon_in[v,p,co,t]
        if co in m.r_out.loc[p].index:
            balance += m.Epsilon_out[v,p,co,t]
    return balance

def throughput_sum(m, v, p, t):
    """ Calculate process throughput as the sum of inputs. """
    throughput = 0
    for (pro, co) in m.process_input_tuples:
        if pro == p:
            throughput += m.Epsilon_in[v,p,co,t] * m.r_in.loc[p,co]
    return throughput

def find_matching_edge(m, i, j):
    """ Return corresponding edge for a given arc. """
    if (i,j) in m.edge:
        return (i,j)
    else:
        return (j,i)


