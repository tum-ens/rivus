"""Functions are collected here, which can be useful in case of a massive
runs involving analysis of a broader parameter-space.
"""
from numpy import arange


def parameter_range(data_df, index, column, lim_lo=None, lim_up=None,
                    step=None, zero_root=None):
    """Yield values of the parameter in a given range

    Parameters
    ----------
    data_df : DataFrame
        Original data frame, where the target parameter can be found.
    index : valid pandas DataFrame row label
        DataFrame .loc parameter to locate the parameter value.
        E.g.: ['Gas power plant', 'CO2', 'Out'] or 'Gas'
    column : str
        Label of the column, where the parameter is.
        E.g.: 'ratio' or 'cap-max'
    lim_lo : None, optional
        Proportional parameter. If omitted, 90% of the original.
    lim_up : None, optional
        Proportional parameter. If omitted 110% of the original.
    step : None, optional
        Proportional parameter. The difference between
        two following yielded values.
    zero_root : None, optional
        If the selected parameter is 0, then the default method using
        proportions will fail.
        Use this value to set the root for the parameter range.

    Yields
    ------
    DataFrame
        A modified version of xls[df_name]

    Example
    --------
    ::

        data = read_excel(data_spreadsheet)
        interesting_parameters = [
            {'df_name': 'commodity',
             'args': {'index': 'Heat',
                      'column': 'cost-inv-fix',
                      'lim_lo': 0.5, 'lim_up': 1.6, 'step': 0.5}},
            {'df_name': 'commodity',
             'args': {'index': 'Heat',
                      'column': 'cost-fix',
                      'lim_lo': 0.5, 'lim_up': 1.6, 'step': 0.5}}]
        for param in interesting_parameters :
            sheet = data[param['df_name']]
            param_path = param['args']
            for variant in parameter_range(sheet, **param_path):
                ...
    """
    df = data_df.copy()  # Leave the original untouched
    is_multi = len(df.index.names) > 1
    if is_multi:
        original = df.loc[tuple(index)][column]
    else:
        original = df.loc[index][column]

    if original == 0 and zero_root is not None:
        original = zero_root
        # TODO Add warning if needed.
        print('Parameter range is derived from zero_root: {}'
              .format(zero_root))
    elif original == 0 and zero_root is None:
        # TODO Add warning if needed.
        print('Parameter range is just the original parameter (0)!')
        return df

    LO_PROP = 0.9
    UP_PROP = 1.1
    STEP_PROP = 0.05
    lim_lo = LO_PROP * original if lim_lo is None else lim_lo * original
    lim_up = UP_PROP * original if lim_up is None else lim_up * original
    step = STEP_PROP * original if step is None else step * original
    if step == 0:
        step = None
    print('\n> Parameter {} was: {} now changing from {} to {} by {}'.
          format(column, original, lim_lo, lim_up, step))
    for mod in arange(lim_lo, lim_up, step):
        if is_multi:
            df.loc[tuple(index)][column] = mod
        else:
            df.loc[index, column] = mod
        yield df


def char_plot(vertex, just_return=False, show_vertex_ids=False):
    """Plot vertices of a square grid to stdout.
    O: where no sources
    E,G,H... :  First letter of the commodity what is in the source.

    Parameters
    ----------
    vertex : GeoDataFrame
        As returned by ``create_model()``.
    just_return : Boolean
        Plot and return None or do not plot but return a string.
    show_vertex_ids : Boolean
        Show ``O`` or verex id for vertices which are not sources.
    """
    from math import sqrt
    vertex = vertex.copy()
    del vertex['geometry']
    # FIXME: handle multiple commodities with same letter
    vertex.rename(columns=(lambda x: x[0].upper()), inplace=True)
    square_side = sqrt(len(vertex))

    txts = []

    def extract_signs(vert):
        letters = ''.join([com for com, cap in vert.iteritems() if cap > 0])
        txts.append(letters)

    vertex.apply(extract_signs, axis=1)
    char_plot = ''
    is_newline = False
    curr_row = []
    for ix, txt in enumerate(txts):
        is_newline = True if (ix % square_side) == 0 else False
        if is_newline:
            char_plot = '\t'.join(curr_row) + '\n' + char_plot
            curr_row = []
        if txt is '':
            if show_vertex_ids:
                curr_row += [str(ix)]
            else:
                curr_row += ['O']
        else:
            curr_row += [txt]
    else:
        char_plot = '\t'.join(curr_row) + '\n' + char_plot

    if just_return:
        return char_plot
    print(char_plot)
