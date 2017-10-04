import unittest
# For line length test
from rivus.main.rivus import line_length
from shapely.geometry import LineString


class RivusMainTest(unittest.TestCase):

    # TODO There is plenty of more functions (if not all)
    # which reside in the code-base untested. Bellow some placeholders.

    def test_line_length(self):
        # known LineStrings with length and LonLat(x-y) coordinates
        lines = (LineString(((11.6625881, 48.2680606),
                             (11.6527176, 48.2493919),
                             (11.6424179, 48.2366107),
                             (11.6235352, 48.1952043),
                             (11.608429, 48.184218),
                             (11.5871429, 48.1647573),
                             (11.5795898, 48.1455182))),
                 LineString(((11.5795898, 48.1455182),
                             (11.6142654, 48.1379581),
                             (11.6630173, 48.1391036),
                             (11.6781235, 48.1372707),
                             (11.6963196, 48.142311),
                             (11.7581177, 48.1432274))),
                 LineString(((11.5710926, 48.1596505),
                             (11.5704918, 48.1586199),
                             (11.5718651, 48.1582764))),
                 LineString(((11.571908, 48.1490288),
                             (11.5755129, 48.1544401))))
        lens = [15181, 13553, 232, 659]

        for line, length in zip(lines, lens):
            calculated = round(line_length(line), 0)
            self.assertTrue(calculated == length,
                            msg=('Calculated line length is invalid. {}<>{}'
                                 .format(calculated, length)))

    def test_source_calculation(self):
        pass

    def test_pair_vertex_to_edge(self):
        pass

    def test_save_load(self):
        pass

    def test_read_excel(self):
        pass
