from shapely.geometry import (box, LineString, MultiLineString, MultiPoint,
                              Point, Polygon)
import shapely.ops


def endpoints_from_lines(lines):
    """Return list of terminal points from list of LineStrings.
    Where in case of common end points, no duplicate is generated.

    Parameters
    ----------
    lines : list(LineStrings)

    Returns
    -------
    list of Shapely.Point
    """

    all_points = []
    for line in lines:
        for i in [0, -1]:  # start and end point
            all_points.append(line.coords[i])

    unique_points = set(all_points)

    return [Point(p) for p in unique_points]


def vertices_from_lines(lines):
    """Return list of unique vertices from list of LineStrings.

    Parameters
    ----------
    lines : list(LineStrings)

    Returns
    -------
    list of Shapely.Point
    """

    vertices = []
    for line in lines:
        vertices.extend(list(line.coords))
    return [Point(p) for p in set(vertices)]


def snapping_vertices_from_lines(lines, closeness_limit):
    """" Return a list of edge endpoints, where close, but not identical
         points are unified

    Note
    -----
    When working with projected coordinates, the unit of closeness_limit is meters.
    But do not forget, that the majority of functions in rivus returns
    data in WGS84 as CRS. (LatLon, not projected coordinates.)
    In this case, the unit of closeness_limit is a good question. But the meaning
    of meters would be well beyond the decimal point.

    Suggestion: use projected crs for this calculation.

    Parameters
    ----------
    lines
        list of LineStrings
    closeness_limit
        critical distance for selecting unique vertices.
        From which vertices will be united with their neighbours in their proximity.

    Returns
    -------
    TYPE
        Description
    """
    uni_verts = []
    for line in lines:
        for end in line.coords:
            if len(uni_verts):
                inter = (Point(end).buffer(closeness_limit)
                         .intersection(MultiPoint(uni_verts)))
                if inter.type != 'Point':
                    uni_verts.append(end)
            else:
                uni_verts.append(end)
    return [Point(p) for p in uni_verts]


def prune_short_lines(lines, min_length):
    """Remove lines from a LineString DataFrame shorter than min_length.

    Deletes all lines from a list of LineStrings or a MultiLineString
    that have a total length of less than min_length. Vertices of touching
    lines are contracted towards the centroid of the removed line.

    Parameters
    ----------
    lines
        list of LineStrings or a MultiLineString
    min_length
        minimum length of a single LineString to be preserved

    Returns
    -------
    list
        including not pruned lines
    """
    pruned_lines = [line for line in lines]  # converts MultiLineString to list
    to_prune = []

    for i, line in enumerate(pruned_lines):
        if line.length < min_length:
            to_prune.append(i)
            for n in neighbors(pruned_lines, line):
                contact_point = line.intersection(pruned_lines[n])
                pruned_lines[n] = bend_towards(pruned_lines[n],
                                               where=contact_point,
                                               to=line.centroid)

    return [line for i, line in enumerate(pruned_lines) if i not in to_prune]


def neighbors(lines, of):
    """Find the indices in a list of LineStrings that touch a given LineString.

    Parameters
    ----------
    lines
        list of LineStrings in which to search for neighbours
    of
        the LineString which must be touched

    Returns
    -------
    list of indices, so that all lines[indices] touch the LineString of
    """
    return [k for k, line in enumerate(lines) if line.touches(of)]


def bend_towards(line, where, to):
    """Move the point ``where`` on the ``line`` to the point ``to``.

    Parameters
    ----------
    line : Shapely.LineString
        a LineString
    where : Shapely.Point
        a point ON the line (not necessarily a vertex)
    to : Shapely.Point
        a point NOT on the line where the nearest vertex will be moved to

    Returns
    -------
    LineString
        the modified (bent) line.

    Raises
    ------
    ValueError
        ``line`` does not contain the point ``where``.
    """

    if not line.contains(where) and not line.touches(where):
        raise ValueError('line does not contain the point where.')

    coords = line.coords[:]
    # easy case: ``where`` is (within numeric precision) a vertex of line
    for k, vertex in enumerate(coords):
        if where.almost_equals(Point(vertex)):
            # move coordinates of the vertex to destination
            coords[k] = to.coords[0]
            return LineString(coords)

    # hard case: ``where`` lies between vertices of line, so
    # find nearest vertex and move that one to point to
    _, min_k = min((where.distance(Point(vertex)), k)
                   for k, vertex in enumerate(coords))
    coords[min_k] = to.coords[0]
    return LineString(coords)


def snappy_endings(lines, max_distance):
    """Snap endpoints of lines together if they are at most max_length apart.

    Parameters
    ----------
    lines
        a list of LineStrings or a MultiLineString
    max_distance
        maximum distance two endpoints may be joined together 

    Returns
    -------
    list(LineString)
        snapped lines
    """

    # initialize snapped lines with list of original lines
    # snapping points is a MultiPoint object of all vertices
    snapped_lines = [line for line in lines]
    # If the ends of lines truly meet at an intersection
    snapping_points = vertices_from_lines(snapped_lines)
    # If the ends of (self drawn) lines may not snap together perfectly
    # snapping_points = snapping_vertices_from_lines(snapped_lines, max_distance)

    # isolated endpoints are going to snap to the closest vertex
    isolated_endpoints = find_isolated_endpoints(snapped_lines)

    # only move isolated endpoints, one by one
    for endpoint in isolated_endpoints:
        # find all vertices within a radius of max_distance as possible
        target = nearest_neighbor_within(snapping_points, endpoint,
                                         max_distance)

        # do nothing if no target point to snap to is found
        if not target:
            continue

        # find the LineString to modify within snapped_lines and update it
        for i, snapped_line in enumerate(snapped_lines):
            if endpoint.touches(snapped_line):
                snapped_lines[i] = bend_towards(snapped_line, where=endpoint,
                                                to=target)
                break

        # also update the corresponding snapping_points
        for i, snapping_point in enumerate(snapping_points):
            if endpoint.equals(snapping_point):
                snapping_points[i] = target
                break

    # post-processing: remove any resulting lines of length 0
    snapped_lines = [s for s in snapped_lines if s.length > 0]

    return snapped_lines


def nearest_neighbor_within(others, point, max_distance):
    """Find nearest point among others up to a maximum distance.

    Parameters
    ----------
    others
        a list of Points or a MultiPoint
    point
        a Point
    max_distance
        maximum distance to search for the nearest neighbour

    Returns
    -------
    Shapely.Point
        A shapely Point if one is within max_distance, None otherwise
    """
    search_region = point.buffer(max_distance)
    interesting_points = search_region.intersection(MultiPoint(others))

    if not interesting_points:
        closest_point = None
    elif isinstance(interesting_points, Point):
        closest_point = interesting_points
    else:
        distances = [point.distance(ip) for ip in interesting_points
                     if point.distance(ip) > 0]
        closest_point = interesting_points[distances.index(min(distances))]

    return closest_point


def find_isolated_endpoints(lines):
    """Find endpoints of lines that don't touch another line.

    Parameters
    ----------
    lines
        a list of LineStrings or a MultiLineString

    Returns
    -------
    A list of line end Points that don't touch any other line of lines
    """

    isolated_endpoints = []
    for i, line in enumerate(lines):
        other_lines = lines[:i] + lines[i+1:]
        for q in [0, -1]:
            endpoint = Point(line.coords[q])
            if any(endpoint.touches(another_line)
                   for another_line in other_lines):
                continue
            else:
                isolated_endpoints.append(endpoint)
    return isolated_endpoints


def closest_object(geometries, point):
    """Find the nearest geometry among a list, measured from fixed point.

    Parameters
    ----------
    geometries
        a list of shapely geometry objects
    point
        a shapely Point

    Returns
    -------
    Tuple (geom, min_dist, min_index) of the geometry with minimum distance
    to point, its distance min_dist and the list index of geom, so that
    geom = geometries[min_index].
    """
    min_dist, min_index = min((point.distance(geom), k)
                              for (k, geom) in enumerate(geometries))

    return geometries[min_index], min_dist, min_index


def project_point_to_line(point, line_start, line_end):
    """Find nearest point on a straight line, measured from given point.

    Parameters
    ----------
    point
        a shapely Point object
    line_start
        the line starting point as a shapely Point
    line_end
        the line end point as a shapely Point

    Returns
    -------
    Shapely.Point
        The projected point

    References
    -----------
        `Source <http://gis.stackexchange.com/a/438/19627>`_
    """
    line_magnitude = line_start.distance(line_end)

    u = ((point.x - line_start.x) * (line_end.x - line_start.x) +
         (point.y - line_start.y) * (line_end.y - line_start.y)) \
        / (line_magnitude ** 2)

    # closest point does not fall within the line segment,
    # take the shorter distance to an endpoint
    if u < 0.00001 or u > 1:
        ix = point.distance(line_start)
        iy = point.distance(line_end)
        if ix > iy:
            return line_end
        else:
            return line_start
    else:
        ix = line_start.x + u * (line_end.x - line_start.x)
        iy = line_start.y + u * (line_end.y - line_start.y)
        return Point([ix, iy])


def pairs(a_list):
    """Iterate over a list in overlapping pairs.

    Parameters
    ----------
    a_list
        an iterable/list

    Example
    -------
    a_list = [4, 7, 11, 2]
    pairs(a_list) yields (4, 7), (7, 11), (11, 2)

    References
    -----------
    `Source <http://stackoverflow.com/questions/1257413/1257446#1257446>`_

    Yields
    ------
    Yields a pair of consecutive elements (a_list[k], a_list[k+1]) of a_list.
    Last call yields (a_list[-2], a_list[-1]).
    """
    i = iter(a_list)
    prev = next(i)
    for item in i:
        yield prev, item
        prev = item


def project_point_to_object(point, geometry):
    """Find nearest point in geometry, measured from given point.

    Parameters
    ----------
    point
        a shapely Point
    geometry
        a shapely geometry object (LineString, Polygon)

    Returns
    -------
    Shapely.Point
        that lies on geometry closest to point

    Raises
    ------
    NotImplementedError
        project_point_to_object not implemented for geometry type
    """
    nearest_point = None
    min_dist = float("inf")

    if isinstance(geometry, Polygon):
        for seg_start, seg_end in pairs(list(geometry.exterior.coords)):
            line_start = Point(seg_start)
            line_end = Point(seg_end)

            intersection_point = project_point_to_line(point, line_start, line_end)
            cur_dist = point.distance(intersection_point)

            if cur_dist < min_dist:
                min_dist = cur_dist
                nearest_point = intersection_point

    elif isinstance(geometry, LineString):
        for seg_start, seg_end in pairs(list(geometry.coords)):
            line_start = Point(seg_start)
            line_end = Point(seg_end)

            intersection_point = project_point_to_line(point, line_start, line_end)
            cur_dist = point.distance(intersection_point)

            if cur_dist < min_dist:
                min_dist = cur_dist
                nearest_point = intersection_point
    else:
        raise NotImplementedError("project_point_to_object not implemented for" +
                                  " geometry type '" + geometry.type + "'.")
    return nearest_point


def one_linestring_per_intersection(lines):
    """Move line endpoints to intersections of line segments.

    Given a list of touching or possibly intersecting LineStrings, return a
    list of LineStrings that have their endpoints at all crossings and
    intersecting points and ONLY there.

    Parameters
    ----------
    lines : list(LineString)
        a list of LineStrings or a MultiLineString
        Possible complex collection of line strings.

    Returns
    -------
    list of LineStrings
    """
    lines_merged = shapely.ops.linemerge(lines)

    # intersecting multiline with its bounding box somehow triggers a first
    bounding_box = box(*lines_merged.bounds)

    # perform linemerge (one linestring between each crossing only)
    # if this fails, write function to perform this on a bbox-grid and then
    # merge the result
    lines_merged = lines_merged.intersection(bounding_box)
    lines_merged = shapely.ops.linemerge(lines_merged)
    return lines_merged


def linemerge(linestrings_or_multilinestrings):
    """Merge list of LineStrings and/or MultiLineStrings.

    Given a list of LineStrings and possibly MultiLineStrings, merge all of
    them to a single MultiLineString.

    Parameters
    ----------
    linestrings_or_multilinestrings
        list of LineStrings and/or MultiLineStrings

    Returns
    -------
    a merged LineString or MultiLineString
    """
    lines = []
    for line in linestrings_or_multilinestrings:
        if isinstance(line, MultiLineString):
            # line is a multilinestring, so append its components
            lines.extend(line)
        else:
            # line is a line, so simply append it
            lines.append(line)

    return shapely.ops.linemerge(lines)
