"""rivus: optimization model for distributed urban energy systems

rivus optimizes topology and size of urban energy networks, energy conversion.

"""
import coopr.pyomo as pyomo
import itertools
import pandas as pd
import warnings

COLORS = {
    'base': (.667, .667, .667),
    'building': (0.95686274509803926, 0.95686274509803926, 0.7803921568627451),
    'decoration': (.5, .5, .5),
    'Heat': (1, 0, 0),
    'Cool': (0, 0, 1),
    'Elec': (1, .667, 0),
    'Demand': (0, 1, 0),
    'Gas': (.5, .25, 0),
}

def read_excel(filename):
    """Read Excel input file and prepare rivus input data dict.
    
    Reads an Excel spreadsheet that adheres to the structure shown in the
    example dataset data/mnl/mnl.xlsx. Must contain
    
    Args:
        filename: filename to an Excel spreadsheet.
    
    Returns:
        a dict of 6 DataFrames, one for each sheet
    """
    with pd.ExcelFile(filename) as xls:
        commodity = xls.parse('Commodity', index_col=['Commodity'])
        process = xls.parse('Process', index_col=['Process'])
        time = xls.parse('Time', index_col=['Time'])
        area_demand = xls.parse('Area-Demand', index_col=['Area', 'Commodity'])
        process_commodity = xls.parse(
            'Process-Commodity',
            index_col=['Process', 'Commodity', 'Direction'])
        
    data = {
        'commodity': commodity,
        'process': process,
        'process_commodity': process_commodity,
        'time': time,
        'area_demand': area_demand}
    
    # sort nested indexes to make direct assignments work, cf
    # http://pandas.pydata.org/pandas-docs/stable/indexing.html#the-need-for-sortedness-with-multiindex
    for key in data:
        if isinstance(data[key].index, pd.core.index.MultiIndex):
            data[key].sortlevel(inplace=True)
    return data    
    

def create_model(data, vertex, edge):
    """Return a rivus model instance from input file and spatial input. 
    
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
    m.name = 'rivus'
    
    # DataFrames
    commodity = data['commodity']    
    process = data['process']
    process_commodity = data['process_commodity']
    #storage = dfs['Storage']
    time = data['time']
    area_demand = data['area_demand']   
    
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
    m.peak.sortlevel(inplace=True)
    
    # store geographic DataFrames vertex & edge for later use
    m._vertex = vertex.copy()
    m._edge = edge.copy()
    
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
    # none needed, DataFrames work directly in equation definitions
    
    # Variables
    
    # edges and arcs
    m.Sigma = pyomo.Var(
        m.edge, m.commodity, m.time, 
        within=pyomo.NonNegativeReals, 
        doc='supply (kW) of commodity in edge at time')
    m.Pin = pyomo.Var(
        m.arc, m.co_transportable, m.time, 
        within=pyomo.NonNegativeReals,
        doc='power flow (kW) of commodity into arc at time')
    m.Pot = pyomo.Var(
        m.arc, m.co_transportable, m.time, 
        within=pyomo.NonNegativeReals,
        doc='power flow (kW) of commodity out of arc at time')
    m.Psi = pyomo.Var(
        m.arc, m.co_transportable, m.time, 
        within=pyomo.Binary,
        doc='1 if (directed!) arc is used at time, 0 else')
    m.Pmax = pyomo.Var(
        m.edge, m.co_transportable, 
        within=pyomo.NonNegativeReals,
        doc='power flow capacity (kW) for commodity in edge')
    m.Xi = pyomo.Var(
        m.edge, m.co_transportable, 
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
        return provided_power >= m.peak.loc[i,j][co] * time.loc[t]['scale']
    
    def edge_equation_rule(m, i, j, co, t):
        if co in m.co_transportable:
            length = edge.loc[i, j]['geometry'].length
            
            flow_in = ( 1 - length * commodity.loc[co]['loss-var']) * \
                      ( m.Pin[i,j,co,t] + m.Pin[j,i,co,t] )
            flow_out =  m.Pot[i,j,co,t] + m.Pot[j,i,co,t]
            fixed_losses = ( m.Psi[i,j,co,t] + m.Psi[j,i,co,t] ) * \
                           length * commodity.loc[co]['loss-fix']
            
            return m.Sigma[i,j,co,t] <= flow_in - flow_out - fixed_losses
        else:
            return m.Sigma[i,j,co,t] <= 0
        
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
        if co in m.co_transportable:
            flow_required = - flow_balance(m, v, co, t)
        else:
            flow_required = 0
        process_required = - process_balance(m, v, co, t)
        if co in m.co_source:
            return m.Rho[v,co,t] >= flow_required + process_required
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
                    for (i,j) in m.edge for co in m.co_transportable)
                    
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
        m.edge, m.commodity, m.time,
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


# Technical helper functions for data retrieval

def get_entity(instance, name):
    """ Return a DataFrame for an entity in model instance.

    Args:
        instance: a Pyomo ConcreteModel instance
        name: name of a Set, Param, Var, Constraint or Objective

    Returns:
        a single-columned Pandas DataFrame with domain as index
    """

    # retrieve entity, its type and its onset names
    entity = instance.__getattribute__(name)
    labels = get_onset_names(entity)

    # extract values
    if isinstance(entity, pyomo.Set):
        # Pyomo sets don't have values, only elements
        results = pd.DataFrame([(v, 1) for v in entity.value])

        # for unconstrained sets, the column label is identical to their index
        # hence, make index equal to entity name and append underscore to name
        # (=the later column title) to preserve identical index names for both
        # unconstrained supersets
        if not labels:
            labels = [name]
            name = name+'_'

    elif isinstance(entity, pyomo.Param):
        if entity.dim() > 1:
            results = pd.DataFrame([v[0]+(v[1],) for v in entity.iteritems()])
        else:
            results = pd.DataFrame(entity.iteritems())
    else:
        # create DataFrame
        if entity.dim() > 1:
            # concatenate index tuples with value if entity has
            # multidimensional indices v[0]
            results = pd.DataFrame(
                [v[0]+(v[1].value,) for v in entity.iteritems()])
        else:
            # otherwise, create tuple from scalar index v[0]
            results = pd.DataFrame(
                [(v[0], v[1].value) for v in entity.iteritems()])

    # check for duplicate onset names and append one to several "_" to make
    # them unique, e.g. ['sit', 'sit', 'com'] becomes ['sit', 'sit_', 'com']
    for k, label in enumerate(labels):
        if label in labels[:k]:
            labels[k] = labels[k] + "_"

    # name columns according to labels + entity name
    results.columns = labels + [name]
    results.set_index(labels, inplace=True)
    results = results[name]
    return results


def get_entities(instance, names):
    """ Return one DataFrame with entities in columns and a common index.

    Works only on entities that share a common domain (set or set_tuple), which
    is used as index of the returned DataFrame.

    Args:
        instance: a Pyomo ConcreteModel instance
        names: list of entity names (as returned by list_entities)

    Returns:
        a Pandas DataFrame with entities as columns and domains as index
    """

    df = pd.DataFrame()
    for name in names:
        other = get_entity(instance, name)
        
        if isinstance(other, pd.Series):
            other = other.to_frame()

        if df.empty:
            df = other
        else:
            index_names_before = df.index.names

            df = df.join(other, how='outer')

            if index_names_before != df.index.names:
                df.index.names = index_names_before

    return df


def list_entities(instance, entity_type):
    """ Return list of sets, params, variables, constraints or objectives

    Args:
        instance: a Pyomo ConcreteModel object
        entity_type: "set", "par", "var", "con" or "obj"

    Returns:
        DataFrame of entities

    Example:
        >>> data = read_excel('data-example.xlsx')
        >>> model = create_model(data, range(1,25))
        >>> list_entities(model, 'obj')  #doctest: +NORMALIZE_WHITESPACE
                                         Description Domain
        Name
        obj   minimize(cost = sum of all cost types)     []
        [1 rows x 2 columns]

    """

    # helper function to discern entities by type
    def filter_by_type(entity, entity_type):
        if entity_type == 'set':
            return isinstance(entity, pyomo.Set) and not entity.virtual
        elif entity_type == 'par':
            return isinstance(entity, pyomo.Param)
        elif entity_type == 'var':
            return isinstance(entity, pyomo.Var)
        elif entity_type == 'con':
            return isinstance(entity, pyomo.Constraint)
        elif entity_type == 'obj':
            return isinstance(entity, pyomo.Objective)
        else:
            raise ValueError("Unknown entity_type '{}'".format(entity_type))

    # iterate through all model components and keep only 
    iter_entities = instance.__dict__.iteritems()
    entities = sorted(
        (name, entity.doc, get_onset_names(entity))
        for (name, entity) in iter_entities
        if filter_by_type(entity, entity_type))

    # if something was found, wrap tuples in DataFrame, otherwise return empty
    if entities:
        entities = pd.DataFrame(entities,
                                columns=['Name', 'Description', 'Domain'])
        entities.set_index('Name', inplace=True)
    else:
        entities = pd.DataFrame()
    return entities


def get_onset_names(entity):
    """
        Example:
            >>> data = read_excel('data-example.xlsx')
            >>> model = create_model(data, range(1,25))
            >>> get_onset_names(model.e_co_stock)
            ['t', 'sit', 'com', 'com_type']
    """
    # get column titles for entities from domain set names
    labels = []

    if isinstance(entity, pyomo.Set):
        if entity.dimen > 1:
            # N-dimensional set tuples, possibly with nested set tuples within
            if entity.domain:
                domains = entity.domain.set_tuple
            else:
                domains = entity.set_tuple

            for domain_set in domains:
                labels.extend(get_onset_names(domain_set))

        elif entity.dimen == 1:
            if entity.domain:
                # 1D subset; add domain name
                labels.append(entity.domain.name)
            else:
                # unrestricted set; add entity name
                labels.append(entity.name)
        else:
            # no domain, so no labels needed
            pass

    elif isinstance(entity, (pyomo.Param, pyomo.Var, pyomo.Constraint,
                    pyomo.Objective)):
        if entity.dim() > 0 and entity._index:
            labels = get_onset_names(entity._index)
        else:
            # zero dimensions, so no onset labels
            pass

    else:
        raise ValueError("Unknown entity type!")

    return labels


def get_constants(prob):
    """Retrieve time-independent variables/quantities.

    Usage:
        costs, Pmax, Kappa_hub, Kappa_process = get_constants(prob)

    Args:
        prob: a rivus model instance

    Returns:
        (costs, Pmax, Kappa_hub) tuple
    """
    costs = get_entity(prob, 'costs')
    Pmax = get_entity(prob, 'Pmax')
    Kappa_hub = get_entity(prob, 'Kappa_hub')
    Kappa_process = get_entity(prob, 'Kappa_process')
    
    # nicer index names
    Pmax.index.names = ['Vertex1', 'Vertex2', 'commodity']
    Kappa_hub.index.names = ['Vertex1', 'Vertex2', 'process']
    
    # drop all-zero rows 
    Pmax = Pmax[Pmax > 0].unstack().fillna(0)
    Kappa_hub = Kappa_hub[Kappa_hub > 0].unstack().fillna(0)
    Kappa_process = Kappa_process[Kappa_process > 0].unstack().fillna(0)
    
    # round to integers
    if Pmax.empty:
        Pmax = pd.DataFrame([])
    else:
        Pmax = Pmax.applymap(round)
    if Kappa_hub.empty:
        Kappa_hub = pd.DataFrame([])
    else:
        Kappa_hub = Kappa_hub.applymap(round)
    if Kappa_process.empty:
        Kappa_process = pd.DataFrame([])
    else:
        Kappa_process = Kappa_process.applymap(round)
    costs = costs.apply(round)
    
    return costs, Pmax, Kappa_hub, Kappa_process
    
def get_timeseries(prob):
    """Retrieve time-dependent variables/quantities.
    
    Usage:
        source, flows, hubs, proc_io, proc_tau = get_timeseries(prob)

    Args:
        prob: a rivus model instance

    Returns:
        (source, flows, hubs, proc_io, proc_tau) tuple
    """

    source = get_entity(prob, 'Rho')
    flows = get_entities(prob, ['Pin', 'Pot', 'Psi', 'Sigma'])
    hubs = get_entity(prob, 'Epsilon_hub')
    proc_io = get_entities(prob, ['Epsilon_in', 'Epsilon_out'])
    proc_tau = get_entity(prob, 'Tau')

    # fill NaN's
    flows.fillna(0, inplace=True)
    proc_io.fillna(0, inplace=True)

    # drop all-zero rows
    source = source[source > 0].unstack()
    flows = flows[flows.sum(axis=1) > 0].applymap(round)
    
    hubs = hubs[hubs > 0].unstack().fillna(0)
    if hubs.empty:
        hubs = pd.DataFrame([])
    else:
        hubs = hubs.applymap(round)
    
    proc_io = proc_io[proc_io.sum(axis=1) > 0]
    if not proc_io.empty:
        proc_io = proc_io.applymap(round)
    
    proc_tau = proc_tau[proc_tau.apply(round) > 0]
    if not proc_tau.empty:
        proc_tau = proc_tau.unstack().applymap(round)

    return source, flows, hubs, proc_io, proc_tau


def plot(prob, commodity, plot_demand=False, mapscale=False, tick_labels=True):
    """Plot a map of supply, conversion, transport and consumption.
    
    For given commodity, plot a map of all locations where the commodity is
    introduced (Rho), transported (Pin/Pot/Pmax), converted (Epsilon_*) and
    consumed (Sigma, peak).  
    """
    import math
    import matplotlib as mpl
    import matplotlib.pyplot as plt
    import matplotlib.patheffects as pe
    from mpl_toolkits.basemap import Basemap
    import numpy as np
    import pandashp as pdshp
    
    # set up Basemap for extent
    bbox = pdshp.total_bounds(prob._vertex)
    bbox = [bbox[1], bbox[0], bbox[3], bbox[2]]
    
    # set projection center to map center
    central_parallel = (bbox[0] + bbox[2]) / 2
    central_meridian = (bbox[1] + bbox[3]) / 2
        
    # increase map extent by 5% in each direction
    height = bbox[2] - bbox[0]
    width = bbox[3] - bbox[1] 
    bbox[0] -= 0.05 * height
    bbox[1] -= 0.05 * width
    bbox[2] += 0.05 * height
    bbox[3] += 0.05 * width
    
    # default settings for annotation labels
    annotate_defaults = dict(
        textcoords='offset points', ha='center', va='center', xytext=(0, 0),
        path_effects=[pe.withStroke(linewidth=2, foreground="w")])
    
    # create new figure with basemap in Transverse Mercator projection
    # centered on map location
    fig = plt.figure()
    map = Basemap(
        projection='tmerc', resolution=None, 
        llcrnrlat=bbox[0], llcrnrlon=bbox[1], 
        urcrnrlat=bbox[2], urcrnrlon=bbox[3], 
        lat_0=central_parallel, lon_0=central_meridian)

    # basemap: plot street network
    for k, row in prob._edge.iterrows():
        line = row['geometry']
        lon, lat = zip(*line.coords)
        # linewidth
        line_width = 0.1
        # plot
        map.plot(lon, lat, latlon=True, 
                 color=COLORS['base'], linewidth=line_width, 
                 solid_capstyle='round', solid_joinstyle='round')

    if not plot_demand:
        # default commodity plot with Pmax, Kappa_hub, Kappa_process, sources
        
        # read data from solution
        _, Pmax, Kappa_hub, Kappa_process = get_constants(prob)
        source = get_timeseries(prob)[0]
        
        # Pmax: pipe capacities
        Pmax = Pmax.join(prob._edge.geometry)
        for k, row in Pmax.iterrows():
            # coordinates
            line = row['geometry']
            lon, lat = zip(*line.coords)
            # linewidth
            line_width = math.sqrt(row[commodity]) * 0.05
            # plot
            map.plot(lon, lat, latlon=True, 
                     color=COLORS[commodity], linewidth=line_width, 
                     solid_capstyle='round', solid_joinstyle='round')
        
        # Kappa_process: Process capacities consuming/producing a commodity
        r_in = prob.r_in.xs(commodity, level='Commodity')
        r_out = prob.r_out.xs(commodity, level='Commodity')
        sources = source.max(axis=1).xs(commodity, level='commodity')
        
        # multiply input/output ratios with capacities and drop non-matching 
        # process types completely
        consumers = Kappa_process.mul(r_in).dropna(how='all', axis=1).sum(axis=1)
        producers = Kappa_process.mul(r_out).dropna(how='all', axis=1).sum(axis=1)
        
        
        # iterate over all point types (consumers, producers, sources) with
        # different markers
        point_sources = [(consumers, 'v'), 
                         (producers, '^'),
                         (sources, 'D')]
        
        for kappas, marker_style in point_sources:
            # sum capacities
            kappa_sum = kappas.to_frame(name=commodity)
            
            # skip if empty
            if kappa_sum.empty:
                continue
                
            # add geometry (point coordinates)                
            kappa_sum = kappa_sum.join(prob._vertex.geometry)
            
            for k, row in kappa_sum.iterrows():
                # skip if no capacity installed
                if row[commodity] == 0:
                    continue
                    
                # coordinates
                lon, lat = row['geometry'].xy
                # size
                marker_size = 50 + math.sqrt(row[commodity]) * 4
                font_size = 6 + 6 * math.sqrt(row[commodity]) / 200
                # plot
                map.scatter(lon, lat, latlon=True,
                            c=COLORS[commodity], s=marker_size, 
                            marker=marker_style, lw=0.5,
                            edgecolor=(1, 1, 1), zorder=10)
                # annotate at line midpoint

                (x, y) = map(lon[len(lon)/2], lat[len(lat)/2])
                plt.annotate(
                    '%u'%row[commodity], xy=(x, y), 
                    fontsize=font_size, zorder=12, color=COLORS[commodity],
                    **annotate_defaults)
        
        # Kappa_hub
        # reuse r_in, r_out from before to select hub processes
        consumers = Kappa_hub.mul(r_in).dropna(how='all', axis=1).sum(axis=1)
        producers = Kappa_hub.mul(r_out).dropna(how='all', axis=1).sum(axis=1)
        
        # drop zero-capacity hubs
        consumers = consumers[consumers > 0]
        producers = producers[producers > 0]
        
        # iterate over both types (with different markers for both types)
        lines_sources = [(consumers, 'v'), 
                         (producers, '^')]
        for kappas, marker_style in lines_sources:
            # sum consuming capacities            
            kappa_sum = kappas.to_frame(name=commodity)
            
            # skip if empty
            if kappa_sum.empty:
                continue
            
            # join with vertex coordinates            
            kappa_sum = kappa_sum.join(prob._edge.geometry)
            
            for k, row in kappa_sum.iterrows():
                # coordinates
                line = row['geometry']
                midpoint = line.interpolate(0.5, normalized=True)
                x, y = map(midpoint.x, midpoint.y)
                # size
                marker_size = 50 + math.sqrt(row[commodity]) * 4
                font_size = 6 + 6 * math.sqrt(row[commodity]) / 200
                # plot
                map.scatter(x, y, latlon=False,
                            c=COLORS[commodity], s=marker_size, 
                            marker=marker_style, lw=0.5,
                            edgecolor=(1, 1, 1), zorder=11)
                # annotate at line midpoint
                if row[commodity] > 0:
                    plt.annotate(
                        '%u'%row[commodity], xy=(x, y), 
                        fontsize=font_size, zorder=12, color=COLORS['decoration'],
                        **annotate_defaults)

        plt.title("{} capacities".format(commodity))
    
    else:
        # demand plot
        demand = prob.peak.join(prob._edge.geometry)
    
        # demand: pipe capacities
        for k, row in demand.iterrows():
            # coordinates
            line = row['geometry']
            lon, lat = zip(*line.coords)

            # linewidth
            try:
                line_width = math.sqrt(row[commodity]) * 0.05
            except KeyError:
                warnings.warn("Skipping commodity {} without "
                              "demand.".format(commodity))
                return
            font_size = 6 + 6 * math.sqrt(row[commodity]) / 200
            # plot
            map.plot(lon, lat, latlon=True, 
                     color=COLORS[commodity], linewidth=line_width, 
                     solid_capstyle='round', solid_joinstyle='round')
            # annotate at line midpoint
            if row[commodity] > 0:
                midpoint = line.interpolate(0.5, normalized=True)
                (x, y) = map(midpoint.x, midpoint.y)
                plt.annotate(
                    '%u'%row[commodity], xy=(x, y), 
                    fontsize=font_size, zorder=12, color=COLORS[commodity],
                    **annotate_defaults)
        plt.title("{} demand".format(commodity))
    
    # map decoration
    map.drawmapboundary(linewidth=0)
    parallel_labels = [1,0,0,0] if tick_labels else [0,0,0,0]
    meridian_labels = [0,0,0,1] if tick_labels else [0,0,0,0]
    map.drawparallels(
        np.arange(bbox[0] + height * .15, bbox[2], height * .25), 
        color=COLORS['decoration'], 
        linewidth=0.1, labels=parallel_labels, dashes=[1, 0])
    map.drawmeridians(
        np.arange(bbox[1] + width * .15, bbox[3], width * .25), 
        color=COLORS['decoration'], 
        linewidth=0.1, labels=meridian_labels, dashes=[1, 0])
    
    # bar length = (horizontal map extent) / 3, rounded to 100 (1e-2) metres
    bar_length = round((map(bbox[3], bbox[2])[0] - 
                        map(bbox[1], bbox[0])[0]) / 3, -2)
    
    if mapscale:
        map.drawmapscale(
            bbox[1]+ 0.22 * width, bbox[0] + 0.1 * height, 
            central_meridian, central_parallel, bar_length,
            barstyle='fancy', units='m', zorder=13)  
    
    return fig
    
def report(prob, filename):
    """Write result summary to a spreadsheet file

    Args:
        prob: a rivus model instance
        filename: Excel spreadsheet filename, will be overwritten if exists

    Returns:
        Nothing
    """
    costs, Pmax, Kappa_hub, Kappa_process = get_constants(prob)
    source, flows, hubs, proc_io, proc_tau = get_timeseries(prob)
    
    with pd.ExcelWriter(filename) as writer:
        costs.to_frame().to_excel(writer, 'Costs')
        Pmax.to_excel(writer, 'Pmax')
        Kappa_hub.to_excel(writer, 'Kappa_hub')
        Kappa_process.to_excel(writer, 'Kappa_process')
        
        source.to_excel(writer, 'Source')
        flows.to_excel(writer, 'Flows')
        hubs.to_excel(writer, 'Hubs')
        proc_tau.to_excel(writer, 'Process')
