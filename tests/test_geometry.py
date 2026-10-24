import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from geometry import check_geometry, number


def polygon(west, south, east, north, z=None):
    ring = [[west, south], [east, south], [east, north], [west, north], [west, south]]
    if z is not None:
        ring = [p + [z] for p in ring]
    return {"type": "Polygon", "coordinates": [ring]}


class GeometryTests(unittest.TestCase):
    def check(self, geometry, bbox=None):
        return check_geometry({"geometry": geometry, "bbox": bbox})

    def test_null_and_absent_geometry(self):
        self.assertEqual(check_geometry({}), [])
        self.assertEqual(self.check(None), [])

    def test_all_geometry_types(self):
        fixtures = [
            ({"type": "Point", "coordinates": [120, 30]}, [120, 30, 120, 30]),
            ({"type": "MultiPoint", "coordinates": [[0, 0], [2, 3]]}, [0, 0, 2, 3]),
            ({"type": "LineString", "coordinates": [[0, 0], [2, 3]]}, [0, 0, 2, 3]),
            (
                {"type": "MultiLineString", "coordinates": [[[0, 0], [2, 3]]]},
                [0, 0, 2, 3],
            ),
            (polygon(0, 0, 2, 3), [0, 0, 2, 3]),
            (
                {
                    "type": "MultiPolygon",
                    "coordinates": [polygon(0, 0, 2, 3)["coordinates"]],
                },
                [0, 0, 2, 3],
            ),
            (
                {
                    "type": "GeometryCollection",
                    "geometries": [
                        {
                            "type": "GeometryCollection",
                            "geometries": [{"type": "Point", "coordinates": [0, 0]}],
                        },
                        polygon(1, 1, 2, 3),
                    ],
                },
                [0, 0, 2, 3],
            ),
        ]
        for geometry, bbox in fixtures:
            with self.subTest(type=geometry["type"]):
                self.assertEqual(self.check(geometry, bbox), [])
                wrong = bbox.copy()
                wrong[1] -= 1
                self.assertTrue(self.check(geometry, wrong))

    def test_ranges_include_boundaries_and_reject_definite_errors(self):
        for point in [[-180, -90], [180, 90], [120, 30], [-170, -20]]:
            self.assertEqual(self.check({"type": "Point", "coordinates": point}), [])
        for point, label in [
            ([180.00001, 0], "longitude"),
            ([-180.00001, 0], "longitude"),
            ([0, 90.00001], "latitude"),
            ([0, -90.00001], "latitude"),
        ]:
            with self.subTest(point=point):
                errors = self.check(
                    {
                        "type": "GeometryCollection",
                        "geometries": [{"type": "Point", "coordinates": point}],
                    }
                )
                self.assertIn(label, errors[0])

    def test_three_dimensions_and_elevation_bounds(self):
        geometry = {"type": "LineString", "coordinates": [[0, 1, -100], [2, 3, 500]]}
        self.assertEqual(self.check(geometry, [0, 1, -100, 2, 3, 500]), [])
        self.assertTrue(self.check(geometry, [0, 1, -99, 2, 3, 500]))
        self.assertTrue(self.check(geometry, [0, 1, -100, 2, 3, 499]))
        self.assertTrue(self.check(geometry, [0, 1, 2, 3]))
        self.assertEqual(self.check(polygon(0, 0, 1, 1, 10), [0, 0, 10, 1, 1, 10]), [])

    def test_mixed_dimensions_fail_bbox_explicitly(self):
        geometry = {"type": "MultiPoint", "coordinates": [[0, 0], [1, 1, 2]]}
        self.assertIn("mixed", self.check(geometry, [0, 0, 1, 1])[0])

    def test_tolerance_is_absolute_and_axis_specific(self):
        geometry = {"type": "Point", "coordinates": [100, 20, 1000000]}
        self.assertEqual(
            self.check(
                geometry, [100 - 1e-7, 20 - 1e-7, 1000000 - 5e-7, 100, 20, 1000000]
            ),
            [],
        )
        self.assertTrue(
            self.check(geometry, [100 + 1e-6, 20, 1000000, 100, 20, 1000000])
        )
        self.assertTrue(self.check(geometry, [100, 20, 1000000, 100, 20, 1000001]))

    def test_wide_and_world_polygons(self):
        for west, east in [(-180, 180), (-170, 170), (-100, 150)]:
            geometry = polygon(west, -90, east, 90)
            self.assertEqual(self.check(geometry, [west, -90, east, 90]), [])
            self.assertTrue(self.check(geometry, [170, -90, -170, 90]))

    def test_cut_antimeridian_polygon(self):
        geometry = {
            "type": "MultiPolygon",
            "coordinates": [
                polygon(170, -10, 180, 10)["coordinates"],
                polygon(-180, -10, -175, 10)["coordinates"],
            ],
        }
        self.assertEqual(self.check(geometry, [170, -10, -175, 10]), [])
        self.assertEqual(self.check(geometry, [-180, -10, 180, 10]), [])
        for bbox in [
            [169, -10, -175, 10],
            [171, -10, -175, 10],
            [170, -10, -174, 10],
            [170, -10, -176, 10],
            [170, -11, -175, 10],
            [-175, -10, 170, 10],
        ]:
            with self.subTest(bbox=bbox):
                self.assertTrue(self.check(geometry, bbox))

    def test_crossing_lines_and_points(self):
        cut = {
            "type": "MultiLineString",
            "coordinates": [[[170, 0], [180, 1]], [[-180, 1], [-170, 2]]],
        }
        self.assertEqual(self.check(cut, [170, 0, -170, 2]), [])
        uncut = {"type": "LineString", "coordinates": [[170, 0], [-170, 2]]}
        self.assertTrue(self.check(uncut, [170, 0, -170, 2]))
        self.assertEqual(self.check(uncut, [-170, 0, 170, 2]), [])
        points = {"type": "MultiPoint", "coordinates": [[170, 0], [-170, 2]]}
        self.assertEqual(self.check(points, [170, 0, -170, 2]), [])
        self.assertTrue(
            self.check({"type": "Point", "coordinates": [175, 0]}, [170, 0, -170, 0])
        )

    def test_holes_and_elevation_extrema(self):
        geometry = polygon(0, 0, 10, 10, 0)
        geometry["coordinates"].append([[2, 2, -5], [3, 2, 7], [3, 3, 0], [2, 2, -5]])
        self.assertEqual(self.check(geometry, [0, 0, -5, 10, 10, 7]), [])

    def test_parser_failures_become_validation_errors(self):
        fixtures = [
            {"type": "Unknown"},
            {"type": "Point", "coordinates": [0]},
            {"type": "Point", "coordinates": [True, 0]},
        ]
        for value in [float("nan"), float("inf"), 10**400]:
            fixtures.append({"type": "Point", "coordinates": [value, 0]})
        for geometry in fixtures:
            with self.subTest(geometry=geometry):
                self.assertTrue(self.check(geometry)[0].startswith("geometry:"))
        self.assertFalse(number(10**400))

    def test_empty_geometries_have_no_calculable_bbox(self):
        for geometry in [
            {"type": "MultiPoint", "coordinates": []},
            {"type": "Polygon", "coordinates": [[]]},
            {"type": "GeometryCollection", "geometries": []},
        ]:
            self.assertEqual(self.check(geometry), [])
            self.assertTrue(self.check(geometry, [0, 0, 0, 0]))

    def test_empty_component_in_wrapped_collection(self):
        geometry = {
            "type": "GeometryCollection",
            "geometries": [
                {"type": "Point", "coordinates": []},
                {"type": "MultiPoint", "coordinates": [[170, 0], [-170, 1]]},
            ],
        }
        self.assertEqual(self.check(geometry, [170, 0, -170, 1]), [])

    def test_invalid_bbox(self):
        geometry = {"type": "Point", "coordinates": [0, 0]}
        for bbox in [
            [],
            "bad",
            [0, 0, 0],
            [0, 0, float("nan"), 0],
            [False, 0, 0, 0],
            [-181, 0, 0, 0],
            [0, -91, 0, 0],
            [0, 1, 0, -1],
        ]:
            with self.subTest(bbox=bbox):
                self.assertTrue(self.check(geometry, bbox))

    def test_three_dimensional_antimeridian_and_nested_collections(self):
        parts = [
            polygon(170, -10, 180, 10, -5),
            polygon(-180, -5, -170, 5, 20),
        ]
        geometry = {"type": "GeometryCollection", "geometries": parts}
        self.assertEqual(self.check(geometry, [170, -10, -5, -170, 10, 20]), [])
        self.assertTrue(self.check(geometry, [170, -10, -4, -170, 10, 20]))
        self.assertTrue(self.check(geometry, [170, -10, -5, -170, 10, 19]))

    def test_each_bbox_edge_must_match(self):
        geometry = polygon(-12.5, -4.25, 30.75, 62.125)
        bbox = [-12.5, -4.25, 30.75, 62.125]
        self.assertEqual(self.check(geometry, bbox), [])
        for axis in range(4):
            with self.subTest(axis=axis):
                bad = bbox.copy()
                bad[axis] += 0.01
                self.assertTrue(self.check(geometry, bad))


if __name__ == "__main__":
    unittest.main()
