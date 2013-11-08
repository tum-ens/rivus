""" CAPMIN: optimization model for distributed urban energy systems

CAPMIN optimizes topology and size of urban energy networks, energy conversion.

"""
import coopr.pyomo as pyomo
import itertools
import pandas as pd
import pyomotools
import pdb

def create_model(spreadsheet, vertex, edge):
    """Return a CAPMIN model instance from input file and spatial input. 
    
    Args:
        spreadsheet: Excel spreadsheet with entity sheets Commodity, Process,
            Process-Commodity, Time and Area-Demand
        vertex: DataFrame with vertex IDs as column 'Vertex' and other columns 
            named like source commodities (e.g. 'Gas', 'Elec', 'Pellets'), 
            containing source vertex capacities (in kW)
        edge: DataFrame woth vertex IDs in columns 'Vertex1' and 'Vertex2' and
            other columns named like area types (in spreadsheet/Area-Demand),
            containing total areas (square metres) to be supplied
            
    Returns:
        Pyomo ConcreteModel object

    """ 
    m = pyomo.ConcreteModel()
    m.name = 'CAPMIN'
    
    # DataFrames
    dfs = pyomotools.read_xls(spreadsheet)
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
    hub = process[has_cost_inv_fix_0 & has_cap_min_0 & has_one_input & has_r_in_1]   
    
    # derive peak and demand of edges
    # by selecting edge columns that are named like area types (res, com, ind)
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
    
    # find transportable commodities, i.e. those with a positive maximum
    # transport capacity. Commodities with 0, #NV or empty values are thus 
    # excluded
    is_transportable = commodity['cap-max'] > 0
    co_transportable = commodity[is_transportable].index
    
    # find possible source commodities, i.e. those for which there are
    # capacities within table `vertex`
    co_source = commodity.index.intersection(vertex.columns)
    
    # find commodities for which there exists no identically named attribute in
    # table 'vertex' and set it to zero to disable them as source-commodities.
    no_source_commodities = commodity.index.diff(vertex.columns)
    for co in no_source_commodities:
        vertex[co] = 0

    # MODEL
    
    # Sets
    
    # commodity
    m.commodity = pyomo.Set(
        initialize=commodity.index,
        doc='Commodities')
    m.co_demand = pyomo.Set(
        within=m.commodity, 
        initialize=co_demand,
        doc='Commodities that have demand in edges')
    m.co_source = pyomo.Set(
        within=m.commodity,
        initialize=co_source,
        doc='Commodities that may have a source at some vertex/vertices')   
    m.co_transportable = pyomo.Set(
        within=m.commodity,
        initialize=co_transportable,
        doc='Commodities that may be transported through edges')
    
    # process
    m.process = pyomo.Set(
        initialize=process.index,
        doc='Processes, converting commodities in vertices')
    m.process_input_tuples = pyomo.Set(
        within=m.process*m.commodity, 
        initialize=m.r_in.index,
        doc='Commodities consumed by processes')
    m.process_output_tuples = pyomo.Set(
        within=m.process*m.commodity, 
        initialize=m.r_out.index,
        doc='Commodities emitted by processes')
    
    # hub
    m.hub = pyomo.Set(
        within=m.process,
        initialize=hub.index,
        doc='Hub processes, converting commodities in edges')
    
    # time
    m.time = pyomo.Set(
        initialize=time.index, 
        doc='Timesteps')
    
    # storage
    #m.storage = pyomo.Set(
    #   initialize=storage.index.levels[storage.index.names.index('Storage')],
    #   doc='')
    
    # graph
    m.vertex = pyomo.Set(
        initialize=vertex.index,
        doc='Connection points between edges, for source and processes')
    m.edge = pyomo.Set(
        within=m.vertex*m.vertex, 
        initialize=edge.index,
        doc='Undirected street segments, for demand and hubs')
    m.arc = pyomo.Set(
        within=m.vertex*m.vertex, 
        initialize=arcs,
        doc='Directed street segments, for power flows')
    
    # costs
    m.cost_type = pyomo.Set(
        initialize=['Inv', 'Fix', 'Var'],
        doc='')
    
    # Parameters
    # no or few will be needed
    
    # Variables
    
    # edges and arcs
    m.Sigma = pyomo.Var(
        m.edge, m.commodity, m.time, 
        within=pyomo.NonNegativeReals, 
        doc='supply (kW) of commodity in edge at time')
    m.Pin = pyomo.Var(
        m.arc, m.commodity, m.time, 
        within=pyomo.NonNegativeReals,
        doc='power flow (kW) of commodity into arc at time')
    m.Pot = pyomo.Var(
        m.arc, m.commodity, m.time, 
        within=pyomo.NonNegativeReals,
        doc='power flow (kW) of commodity out of arc at time')
    m.Psi = pyomo.Var(
        m.arc, m.commodity, m.time, 
        within=pyomo.Binary,
        doc='1 if (directed!) arc is used at time, 0 else')
    m.Pmax = pyomo.Var(
        m.edge, m.commodity, 
        within=pyomo.NonNegativeReals,
        doc='power flow capacity (kW) for commodity in edge')
    m.Xi = pyomo.Var(
        m.edge, m.commodity, 
        within=pyomo.Binary,
        doc='1 if (undirected!) edge is used for commodity at all, 0 else')
    
    # vertices
    m.Rho = pyomo.Var(
        m.vertex, m.co_source, m.time, 
        within=pyomo.NonNegativeReals,
        doc='source stream (kW) of commodity from vertex')

    # hubs
    m.Kappa_hub = pyomo.Var(
        m.edge, m.hub, 
        within=pyomo.NonNegativeReals,
        doc='capacity (kW) of hub process in an edge')
    m.Epsilon_hub = pyomo.Var(
        m.edge, m.hub, m.time, 
        within=pyomo.NonNegativeReals,
        doc='acitvity (kW) of hub process in edge at time')

    # processes
    m.Kappa_process = pyomo.Var(
        m.vertex, m.process, 
        within=pyomo.NonNegativeReals,
        doc='capacity (kW) of process in vertex')
    m.Phi = pyomo.Var(
        m.vertex, m.process, 
        within=pyomo.Binary,
        doc='1 if process in vertex has Kappa_process > 0, 0 else')
    m.Tau = pyomo.Var(
        m.vertex, m.process, m.time, 
        within=pyomo.NonNegativeReals,
        doc='power flow (kW) through process')
    m.Epsilon_in = pyomo.Var(
        m.vertex, m.process, m.commodity, m.time, 
        within=pyomo.NonNegativeReals,
        doc='power flow (kW) of commodity into process')
    m.Epsilon_out = pyomo.Var(
        m.vertex, m.process, m.commodity, m.time, 
        within=pyomo.NonNegativeReals,
        doc='power flow (kW) of commodity out of process')
    
    # costs
    m.costs = pyomo.Var(
        m.cost_type, 
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
    
    def arc_flow_unidirectionality_rule(m, i, j, co, t):
        return m.Pin[i,j,co,t] <= commodity.loc[co]['cap-max'] * m.Psi[i,j,co,t]

    def arc_unidirectionality_rule(m, i, j, co, t):
        return m.Psi[i,j,co,t] + m.Psi[j,i,co,t] <= 1
        
    def edge_capacity_rule(m, i, j, co):
        return m.Pmax[i,j,co] <= m.Xi[i,j,co] * commodity.loc[co]['cap-max']
        
    # hubs        
    def hub_supply_rule(m, i, j, co, t):
        hub_input_power = - hub_balance(m, i, j, co, t)
        return hub_input_power <= m.Sigma[i,j,co,t]
    
    def hub_output_by_capacity_rule(m, i, j, h, t):
        return m.Epsilon_hub[i,j,h,t] <= m.Kappa_hub[i,j,h]
        
    def hub_capacity_rule(m, i, j, h):
        return m.Kappa_hub[i,j,h] <= hub.loc[h]['cap-max']
        
    # vertex
    def vertex_equation_rule(m, v, co, t):
        flow_required = - flow_balance(m, v, co, t)
        process_required = - process_balance(m, v, co, t)
        if co in m.co_source:
            return m.Rho[v,co,t] >= flow_required + process_required # + storage_required
        else:
            return 0 >= flow_required + process_required
    
    def source_vertices_rule(m, v, co, t):
        return m.Rho[v,co,t]<= vertex.loc[v][co]
    
    # process
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
                    for v in m.vertex for co in m.co_source for t in m.time)
            
        else:
            raise NotImplementedError("Unknown cost type!")
    
    def obj_rule(m):
        return pyomo.summation(m.costs)
    
    # Equation declarations
    
    # edges/arcs
    m.peak_satisfaction = pyomo.Constraint(
        m.edge, m.co_demand, m.time,
        doc='peak must be satisfied by Sigma and hub process output')
    m.edge_equation = pyomo.Constraint(
        m.edge, m.co_transportable, m.time,
        doc='Sigma is provided by arc flow difference Pin-Pot in either direction')
    m.arc_flow_by_capacity = pyomo.Constraint(
        m.arc, m.co_transportable, m.time,
        doc='Pin <= Pmax')
    m.arc_flow_unidirectionality = pyomo.Constraint(
        m.arc, m.co_transportable, m.time,
        doc='Pin <= Cmax * Psi')
    m.arc_unidirectionality = pyomo.Constraint(
        m.arc, m.co_transportable, m.time,
        doc='Psi[i,j,t] + Psi[j,i,t] <= 1')
    m.edge_capacity = pyomo.Constraint(
        m.edge, m.co_transportable, 
        doc='Pmax <= Cmax * Xi')

    # hubs
    m.hub_supply = pyomo.Constraint(
        m.edge, m.commodity, m.time,
        doc='Hub inputs <= Sigma')
    
    m.hub_output_by_capacity = pyomo.Constraint(
        m.edge, m.hub, m.time,
        doc='Epsilon_hub <= Kappa_hub')
    m.hub_capacity = pyomo.Constraint(
        m.edge, m.hub,
        doc='Kappa_hub <= Cmax')
    
    # vertex
    m.vertex_equation = pyomo.Constraint(
        m.vertex, m.commodity, m.time, 
        doc='Rho >= Process balance + Arc flow balance')
    m.source_vertices = pyomo.Constraint(
        m.vertex, m.co_source, m.time,
        doc='Rho <= Cmax')
    
    # process
    m.process_throughput = pyomo.Constraint(
        m.vertex, m.process, m.time,
        doc='process throughput (Tau) is equal to sum of process inputs flows')
    m.process_throughput_by_capacity = pyomo.Constraint(
        m.vertex, m.process, m.time,
        doc='Tau <= Kappa_process')
    m.process_capacity_min = pyomo.Constraint(
        m.vertex, m.process,
        doc='Kappa_process >= Cmin * Phi')
    m.process_capacity_max = pyomo.Constraint(
        m.vertex, m.process,
        doc='Kappa_process <= Cmax * Phi')
    m.process_input = pyomo.Constraint(
        m.vertex, m.process_input_tuples, m.time,
        doc='Epsilon_in = Tau * r_in')
    m.process_output = pyomo.Constraint(
        m.vertex, m.process_output_tuples, m.time,
        doc='Epsilon_out = Tau * r_out')

    # costs
    m.def_costs = pyomo.Constraint(
        m.cost_type, 
        doc='Costs = sum of activities')
    m.obj = pyomo.Objective(
        sense=pyomo.minimize, 
        doc='Sum costs by cost type')
    
    return m


# Helper functions for model

def hub_balance(m, i, j, co, t):
    """ Calculate commodity balance in an edge {i,j} from/to hubs. """
    balance = 0
    for h in m.hub:
        if co in m.r_in.loc[h].index:
            balance -= m.Epsilon_hub[i,j,h,t] * m.r_in.loc[h,co] # m.r_in = 1 by definition
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


