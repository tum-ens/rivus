import numpy as np
from itertools import product as iter_product
from shapely.geometry import Point, LineString
from geopandas import GeoDataFrame
from math import ceil
from geopy.distance import distance
from geopy import Point as gPoint
from pyproj import Proj


def _gen_grid_edges(point_matrix):
    '''Connecting vertices in a chessboard manner
    1  2  3     1--2--3       1--2--3
    4  5  6  -> 4--5--6   ->  |  |  |
    7  8  9     7--8--9       4--5--6
                              |  |  |
                              7--8--9
    '''
    lines = []
    for row in point_matrix:
        lines.extend([LineString(coords) for coords in zip(row[:-1], row[1:])])
    for row in np.transpose(point_matrix, (1, 0, 2)):
        lines.extend([LineString(coords) for coords in zip(row[:-1], row[1:])])

    return lines


def _check_input(origo_latlon, num_edge_x, num_edge_y, dx, dy, noise_prop):
    if len(origo_latlon) != 2 or not all([isinstance(c, (int, float))
                                          for c in origo_latlon]):
        raise TypeError('Origo_latlon has nan element(s)')
    if all([a < 1 for a in (num_edge_x, num_edge_y)]):
        raise ValueError('Both of the edge dimensions cannot be <1.')
    if any([a < 0 for a in (dx, dy, noise_prop)]):
        raise ValueError('dx, dy, noise_prop must be positive numbers.')


def create_square_grid(origo_latlon=(48.26739, 11.66842), num_edge_x=1,
                       num_edge_y=None, dx=100, dy=None, noise_prop=0.0,
                       epsg=None, match=0):
    ''' Create chessboard grid with edges and vertices
        on WGS84 suface with vincenty distance calculation
        lat ~ x, lon ~ y

        Parameters
        ----------
        origo_latlon : tuple, optional
            WGS84 latlon coordinates of the bottom left grid point
            defaults to some the TUM-ENS dep. ;]
        num_edge_x : int, optional
            how many edges horizontally
        num_edge_y : None, optional
            How many edgey vertically
        dx : int, optional
            length of the horizontal edges (in meters)
        dy : None, optional
            length of the vertical edges (in meters)
        noise_prop : float, optional
            0.0 to MAX_NOISE < 1.0 effectively a relative missplacement radius
        epsg : int, optional
            If a valid epsg code which is supported py pyproy,
            the coordinates are calculated in the carthesian UTM CRS
            and then transformed into epsg4326 (latlon).
            If `None` or omitted, then the coordinates are calculated
            directly in epsg4326 with vincenty's formula for distance
            and the grid lines up with the North and East directions
        match : enumerated values, optional
            0 : vertices and edges are matched by the logic of generation
                (faster as less calculation is needed.)
            1 : matching is done geographicaly
                with pandashp helper (slower, but flexible)

        Return : [vertices, edges] As GeoDataFrames
            vertices : [geometry, Vertex]
            edges : [geometry, Edge, Vertex1, Vertex2]

        Indexing:
            (6)══04══(7)══05══(8)
             ║        ║        ║
             7        9        11
             ║        ║        ║
            (3)══02══(4)══03══(4)
             ║        ║        ║
             6        8        10
             ║        ║        ║
            (0)══00══(1)══01══(2)
    '''
    # INIT
    # ---- Grid structure
    lat, lon = origo_latlon
    dy = dx if not dy else dy
    num_edge_y = num_edge_x if not num_edge_y else num_edge_y
    num_vert_x = num_edge_x + 1
    num_vert_y = num_edge_y + 1
    match = 0 if match not in [0, 1] else match
    # ---- Noise
    MAX_NOISE = 0.45  # relative to dx dy
    fuzz_radius_x = dx * noise_prop
    fuzz_radius_y = dy * noise_prop
    if noise_prop > MAX_NOISE:
        fuzz_radius_x = MAX_NOISE * dx
        fuzz_radius_y = MAX_NOISE * dy

    _check_input(origo_latlon, num_edge_x, num_edge_y, dx, dy, noise_prop)

    # Generate offset point coordinates
    if epsg is None:  # in  LatLon system
        # getting new points based on https://stackoverflow.com/a/24429798
        # Convert to geopy distance
        crsinit = {'init': 'epsg:4326'}
        dx = distance(meters=dx)
        dy = distance(meters=dy)
        points = []
        startp = gPoint([lat, lon])
        # create the grid coordinates
        for _ in range(num_vert_y):
            points.append([startp.longitude, startp.latitude])
            _startp = startp
            for _ in range(num_edge_x):
                _startp = dx.destination(point=_startp, bearing=90)
                points.append([_startp.longitude, _startp.latitude])
            startp = dy.destination(point=startp, bearing=0)
    else:  # in UTM XY coord system
        try:
            UTMXX = Proj(init='epsg:{}'.format(epsg))
            crsinit = {'init': 'epsg:{}'.format(epsg)}  # for GeoDataFrame
        except:
            raise ValueError('Not supported epsg number, \
                only Proj4 init epsg numbers are supported')
        ox, oy = UTMXX(lon, lat)
        coords_x = np.arange(ox, ox + (dx * num_vert_x), dx)
        coords_y = np.arange(oy, oy + (dy * num_vert_y), dy)
        points = [(x, y) for y, x in iter_product(coords_y, coords_x,
                                                  repeat=1)]

    # Add fuzz
    if noise_prop > 0.0:
        def _fuzz(xy):
            if epsg is not None:
                return [xy[ii] + lim * (2 * np.random.rand() - 1)
                        for ii, lim in enumerate((fuzz_radius_x,
                                                  fuzz_radius_y))]
            else:
                lon, lat = xy
                fromP = gPoint([lat, lon])
                londist = distance(meters=(fuzz_radius_x * np.random.rand()))
                latdist = distance(meters=(fuzz_radius_y * np.random.rand()))
                newX = latdist.destination(point=fromP, bearing=0)
                newY = londist.destination(point=fromP, bearing=90)
                return [newX.longitude, newY.latitude]
        points = list(map(lambda xy: _fuzz(xy), points))

    # Create Shapely objects
    vertices = [Point(coo) for coo in points]
    # reshape(num_rows, num_cols) --> num_vert_y is the number of rows.
    # As it counts the elements in a column along the y axis.
    point_matrix = np.array(points).reshape(num_vert_y, num_vert_x, 2)
    edges = _gen_grid_edges(point_matrix)

    # Create GeoDataFrames
    vdf = GeoDataFrame(geometry=vertices, crs=crsinit)
    vdf['Vertex'] = vdf.index  # ; vdf.set_index('Vertex', inplace=True)
    edf = GeoDataFrame(geometry=edges, crs=crsinit)
    edf['Edge'] = edf.index  # ; edf.set_index('Edge', inplace=True)

    # Match Vertex1 and Vertex2 columns to Vertex index
    if match == 1:
        from ..utils import pandashp as pdshp  # to match vertices and edges
        pdshp.match_vertices_and_edges(vdf, edf)
    elif match == 0:
        v1s = []
        v2s = []
        indices = np.arange(
            num_vert_x * num_vert_y).reshape(num_vert_y, num_vert_x)
        for row in indices:
            v1s.extend(row[:-1])
            v2s.extend(row[1:])
        for col in indices.T:
            v1s.extend(col[:-1])
            v2s.extend(col[1:])
        edf['Vertex1'] = v1s
        edf['Vertex2'] = v2s

    if epsg is not None:
        vdf.to_crs(epsg=4326, inplace=True)
        edf.to_crs(epsg=4326, inplace=True)

    return (vdf, edf)


def get_source_candidates(vdf, dim_x, dim_y, logic='sym'):
    """Calculate the set of indexes of the vertices, which are worth testing
    as source vertex in a single commodity case. A square grid is assumed.
    "Worth" means:
    The minimal set of vertices which cover the main symmetrical positions.

    Parameters
    ----------
    vdf : pandas DataFrame
        The vertex frame. (Created by create_square_grid())
    dim_x : int
        Number of vertices along the x axis.
    dim_y : int
        Number of vertices along the y axis.
    logic : str, optional default='sym'
        what kind or source candidates are looked for.
        sym : Minimal(ish) set of vertices based on symmetry.
        extrema: Pairs of vertices possibly further away from each other.

    Returns
    -------
    List
        smy : 1D list
        extrema : 2D list - list of lists
    """
    mat = vdf.index.values.reshape(dim_y, dim_x)

    if logic == 'sym':
        lim_x = ceil(dim_x / 2)
        lim_y = ceil(dim_y / 2)
        return mat[0:lim_y, 0:lim_x].flatten().tolist()
    elif logic == 'extrema':
        corners = [(0, 0), (0, dim_x - 1), (dim_y - 1, 0),
                   (dim_y - 1, dim_x - 1)]
        borders = [[corners[0], corners[3]], [corners[0], corners[1]],
                   [corners[0], corners[2]]]
        return borders
    else:
        raise ValueError('Unsupported source vertex calculation logic: <{}>'
                         .format(logic))


# Run Examples / Tests if script is executed directly
if __name__ == '__main__':
    import matplotlib.pyplot as plt
    test0ver, test0edg = create_square_grid(
        num_edge_x=3, num_edge_y=2, noise_prop=0.0, epsg=32632)
    # test1ver, test1edg = create_square_grid(num_edge_x=6, noise_prop=0.1, epsg=32632)
    # test2ver, test2edg = create_square_grid(num_edge_x=6, noise_prop=0.2)
    # test3ver, test3edg = create_square_grid(num_edge_x=6, noise_prop=0.3)
    # test4ver, test4edg = create_square_grid(num_edge_x=6, noise_prop=0.4)
    # test5ver, test5edg = create_square_grid(num_edge_x=6, noise_prop=.45)

    fig, axes = plt.subplots(2, 3, figsize=(10, 6))
    for ij in iter_product(range(2), repeat=2):
        axes[ij].set_aspect('equal')
    test0ver.plot(ax=axes[0, 0], marker='o', color='red', markersize=5)
    test0edg.plot(ax=axes[0, 0], color='blue')
    # test1ver.plot(ax=axes[0, 1], marker='o', color='red', markersize=5)
    # test1edg.plot(ax=axes[0, 1], color='blue')
    # test2ver.plot(ax=axes[0, 2], marker='o', color='red', markersize=5)
    # test2edg.plot(ax=axes[0, 2], color='blue')
    # test3ver.plot(ax=axes[1, 0], marker='o', color='red', markersize=5)
    # test3edg.plot(ax=axes[1, 0], color='blue')
    # test4ver.plot(ax=axes[1, 1], marker='o', color='red', markersize=5)
    # test4edg.plot(ax=axes[1, 1], color='blue')
    # test5ver.plot(ax=axes[1, 2], marker='o', color='red', markersize=5)
    # test5edg.plot(ax=axes[1, 2], color='blue')
