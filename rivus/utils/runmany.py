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

    Returns
    -------
    DataFrame
        A modified version of xls[df_name]
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
