"""rivus: optimization model for distributed urban energy systems

rivus optimizes topology and size of urban energy networks, energy conversion.

"""
import warnings
try:
    import pyomo.core as pyomo
except ImportError:
    import coopr.pyomo as pyomo
    warnings.warn("Support for Pyomo 3.x is now deprecated and will be removed"
                  "removed with the next release. Please upgrade to Pyomo 4.",
                  FutureWarning, stacklevel=2)
import math
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
import numpy as np
import os
import pandas as pd
from ..utils import pandashp as pdshp
import warnings
from geopy.distance import distance
from mpl_toolkits.basemap import Basemap


COLORS = { # (R,G,B) tuples with range (0-255)
    # defaults
    'base': (192, 192, 192),
    'building': (192, 192, 192),
    'decoration': (128, 128, 128),
    # commodities
    'Heat': (230, 112, 36),
    'Cool': (0, 0, 255),
    'Elec': (255, 170, 0),
    'Demand': (0, 255, 0),
    'Gas': (128, 64, 0),
    # buildings
    'industrial': (240, 198, 116),
    'residential': (181, 189, 104),
    'commercial': (129, 162, 190),
    'basin': (110, 75, 56),
    'chapel': (177, 121, 91),
    'church': (177, 121, 91),
    'farm': (202, 178, 214),
    'farm_auxiliary': (106, 61, 154),
    'garage': (253, 191, 111),
    'greenhouse': (255, 127, 0),
    'hospital': (129, 221, 190),
    'hotel': (227, 26, 28),
    'house': (181, 189, 104),
    'office': (129, 162, 190),
    'public': (129, 162, 190),
    'restaurant': (227, 26, 28),
    'retail': (129, 162, 190),
    'school': (29, 103, 214),
    'warehouse': (98, 134, 6),
}
to_rgb = lambda r,g,b: tuple(x/255. for x in (r,g,b))
for key, val in COLORS.items():
    COLORS[key] = to_rgb(*val)

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
        commodity = xls.parse('Commodity').set_index(['Commodity'])
        process = xls.parse('Process').set_index(['Process'])
        time = xls.parse('Time').set_index(['Time'])
        area_demand = xls.parse('Area-Demand').set_index(['Area', 'Commodity'])
        process_commodity = (
            xls.parse('Process-Commodity')
               .set_index(['Process', 'Commodity', 'Direction']))

    data = {
        'commodity': commodity,
        'process': process,
        'process_commodity': process_commodity,
        'time': time,
        'area_demand': area_demand}

    # sort nested indexes to make direct assignments work, cf
    # http://pandas.pydata.org/pandas-docs/stable/indexing.html#the-need-for-sortedness-with-multiindex
    # https://pandas.pydata.org/pandas-docs/stable/generated/pandas.DataFrame.sort_index.html#pandas.DataFrame.sort_index
    for key in data:
        if isinstance(data[key].index, pd.core.index.MultiIndex):
            data[key].sort_index(inplace=True)
    return data


def create_model(data, vertex, edge, peak_multiplier=None):
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
    m.params = data

    # DataFrame aliases
    commodity = data['commodity']
    process = data['process']
    process_commodity = data['process_commodity']
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
    is_hub = (has_cost_inv_fix_0 & has_cap_min_0 & has_one_input & has_r_in_1)
    hub = process[is_hub.reindex(process.index)]
    m.params['hub'] = hub

    # derive peak and demand of edges
    # by selecting edge columns that are named like area types (res, com, ind)
    area_types = list(area_demand.index.levels[0])
    edge_areas = edge[edge.columns.intersection(area_types)]

    # helper function: calculates outer product of column in table area_demand
    # with specified series, which is applied to the columns of edge_areas
    def multiply_by_area_demand(series, column):
        return (area_demand[column].loc[series.name]
                                   .apply(lambda x: x*series)
                                   .stack())

    # peak(edge, commodity) in kW
    m.peak = (edge_areas.apply(lambda x: multiply_by_area_demand(x, 'peak'))
                        .sum(axis=1)
                        .unstack('Commodity'))

    # reindex edges to vertex tuple index
    vertex.set_index('Vertex', inplace=True)
    edge.set_index(['Vertex1', 'Vertex2'], inplace=True)
    m.peak.index = edge.index
    m.peak.sort_index(inplace=True)

    # store geographic DataFrames vertex & edge for later use
    m.params['vertex'] = vertex.copy()
    m.params['edge'] = edge.copy()

    if peak_multiplier:
        m.peak = peak_multiplier(m)

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
    no_source_commodities = commodity.index.difference(vertex.columns)
    for co in no_source_commodities:
        vertex[co] = 0

    # find commodities for which there is a non-zero, finite allowed maximum
    has_allowed_max = (commodity['allowed-max'] > 0 &
                       ~commodity['allowed-max'].apply(math.isinf))
    co_allowed_max = commodity[has_allowed_max].index

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
    m.co_allowed_max = pyomo.Set(
        within=m.commodity,
        initialize=co_allowed_max,
        doc='Commodities that have a maximum allowed generation (e.g. CO2)')

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

    # Equation declarations

    # edges/arcs
    m.peak_satisfaction = pyomo.Constraint(
        m.edge, m.co_demand, m.time,
        rule=peak_satisfaction_rule,
        doc='peak must be satisfied by Sigma and hub process output')
    m.edge_equation = pyomo.Constraint(
        m.edge, m.commodity, m.time,
        rule=edge_equation_rule,
        doc='Sigma is provided by arc flow difference Pin-Pot in either direction')
    m.arc_flow_by_capacity = pyomo.Constraint(
        m.arc, m.co_transportable, m.time,
        rule=arc_flow_by_capacity_rule,
        doc='Pin <= Pmax')
    m.arc_flow_unidirectionality = pyomo.Constraint(
        m.arc, m.co_transportable, m.time,
        rule=arc_flow_unidirectionality_rule,
        doc='Pin <= Cmax * Psi')
    m.arc_unidirectionality = pyomo.Constraint(
        m.arc, m.co_transportable, m.time,
        rule=arc_unidirectionality_rule,
        doc='Psi[i,j,t] + Psi[j,i,t] <= 1')
    m.edge_capacity = pyomo.Constraint(
        m.edge, m.co_transportable,
        rule=edge_capacity_rule,
        doc='Pmax <= Cmax * Xi')

    # hubs
    m.hub_supply = pyomo.Constraint(
        m.edge, m.commodity, m.time,
        rule=hub_supply_rule,
        doc='Hub inputs <= Sigma')

    m.hub_output_by_capacity = pyomo.Constraint(
        m.edge, m.hub, m.time,
        rule=hub_output_by_capacity_rule,
        doc='Epsilon_hub <= Kappa_hub')
    m.hub_capacity = pyomo.Constraint(
        m.edge, m.hub,
        rule=hub_capacity_rule,
        doc='Kappa_hub <= Cmax')

    # vertex
    m.vertex_equation = pyomo.Constraint(
        m.vertex, m.commodity, m.time,
        rule=vertex_equation_rule,
        doc='Rho >= Process balance + Arc flow balance')
    m.source_vertices = pyomo.Constraint(
        m.vertex, m.co_source, m.time,
        rule=source_vertices_rule,
        doc='Rho <= Cmax')

    # commodity
    m.commodity_maximum = pyomo.Constraint(
        m.co_allowed_max,
        rule=commodity_maximum_rule,
        doc='Net commodity generation <= allowed-max')

    # process
    m.process_throughput_by_capacity = pyomo.Constraint(
        m.vertex, m.process, m.time,
        rule=process_throughput_by_capacity_rule,
        doc='Tau <= Kappa_process')
    m.process_capacity_min = pyomo.Constraint(
        m.vertex, m.process,
        rule=process_capacity_min_rule,
        doc='Kappa_process >= Cmin * Phi')
    m.process_capacity_max = pyomo.Constraint(
        m.vertex, m.process,
        rule=process_capacity_max_rule,
        doc='Kappa_process <= Cmax * Phi')
    m.process_input = pyomo.Constraint(
        m.vertex, m.process_input_tuples, m.time,
        rule=process_input_rule,
        doc='Epsilon_in = Tau * r_in')
    m.process_output = pyomo.Constraint(
        m.vertex, m.process_output_tuples, m.time,
        rule=process_output_rule,
        doc='Epsilon_out = Tau * r_out')

    # costs
    m.def_costs = pyomo.Constraint(
        m.cost_type,
        rule=def_costs_rule,
        doc='Costs = sum of activities')
    m.obj = pyomo.Objective(
        sense=pyomo.minimize,
        rule=obj_rule,
        doc='Sum costs by cost type')

    return m

# Constraint functions

# edges/arcs
def peak_satisfaction_rule(m, i, j, co, t):
    provided_power = hub_balance(m, i, j, co, t) + m.Sigma[i, j, co, t]
    return provided_power >= m.peak.loc[i,j][co] * m.params['time'].loc[t][co]

def edge_equation_rule(m, i, j, co, t):
    if co in m.co_transportable:
        length = line_length(m.params['edge'].loc[i, j]['geometry'])

        flow_in = ( 1 - length * m.params['commodity'].loc[co]['loss-var']) * \
                  ( m.Pin[i,j,co,t] + m.Pin[j,i,co,t] )
        flow_out =  m.Pot[i,j,co,t] + m.Pot[j,i,co,t]
        fixed_losses = ( m.Psi[i,j,co,t] + m.Psi[j,i,co,t] ) * \
                       length * m.params['commodity'].loc[co]['loss-fix']

        return m.Sigma[i,j,co,t] <= flow_in - flow_out - fixed_losses
    else:
        return m.Sigma[i,j,co,t] <= 0

def arc_flow_by_capacity_rule(m, i, j, co, t):
    (v1, v2) = find_matching_edge(m, i, j)
    return m.Pin[i,j,co,t] <= m.Pmax[v1, v2, co]

def arc_flow_unidirectionality_rule(m, i, j, co, t):
    return m.Pin[i,j,co,t] <= m.params['commodity'].loc[co]['cap-max'] * m.Psi[i,j,co,t]

def arc_unidirectionality_rule(m, i, j, co, t):
    return m.Psi[i,j,co,t] + m.Psi[j,i,co,t] <= 1

def edge_capacity_rule(m, i, j, co):
    return m.Pmax[i,j,co] <= m.Xi[i,j,co] * m.params['commodity'].loc[co]['cap-max']

# hubs
def hub_supply_rule(m, i, j, co, t):
    hub_input_power = - hub_balance(m, i, j, co, t)
    return hub_input_power <= m.Sigma[i,j,co,t]

def hub_output_by_capacity_rule(m, i, j, h, t):
    return m.Epsilon_hub[i,j,h,t] <= m.Kappa_hub[i,j,h]

def hub_capacity_rule(m, i, j, h):
    return m.Kappa_hub[i,j,h] <= m.params['hub'].loc[h]['cap-max']

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
    return m.Rho[v,co,t]<= m.params['vertex'].loc[v][co]

# commodity
def commodity_maximum_rule(m, co):
    total_generation = 0
    for t in m.time:
        generation_per_timestep = 0
        for v in m.vertex:
            generation_per_timestep += process_balance(m, v, co, t)
        for e in m.edge:
            generation_per_timestep += hub_balance(m, e[0], e[1], co, t)
        generation_per_timestep *= m.params['time'].loc[t]['weight']
        total_generation += generation_per_timestep
    return total_generation <= m.params['commodity'].loc[co]['allowed-max']

# process
def process_throughput_by_capacity_rule(m, v, p, t):
    return m.Tau[v,p,t] <= m.Kappa_process[v, p]

def process_capacity_min_rule(m, v, p):
    return m.Kappa_process[v, p] >= m.Phi[v, p] * m.params['process'].loc[p]['cap-min']

def process_capacity_max_rule(m, v, p):
    return m.Kappa_process[v, p] <= m.Phi[v, p] * m.params['process'].loc[p]['cap-max']

def process_input_rule(m, v, p, co, t):
    return m.Epsilon_in[v, p, co, t] == m.Tau[v, p, t] * m.r_in.loc[p, co]

def process_output_rule(m, v, p, co, t):
    return m.Epsilon_out[v, p, co, t] == m.Tau[v, p, t] * m.r_out.loc[p, co]

# Objective

def def_costs_rule(m, cost_type):
    if cost_type == 'Inv':
        return m.costs['Inv'] == \
            sum(m.Kappa_hub[i,j,h] * m.params['hub'].loc[h]['cost-inv-var']
                for (i,j) in m.edge for h in m.hub) + \
            sum(m.Kappa_process[v,p] * m.params['process'].loc[p]['cost-inv-var'] +
                m.Phi[v,p] * m.params['process'].loc[p]['cost-inv-fix']
                for v in m.vertex for p in m.process) + \
            sum((m.Pmax[i,j,co] * m.params['commodity'].loc[co]['cost-inv-var'] +
                 m.Xi[i,j,co] * m.params['commodity'].loc[co]['cost-inv-fix']) *
                line_length(m.params['edge'].loc[i, j]['geometry'])
                for (i,j) in m.edge for co in m.co_transportable)

    elif cost_type == 'Fix':
        return m.costs['Fix'] == \
            sum(m.Kappa_hub[i,j,h] * m.params['hub'].loc[h]['cost-fix']
                for (i,j) in m.edge for h in m.hub) + \
            sum(m.Kappa_process[v,p] * m.params['process'].loc[p]['cost-fix']
                for v in m.vertex for p in m.process) + \
            sum(m.Pmax[i,j,co] * m.params['commodity'].loc[co]['cost-fix'] *
                line_length(m.params['edge'].loc[i, j]['geometry'])
                for (i,j) in m.edge for co in m.co_transportable)

    elif cost_type == 'Var':
        return m.costs['Var'] == \
            sum(m.Epsilon_hub[i,j,h,t] *
                m.params['hub'].loc[h]['cost-var'] *
                m.params['time'].loc[t]['weight']
                for (i,j) in m.edge for h in m.hub for t in m.time) + \
            sum(m.Tau[v,p,t] *
                m.params['process'].loc[p]['cost-var'] *
                m.params['time'].loc[t]['weight']
                for v in m.vertex for p in m.process for t in m.time) + \
            sum(m.Rho[v,co,t] *
                m.params['commodity'].loc[co]['cost-var'] *
                m.params['time'].loc[t]['weight']
                for v in m.vertex for co in m.co_source for t in m.time)

    else:
        raise NotImplementedError("Unknown cost type!")

def obj_rule(m):
    return pyomo.summation(m.costs)


# Helper functions for model

def hub_balance(m, i, j, co, t):
    """Calculate commodity balance in an edge {i,j} from/to hubs. """
    balance = 0
    for h in m.hub:
        if co in m.r_in.loc[h].index:
            balance -= m.Epsilon_hub[i,j,h,t] * m.r_in.loc[h,co] # m.r_in = 1 by definition
        if co in m.r_out.loc[h].index:
            balance += m.Epsilon_hub[i,j,h,t] * m.r_out.loc[h,co]
    return balance

def flow_balance(m, v, co, t):
    """Calculate commodity flow balance in a vertex from/to arcs. """
    balance = 0
    for w in m.neighbours[v]:
        balance += m.Pot[w,v,co,t]
        balance -= m.Pin[v,w,co,t]
    return balance

def process_balance(m, v, co, t):
    """Calculate commodity balance in a vertex from/to processes. """
    balance = 0
    for p in m.process:
        if co in m.r_in.loc[p].index:
            balance -= m.Epsilon_in[v,p,co,t]
        if co in m.r_out.loc[p].index:
            balance += m.Epsilon_out[v,p,co,t]
    return balance

def find_matching_edge(m, i, j):
    """Return corresponding edge for a given arc. """
    if (i,j) in m.edge:
        return (i,j)
    else:
        return (j,i)


# Helper functions for data preparation

def line_length(line):
    """Calculate length of a line in meters, given in geographic coordinates.

    Args:
        line: a shapely LineString object with WGS 84 coordinates

    Returns:
        Length of line in meters
    """
    return sum(distance(a, b).meters for (a, b) in pairs(line.coords))


def pairs(lst):
    """Iterate over a list in overlapping pairs without wrap-around.

    Args:
        lst: an iterable/list

    Returns:
        Yields a pair of consecutive elements (lst[k], lst[k+1]) of lst. Last
        call yields the last two elements.

    Example:
        lst = [4, 7, 11, 2]
        pairs(lst) yields (4, 7), (7, 11), (11, 2)

    Source:
        http://stackoverflow.com/questions/1257413/1257446#1257446
    """
    i = iter(lst)
    prev = next(i)
    for item in i:
        yield prev, item
        prev = item

# Technical helper functions for data retrieval

def get_entity(instance, name):
    """Return a DataFrame for an entity in model instance.

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
    """Return one DataFrame with entities in columns and a common index.

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
    """Return list of sets, params, variables, constraints or objectives.

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
        proc_tau = proc_tau.unstack().fillna(0).applymap(round)

    return source, flows, hubs, proc_io, proc_tau


def plot(prob, commodity, plot_demand=False, mapscale=False, tick_labels=True,
         annotations=True, buildings=None, shapefiles=None):
    """Plot a map of supply, conversion, transport and consumption.

    For given commodity, plot a map of all locations where the commodity is
    introduced (Rho), transported (Pin/Pot/Pmax), converted (Epsilon_*) and
    consumed (Sigma, peak).

    Args:
        prob:
        commodity:
        plot_demand: If True, plot demand, else plot capacities
        mapscale: If True, add mapscale to plot (default: False)
        tick_labels: If True, add lon/lat tick labels (default: True)
        annotations: If True, add numeric labels to graph (default: True)
        buildings: tuple of (filename to shapefile, boolean)
                   if true, color buildings according to attribute column
                   "type" and colors in constan rivus.COLORS; else use default
                   COLOR['building'] for all
        shapefiles: list of dicts of shapefiles that shall be drawn by
                    basemap function readshapefile. is passed as **kwargs
    Returns:
        fig: the map figure object
    """

    # set up Basemap for extent
    bbox = pdshp.total_bounds(prob.params['vertex'])
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
        path_effects=[pe.withStroke(linewidth=1, foreground="w")])

    # create new figure with basemap in Transverse Mercator projection
    # centered on map location
    fig = plt.figure()
    bm = Basemap(
        projection='tmerc', resolution=None,
        llcrnrlat=bbox[0], llcrnrlon=bbox[1],
        urcrnrlat=bbox[2], urcrnrlon=bbox[3],
        lat_0=central_parallel, lon_0=central_meridian)

    if shapefiles:
        for shp in shapefiles:
            bm.readshapefile(**shp)

    # basemap: plot buildings if provided
    if buildings:
        # unpack option tuple
        building_shapefile, color_buildings = buildings

        # Function readshapefiles sadly only supports drawing the outlines,
        # filling is a bit more involved. Here I'm using the technique from
        # http://basemaptutorial.readthedocs.org/en/latest/shapefile.html
        # in section "Filling polygons".
        from collections import defaultdict
        from matplotlib.patches import Polygon
        from matplotlib.collections import PatchCollection

        bm.readshapefile(building_shapefile, 'buildings', drawbounds=False)
        patches = {}
        for info, shape in zip(bm.buildings_info, bm.buildings):
            group = patches.setdefault(info['type'], [])
            group.append(Polygon(np.array(shape), True))

        # prepare colors defaultdict
        building_colors = defaultdict(lambda: COLORS['building'])
        # only use type-color if option is set
        if color_buildings:
            building_colors.update(COLORS)

        # now color all patches accoridng to type; defaultdict automatically
        # returns COLORS['building'] for unknown building types
        for key in patches:
            pc = PatchCollection(patches[key], facecolor=building_colors[key],
                                 edgecolor='none', zorder=10)
            plt.gca().add_collection(pc)

    # basemap: street network
    for k, row in prob.params['edge'].iterrows():
        line = row['geometry']
        lon, lat = zip(*line.coords)
        # plot
        bm.plot(lon, lat, latlon=True,
                color=COLORS['base'], linewidth=0.1, zorder=19,
                solid_capstyle='round', solid_joinstyle='round')

    if not plot_demand:
        # default commodity plot with Pmax, Kappa_hub, Kappa_process, sources

        # read data from solution
        _, Pmax, Kappa_hub, Kappa_process = get_constants(prob)
        source = get_timeseries(prob)[0]

        # Pmax: pipe capacities (if existing)
        if commodity in Pmax.columns:
            Pmax = Pmax.join(prob.params['edge'].geometry)
            for k, row in Pmax.iterrows():
                # coordinates
                line = row['geometry']
                lon, lat = zip(*line.coords)
                # linewidth
                line_width = math.sqrt(row[commodity]) * 0.025
                # plot
                bm.plot(lon, lat, latlon=True, zorder=20,
                        color=COLORS[commodity], linewidth=line_width,
                        solid_capstyle='round', solid_joinstyle='round')

        # Kappa_process: Process capacities consuming/producing a commodity
        r_in = prob.r_in.xs(commodity, level='Commodity')
        r_out = prob.r_out.xs(commodity, level='Commodity')

        # sources: Commodity source terms
        try:
            sources = source.max(axis=1).xs(commodity, level='commodity')
        except KeyError:
            sources = pd.Series()

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
            kappa_sum = kappa_sum.join(prob.params['vertex'].geometry)

            for k, row in kappa_sum.iterrows():
                # skip if no capacity installed
                if row[commodity] == 0:
                    continue

                # coordinates
                lon, lat = row['geometry'].xy
                # size
                marker_size = 0 + math.sqrt(row[commodity]) * 1.5
                font_size = 3 + 5 * math.sqrt(row[commodity]) / 200
                # plot
                bm.scatter(lon, lat, latlon=True,
                            c=COLORS[commodity], s=marker_size,
                            marker=marker_style, lw=0.5,
                            edgecolor=(1, 1, 1), zorder=30)
                # annotate at line midpoint

                (x, y) = bm(lon[len(lon)//2], lat[len(lat)//2])
                if annotations:
                    plt.annotate(
                        '%u'%row[commodity], xy=(x, y),
                        fontsize=font_size, zorder=31, color=COLORS[commodity],
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
            kappa_sum = kappa_sum.join(prob.params['edge'].geometry)

            for k, row in kappa_sum.iterrows():
                # coordinates
                line = row['geometry']
                midpoint = line.interpolate(0.5, normalized=True)
                x, y = bm(midpoint.x, midpoint.y)
                # size
                marker_size = 0 + math.sqrt(row[commodity]) * 1.5
                font_size = 3 + 5 * math.sqrt(row[commodity]) / 200
                # plot
                bm.scatter(x, y, latlon=False,
                            c=COLORS[commodity], s=marker_size,
                            marker=marker_style, lw=0.5,
                            edgecolor=(1, 1, 1), zorder=40)
                # annotate at line midpoint
                if annotations and row[commodity] > 0:
                    plt.annotate(
                        '%u'%row[commodity], xy=(x, y),
                        fontsize=font_size, zorder=41,
                        color=COLORS['decoration'], **annotate_defaults)

        plt.title("{} capacities".format(commodity))

    else:
        # demand plot
        demand = prob.peak.join(prob.params['edge'].geometry)

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
            font_size = 3 + 5 * math.sqrt(row[commodity]) / 200
            # plot
            bm.plot(lon, lat, latlon=True,
                    color=COLORS[commodity], linewidth=line_width,
                    solid_capstyle='round', solid_joinstyle='round',
                    zorder=20)
            # annotate at line midpoint
            if row[commodity] > 0:
                midpoint = line.interpolate(0.5, normalized=True)
                (x, y) = bm(midpoint.x, midpoint.y)
                if annotations:
                    plt.annotate(
                        '%u'%row[commodity], xy=(x, y),
                        fontsize=font_size, zorder=21,
                        color=COLORS['decoration'], **annotate_defaults)
        plt.title("{} demand".format(commodity))

    # map decoration
    bm.drawmapboundary(linewidth=0)
    parallel_labels = [1,0,0,0] if tick_labels else [0,0,0,0]
    meridian_labels = [0,0,0,1] if tick_labels else [0,0,0,0]
    bm.drawparallels(
        np.arange(bbox[0] + height * .15, bbox[2], height * .25),
        color=COLORS['decoration'], zorder=9,
        linewidth=0.1, labels=parallel_labels, dashes=(None, None))
    bm.drawmeridians(
        np.arange(bbox[1] + width * .15, bbox[3], width * .25),
        color=COLORS['decoration'], zorder=9,
        linewidth=0.1, labels=meridian_labels, dashes=(None, None))

    # bar length = (horizontal map extent) / 3, rounded to 100 (1e-2) metres
    bar_length = round((bm(bbox[3], bbox[2])[0] -
                        bm(bbox[1], bbox[0])[0]) / 3, -2)

    if mapscale:
        bm.drawmapscale(
            bbox[1]+ 0.22 * width, bbox[0] + 0.1 * height,
            central_meridian, central_parallel, bar_length,
            barstyle='simple', units='m', zorder=25,
            fontcolor=(.2, .2, .2), fillcolor2=(.2, .2, .2))

    return fig

def result_figures(prob, file_basename, buildings=None, shapefiles=None):
    """Call rivus.plot with hard-coded combinations of plot_type and commodity.

    This is a convenience wrapper to shorten scripts.
    TODO: Generalise so that no hard-coding of commodity names is needed.

    Args:
        prob: a rivus model instance
        file_basename: filename prefix for figures
        buildings: optional filename to buildings shapefile

    Returns:
        Nothing
    """
    for com, plot_type in [('Elec', 'caps'), ('Heat', 'caps'), ('Gas', 'caps'),
                           ('Elec', 'peak'), ('Heat', 'peak')]:

        # two plot variants
        for plot_annotations in [False, True]:
            # create plot
            fig = plot(prob, com, mapscale=False, tick_labels=False,
                       plot_demand=(plot_type == 'peak'),
                       buildings=buildings,
                       shapefiles=shapefiles,
                       annotations=plot_annotations)
            plt.title('')

            # save to file
            for ext, transp in [('png', True), ('png', False), ('pdf', True)]:
                # split scenario name from subdirectory
                base_dir, sce = os.path.split(file_basename)

                # create subdirectory according to plot variant
                sub_dir = 'annotated' if plot_annotations else 'plain'
                sub_dir += '-transparent' if transp and ext!= 'pdf' else ''

                # create subdirectory if does not exist yet
                fig_dir = os.path.join(base_dir, sub_dir)
                if not os.path.exists(fig_dir):
                    os.makedirs(fig_dir)

                # create complete relative figure filename
                fig_basename = '{}-{}-{}.{}'.format(sce, plot_type, com, ext)
                fig_filename = os.path.join(fig_dir, fig_basename)

                # save the figure
                fig.savefig(fig_filename, dpi=300, bbox_inches='tight',
                            transparent=transp)
            # free memory
            plt.close(fig)



def report(prob, filename):
    """Write result summary to a spreadsheet file.

    Create a concise result spreadsheet with values of all key variables,
    inclduing costs, pipe capacities, process and hub capacities, source flows,
    and process input/output/throughput per time step.

    Args:
        prob: a rivus model instance
        filename: Excel spreadsheet filename, will be overwritten if exists

    Returns:
        Nothing
    """
    costs, Pmax, Kappa_hub, Kappa_process = get_constants(prob)
    source, flows, hubs, proc_io, proc_tau = get_timeseries(prob)

    report_content = [
        (costs.to_frame(), 'Costs'),
        (Pmax, 'Pmax'),
        (Kappa_hub, 'Kappa_hub'),
        (Kappa_process, 'Kappa_process'),
        (source, 'Source'),
        (flows, 'Flows'),
        (hubs, 'Hubs'),
        (proc_io, 'Proc_io'),
        (proc_tau, 'Proc_tau')]

    with pd.ExcelWriter(filename) as writer:
        for df, sheet_name in report_content:
            if not df.empty:
                df.to_excel(writer, sheet_name)


def save_log(result, filename):
    """Save urbs result and solver information to a log file.

    Args:
        result: as returned by the solve method of a solver object
        filename: log file to be written

    Returns:
        Nothing
    """
    with open(filename, 'w') as file_handle:
        file_handle.write(str(result))


def save(prob, filename):
    """Save rivus model instance to a gzip'ed pickle file

    Pickle is the standard Python way of serializing and de-serializing Python
    objects. By using it, saving any object, in case of this function a
    Pyomo ConcreteModel, becomes a twoliner.
    <https://docs.python.org/2/library/pickle.html>
    GZip is a standard Python compression library that is used to transparently
    compress the pickle file further.
    <https://docs.python.org/2/library/gzip.html>
    It is used over the possibly more compact bzip2 compression due to the
    lower runtime. Source: <http://stackoverflow.com/a/18475192/2375855>

    Args:
        prob: a rivus model instance
        filename: pickle file to be written

    Returns:
        Nothing
    """
    import gzip
    try:
        import cPickle as pickle
    except ImportError:
        import pickle
    with gzip.GzipFile(filename, 'wb') as file_handle:
        pickle.dump(prob, file_handle)

def load(filename):
    """Load a rivus model instance from a gzip'ed pickle file

    Args:
        filename: pickle file

    Returns:
        prob: the unpickled rivus model instance
    """
    import gzip
    try:
        import cPickle as pickle
    except ImportError:
        import pickle
    with gzip.GzipFile(filename, 'r') as file_handle:
        prob = pickle.load(file_handle)
    return prob
