import unittest
import os
pdir = os.path.dirname
from rivus.utils.notify import email_me
from rivus.utils.runmany import parameter_range
from rivus.main.rivus import read_excel
import json


class RivusTest(unittest.TestCase):

    def test_parameter_range(self):
        proj_name = 'mnl'
        base_directory = os.path.join('data', proj_name)
        data_spreadsheet = os.path.join(base_directory, 'data.xlsx')
        data = read_excel(data_spreadsheet)
        data_bup = data.copy()
        which_sheet = 'commodity'
        selected_df = data[which_sheet]
        index = 'Heat',
        column = 'cost-inv-fix'
        lims = dict(lim_lo=0.5, lim_up=1.5, step=0.25)
        the_param = selected_df.loc[index][column]
        awaited_number = (lims['lim_up'] - lims['lim_lo']) // lims['step']
        if the_param == 0:
            awaited_number = 0
        got_parameters = []
        for df in parameter_range(selected_df, index, column, **lims):
            got_parameters.append(df.loc[index][column])

        self.assertTrue(len(got_parameters) == awaited_number,
                        msg='got {} instead of awaited {}'
                            .format(len(got_parameters), awaited_number))

        self.assertTrue(all(data_bup[which_sheet].loc[index].fillna(0) ==
                            data[which_sheet].loc[index].fillna(0)),
                        msg='Func changed original row.')

        if the_param != 0:
            self.assertTrue(max(got_parameters) < lims['lim_up'] * the_param,
                            msg='Got parameter bigger than awaited.')

            self.assertTrue(min(got_parameters) >= lims['lim_lo'] * the_param,
                            msg='Got parameter smaller than awaited.')

    def test_email_notification(self):
        # Concatenate the absolute path to the config file.
        # conf_path = __file__[:-len('rivus/tests/utils.py')] + 'config.json'
        conf_path = os.path.join(pdir(pdir(pdir(__file__))), 'config.json')
        config = []
        with open(conf_path) as conf:
            config = json.load(conf)
        email_setup = {
            'sender': config['email']['s_user'],
            'send_pass': config['email']['s_pass'],
            'recipient': config['email']['r_user'],
            'smtp_addr': config['email']['smtp_addr'],
            'smtp_port': config['email']['smtp_port']
        }

        sub = 'Testing from unittest [rivus][test]'
        msg = ('rivus is a mixed integer linear programming model '
               'for multi-commodity energy infrastructure networks systems '
               'with a focus on high spatial resolution.\n'
               'It finds the minimum cost energy infrastructure networks to '
               'satisfy a given energy distribution for '
               'possibly multiple commodities '
               '(e.g. electricity, heating, cooling, ...).')
        self.assertEqual(email_me(msg, subject=sub, **email_setup), 0,
                         msg='Something went wrong during email notification.')
