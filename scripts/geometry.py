import math
import json

import shapely
from shapely.errors import GEOSException


ANGULAR_TOLERANCE = 5e-7
ELEVATION_TOLERANCE = 1e-6


def close(a: float, b: float, axis: int) -> bool:
    tolerance = ELEVATION_TOLERANCE if axis == 2 else ANGULAR_TOLERANCE
    return math.isclose(a, b, rel_tol=0, abs_tol=tolerance)


def number(value) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def check_geometry(item: dict) -> list[str]:
    geometry = item.get("geometry")
    if geometry is None:
        return []
    errors = []
    try:
        shape = shapely.from_geojson(json.dumps(geometry, allow_nan=False))
    except (GEOSException, ValueError, TypeError, OverflowError) as error:
        return [f"geometry: {error}"]
    dimension = int(shapely.get_coordinate_dimension(shape))
    positions = shapely.get_coordinates(shape, include_z=dimension == 3)
    for i, point in enumerate(positions):
        if not all(number(v) for v in point):
            errors.append(
                f"geometry: position {i} contains nonfinite values or mixed 2D and 3D coordinates"
            )
            continue
        lon, lat = point[:2]
        if not -180 <= lon <= 180:
            errors.append(
                f"geometry: position {i} longitude {lon} is outside [-180, 180]"
            )
        if not -90 <= lat <= 90:
            errors.append(f"geometry: position {i} latitude {lat} is outside [-90, 90]")
    if errors:
        return errors
    bbox = item.get("bbox")
    if bbox is None:
        return []
    if len(positions) == 0:
        return ["bbox: can't establish bounds for an empty geometry"]
    if not isinstance(bbox, list) or len(bbox) != 2 * dimension:
        return [f"bbox: expected {2 * dimension} values for {dimension}D geometry"]
    if not all(number(v) for v in bbox):
        return ["bbox: values must be finite numbers"]
    if not all(-180 <= bbox[i] <= 180 for i in (0, dimension)):
        return ["bbox: longitude is outside [-180, 180]"]
    if not all(-90 <= bbox[i] <= 90 for i in (1, dimension + 1)):
        return ["bbox: latitude is outside [-90, 90]"]

    west_bound, south, east_bound, north = shapely.bounds(shape)
    lower, upper = [west_bound, south], [east_bound, north]
    if dimension == 3:
        lower.append(min(positions[:, 2]))
        upper.append(max(positions[:, 2]))
    for axis in range(1, dimension):
        if (
            bbox[axis] > bbox[dimension + axis]
            or not close(bbox[axis], lower[axis], axis)
            or not close(bbox[dimension + axis], upper[axis], axis)
        ):
            errors.append(
                f"bbox: axis {axis} bounds [{bbox[axis]}, {bbox[dimension + axis]}] "
                f"don't match geometry bounds [{lower[axis]}, {upper[axis]}]"
            )

    west, east = bbox[0], bbox[dimension]
    if west <= east:
        if not close(west, lower[0], 0) or not close(east, upper[0], 0):
            errors.append(
                f"bbox: longitude bounds [{west}, {east}] don't match "
                f"geometry bounds [{lower[0]}, {upper[0]}]"
            )
    else:
        pending = [shape]
        intervals = []
        while pending:
            part = pending.pop()
            if (
                part.geom_type.startswith("Multi")
                or part.geom_type == "GeometryCollection"
            ):
                pending.extend(shapely.get_parts(part))
            elif not part.is_empty:
                bounds = shapely.bounds(part)
                intervals.append((bounds[0], bounds[2]))
        # A wrapped bbox must contain each complete component, not just its vertices.
        contained = all(
            start >= west - ANGULAR_TOLERANCE or end <= east + ANGULAR_TOLERANCE
            for start, end in intervals
        )
        starts = [start for start, _ in intervals if start >= west - ANGULAR_TOLERANCE]
        ends = [end for _, end in intervals if end <= east + ANGULAR_TOLERANCE]
        if (
            not contained
            or not starts
            or not ends
            or not close(west, min(starts), 0)
            or not close(east, max(ends), 0)
        ):
            errors.append(
                f"bbox: antimeridian bounds [{west}, {east}] don't match "
                "the geometry's component bounds"
            )
    return errors
