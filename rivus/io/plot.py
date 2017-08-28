""" plotting functions for rivus result visualisation
    Kristof Havasi
"""
from pandas import Series
from numpy import union1d
import math
from mpl_toolkits.basemap import Basemap

from rivus.main.rivus import get_constants, get_timeseries, line_length
from rivus.utils.pandashp import total_bounds

COLORS = {
    # (R,G,B) tuples with range (0-255)
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
    'CO2': (11, 12, 13),
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
for k, val in COLORS.items():
    COLORS[k] = 'rgb({},{},{})'.format(*val)


def _getbb(prob, bm=None):
    """
    Get bounding box of the optimization area
    Args:
        prob: pyomo modell
        bm: Basemap

    Returns:
        bbox, central_parallel, central_meridian
    """
    # set up Basemap for extent
    bbox = total_bounds(prob.params['vertex'])
    bbox = list(bbox)
    if bm:
        bbox[0:2] = bm(*bbox[0:2])
        bbox[2:4] = bm(*bbox[2:4])
    bbox = [bbox[1], bbox[0], bbox[3], bbox[2]]

    # set projection center to map center
    central_parallel = (bbox[0] + bbox[2]) / 2
    central_meridian = (bbox[1] + bbox[3]) / 2

    # increase map extent by X% in each direction
    EXTENT = 0.08
    height = bbox[2] - bbox[0]
    width = bbox[3] - bbox[1]
    bbox[0] -= EXTENT * height
    bbox[1] -= EXTENT * width
    bbox[2] += EXTENT * height
    bbox[3] += EXTENT * width
    return bbox, central_parallel, central_meridian


def _linewidth(value, scale=1.0):
    return math.sqrt(value) * 0.05 * scale


def _add_points(prob, bm, comm_zs, source, proc):
    """ Add Source points
    TODO:add process handling
    Args:
        prob (rivus model): For data retrieval
        bm (Basemap map): For coordinate transformation
        comm_zs (dict): To look up z positions of the layers
            like: {'Elec': 0, 'Heat': 5, 'Gas': 10}
        source (DataFrame): like retrieved with get_timeseries()
        proc (DataFrame): like retrieved with get_constants()

    Returns:
        TYPE: list of dict/plotly scatter3d objects
    """
    # Marker data arrays to plot them together
    markers = []
    for commodity in comm_zs:
        m_x, m_y, m_text, m_stly, m_size = [], [], [], [], []
        comm_z = comm_zs[commodity]
        # sources: Commodity source terms
        try:
            sources = source.max(axis=1).xs(commodity, level='commodity')
        except KeyError:
            sources = Series()

        # r_in = prob.r_in.xs(commodity, level='Commodity')
        # r_out = prob.r_out.xs(commodity, level='Commodity')
        # multiply input/output ratios with capacities and drop non-matching
        # process types completely
        # consumers = proc.mul(r_in).dropna(how='all', axis=1).sum(axis=1)
        # producers = proc.mul(r_out).dropna(how='all', axis=1).sum(axis=1)

        # iterate over all point types (consumers, producers, sources) with
        # different markers: (consumers, 'circle-open'), (producers, 'circle'),
        point_sources = [(sources, 'diamond')]

        for kappas, marker_style in point_sources:
            # sum capacities
            kappa_sum = kappas.to_frame(name=commodity)

            # skip if empty
            if kappa_sum.empty:
                continue

            # add geometry (point coordinates)
            kappa_sum = kappa_sum.join(prob.params['vertex'].geometry)

            for _, row in kappa_sum.iterrows():
                # skip if no capacity installed
                com_val = row[commodity]
                if com_val == 0:
                    continue

                point = row['geometry']
                xx, yy = bm(point.x, point.y)
                m_x.append(xx)
                m_y.append(yy)
                #marker_size = 3 + math.sqrt(com_val) * 1.5
                # m_size.append(marker_size)
                m_stly.append(marker_style)
                # look up unit ? TODO
                m_text.append('Src: {:.0f}'.format(com_val))
                # font_size = 5 + 5 * math.sqrt(com_val) / 200

        # Append a scatter dict per commodity
        markers.append({
            'type': 'scatter3d',
            'x': m_x, 'y': m_y, 'z': [comm_z] * len(m_y),
            'mode': 'marker',
            'legendgroup': commodity, 'showlegend': False,
            'hoverinfo': 'text',
            'hovertext': m_text,
            'marker': {
                'symbol': m_stly,
                'size': 14,
                'color': COLORS[commodity]
            }
        })

    return markers


def _add_edges(prob, bm, comms, comm_zs, Pmax, Hubs, dz=5,
               use_hubs=False, hub_opac=0.2, linescale=1,
               cap_txt=True, len_txt=True):
    # Inits =======================================
    capacities = []
    annots = []  # for hub connectors and capacity infos
    annot_devider = 8
    comm_offs = {
        # for placing anchors on a line
        # 0 for middle, 1 for one annot_devider further...
        'cap': -3 if use_hubs else 0,  # capacity of the line
        'Cool': -2,
        'Elec': -1,
        'Heat': 0,
        'Gas': 1,
        'CO2': 2,
    }

    oneline = {
        'type': 'scatter3d',
        'mode': 'lines',
        'hoverinfo': 'skip'
    }
    cap_groups = {}
    if Hubs.empty:
        use_hubs = False

    # Add dummies for legend formatting
    for com in comms:
        capacities.append({
            'type': 'scatter3d',
            'x': [0, 0], 'y': [0, 0], 'z': [0, 0],
            'mode': 'lines',
            'showlegend': True, 'legendgroup': com, 'name': com,
            'hoverinfo': 'skip',
            'line': {
                'width': 10,
                'color': COLORS[com]
            }
        })
        if com not in Pmax.columns.values:
            continue
        cap_groups[com] = {
            'type': 'scatter3d',
            'x': [], 'y': [], 'z': [],
            'mode': 'markers', 'opacity': 0.5,
            'showlegend': False, 'legendgroup': com, 'name': com,
            'hoverinfo': 'text', 'text': [],
            'marker': {
                'size': 5,
                'symbol': 'cross',
                'color': COLORS[com]
            }
        }
        capacities.append(cap_groups[com])  # it's a convinience link

    if use_hubs:
        hub_legends = []

    # Iterate over edges ==========================
    for v1v2, line in prob.params['edge'].geometry.iteritems():
        linprj = [bm(*coo) for coo in list(line.coords)]
        xs, ys = zip(*linprj)
        anchor_x, anchor_y = sum(xs) / len(xs), sum(ys) / len(ys)
        for com in comms:
            is_built_comm = com in Pmax.columns.values
            if is_built_comm:
                comm_cap = Pmax.get_value(v1v2, com)
                if comm_cap > 0:
                    is_built_edge = True
                else:
                    is_built_edge = False

            if is_built_comm and is_built_edge:
                lwidth = _linewidth(comm_cap, linescale)
                dash = 'solid'
            elif not is_built_comm or not is_built_edge:
                comm_cap = 0
                lwidth = 2
                dash = 'dash'
            capacities.append(
                dict(oneline, x=xs, y=ys, z=[comm_zs[com]] * len(xs),
                     legendgroup=com, name=com, showlegend=False,
                     line=dict(
                         width=lwidth,
                         color=COLORS[com],
                         dash=dash)))

            if use_hubs and v1v2 in Hubs.index.values:
                these_hubs = Hubs.xs(v1v2)
                for hub, val in these_hubs[these_hubs > 0].iteritems():
                    produced = prob.r_out.xs(hub, level='Process') * val
                    from_com = prob.r_in.xs(
                        hub, level='Process').index.values[0]
                    from_z = comm_zs[from_com]
                    for prod_com, prod_val in produced.iteritems():
                        if not (from_com in comms and prod_com in comms):
                            continue  # only show connections to given comms
                        to_z = comm_zs[prod_com]
                        xx = (abs(anchor_x - xs[0]) / annot_devider *
                              comm_offs[prod_com] + anchor_x)
                        yy = (abs(anchor_y - ys[0]) / annot_devider *
                              comm_offs[prod_com] + anchor_y)
                        legend = 'Hub: {} -> {}'.format(from_com, prod_com)
                        is_first = legend not in hub_legends
                        if is_first:
                            hub_legends.append(legend)
                        produced_txt = (produced.to_string(header=False)
                                        .replace('\n', '<br>'))
                        annot_text = '{0}:<br>{1}'.format(hub, produced_txt)
                        annots.append({
                            'type': 'scatter3d',
                            'x': [xx] * 2, 'y': [yy] * 2, 'z': [from_z, to_z],
                            'showlegend': is_first, 'legendgroup': legend,
                            'name': legend,
                            'opacity': hub_opac, "hoverinfo": "text",
                            'text': [annot_text, ''],
                            'mode': 'lines+markers',
                            'line': {
                                'color': COLORS[prod_com],
                                'width': 8,  # prod_val * 2,
                                'dash': 'longdash',
                            },
                            'marker': {
                                'size': 6,
                                'symbol': ['circle-open', 'circle']
                            }
                        })

            if cap_txt and is_built_comm:
                if len_txt:
                    linelength = line_length(line)
                xx = abs(anchor_x - xs[0]) / \
                    annot_devider * comm_offs['cap'] + anchor_x
                yy = abs(anchor_y - ys[0]) / \
                    annot_devider * comm_offs['cap'] + anchor_y
                hovertext = 'cap: {}'.format(comm_cap) if not len_txt \
                    else 'cap: {0}<br>len: {1:.1f} m'.format(comm_cap,
                                                             linelength)
                cap_groups[com]['x'].append(xx)
                cap_groups[com]['y'].append(yy)
                cap_groups[com]['z'].append(comm_zs[com])
                cap_groups[com]['text'].append(hovertext)

            if len_txt and not cap_txt:
                pass

    return capacities, annots


def fig3d(prob, comms=None, linescale=1.0, use_hubs=False, hub_opac=0.55, dz=5,
          layout=None, verbose=False):
    """
    Generate 3D representation of the rivus results using plotly

    Args:
        prob (rivus_archive): A rivus model (later extract of it)
        comms (None, optional): list/ndarray of commodity names to plot,
               Order: ['C1', 'C2', 'C3'] -> Bottom: C1, Top: C3
        linescale (float, optional):
            A multiplier to get proportionally thicker lines.
        use_hubs (bool, optional): Switch to depict hub processes.
        hub_opac (float, optional): 0-1 opacity param.
        dz (number, optional): Distance between layers along 'z' axis .
        layout (None, optional): A plotly layout dict to overwrite default.
        verbose (bool, optional): To print out progress and the time it took.

    Usage:
        import plotly.offline as po
        fig = fig3d(prob, ['Gas', 'Heat', 'Elec'], hub_opac=0.55, linescale=7)
        # for static image
        # po.plot(fig, filename='plotly-game.html', image='png')
        po.plot(fig, filename='plotly-game.html')

    Returns:
        plotly compatible figure *dict* (in plotly everything is kinda a dict.)
    """
    if verbose:
        import time
        plotprep = time.time()

    # Map projection
    bbox, cent_para, cent_meri = _getbb(prob)
    bm = Basemap(
        projection='tmerc', resolution=None,
        llcrnrlat=bbox[0], llcrnrlon=bbox[1],
        urcrnrlat=bbox[2], urcrnrlon=bbox[3],
        lat_0=cent_para, lon_0=cent_meri)

    # Get result values for plotting
    _, Pmax, Kappa_hub, Kappa_process = get_constants(prob)
    source = get_timeseries(prob)[0]

    # Use all commodities if none is given
    if comms is None:
        comm_order = {  # values set the sort order
            'Demand': 0,
            'Gas': 5,
            'CO2': 10,
            'Heat': 15,
            'Elec': 20,
            'Cool': 25,
        }
        # Drop all 0 columns in Pmax
        for column in Pmax:
            if all(Pmax[column] == 0):
                del Pmax[column]
        comms = Pmax.columns.values

        proc_used = Kappa_process.columns.values
        if len(proc_used):
            proc_comms = (prob.r_in.loc[proc_used].index
                          .get_level_values(level='Commodity')
                          .union(prob.r_out.loc[proc_used].index
                                 .get_level_values(level='Commodity')))
            comms = union1d(comms, proc_comms.values)

        hubs_used = Kappa_hub.columns.values
        if len(hubs_used):
            hub_comms = (prob.r_in.loc[hubs_used].index
                         .get_level_values(level='Commodity')
                         .union(prob.r_out.loc[hubs_used].index
                                .get_level_values(level='Commodity')))
            comms = union1d(comms, hub_comms.values)
        comms = sorted(comms, key=lambda comm: comm_order[comm])

    comm_zs = [dz * k for k, c in enumerate(comms)]
    comm_zs = dict(zip(comms, comm_zs))
    # geoPmax = Pmax.join(prob.params['edge'].geometry, how='inner')
    if verbose:
        print("plot prep took: {:.4f}".format(time.time() - plotprep))
        layersstart = time.time()

    # Adding capacity lines: capacities and hubs
    edge_kwargs = {
        'Pmax': Pmax, 'Hubs': Kappa_hub, 'dz': 5,
        'use_hubs': use_hubs, 'hub_opac': hub_opac, 'linescale': linescale}
    cap_layers, hub_layer = _add_edges(prob, bm, comms, comm_zs, **edge_kwargs)
    # Adding markers
    markers = _add_points(prob, bm, comm_zs, source, Kappa_process)
    if verbose:
        print("layers took: {:.4f}".format(time.time() - layersstart))

    layout = {
        # 'autosize' : False,
        # 'width' : 500,
        # 'height' : 500,
        # paper_bgcolor='#7f7f7f', plot_bgcolor='#c7c7c7'
        'margin': {
            'l': 0, 'r': 0,
            'b': 10, 't': 0,
            'pad': 4
        },
        'legend': {
            'traceorder': 'reversed',
            # 'y': 2,
            #'yanchor' : 'center'
        },
        'scene': {
            'xaxis': {
                'visible': False
            },
            'yaxis': {
                'visible': False
            },
            'zaxis': {
                'visible': False,
                # 'range' : [0, comm_zs[-1] + dz]
            },
            'aspectmode': 'data',
            # 'aspectratio': {
            #     'x': 1, 'y': 1, 'z': .6
            # }
        }
        # 'width' : 700
    }

    data = cap_layers + hub_layer + markers
    fig = dict(data=data, layout=layout)
    return fig
