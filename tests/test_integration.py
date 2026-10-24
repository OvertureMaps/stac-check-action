import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from test_runner import catalog, item, validator


@unittest.skipUnless(
    os.environ.get("RUN_INTEGRATION") == "1",
    "Set RUN_INTEGRATION=1 for real rustac tests",
)
class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        work = self.root / "work"
        work.mkdir()
        self.runner = validator.Runner(
            {
                "IN_FILE": str(self.root / "catalog.json"),
                "IN_RECURSIVE": "true",
                "IN_STREAM_OUTPUT": "false",
            },
            work,
        )
        self.capture = contextlib.redirect_stdout(io.StringIO())
        self.capture.__enter__()
        self.addCleanup(self.capture.__exit__, None, None, None)

    def write(self, path, value):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value), encoding="utf-8")

    def test_large_catalog_local_absolute_links_and_repeated_ids(self):
        self.write(
            "catalog.json",
            catalog(
                [
                    {"rel": "self", "href": "https://offline.invalid/catalog.json"},
                    {
                        "rel": "child",
                        "href": "https://offline.invalid/c/collection.json",
                    },
                ]
            ),
        )
        self.write(
            "c/collection.json",
            catalog(
                [
                    {"rel": "item", "href": f"https://offline.invalid/c/{i}.json"}
                    for i in range(3500)
                ],
                "Collection",
            ),
        )
        for i in range(3500):
            self.write(f"c/{i}.json", item("repeated"))
        self.runner.run()
        report = self.runner.finish()
        self.assertTrue(report["valid"], report["errors"])
        self.assertEqual(report["items"], 3500)
        self.assertEqual(report["cli_calls"], 3)
        self.assertEqual(report["skipped_remote"], 0)

    def test_parse_and_schema_errors_keep_source_filenames(self):
        self.write(
            "catalog.json",
            catalog([{"rel": "item", "href": f"{i}.json"} for i in range(4)]),
        )
        for i in range(4):
            doc = item("same")
            if i == 1:
                doc["properties"]["datetime"] = "not-a-date"
            if i == 2:
                doc["bbox"] = [0, 0]
            self.write(f"{i}.json", doc)
        self.runner.run()
        report = self.runner.finish()
        self.assertFalse(report["valid"])
        self.assertEqual(
            {Path(f["file"]).name for f in report["errors"]}, {"1.json", "2.json"}
        )

    def test_extension_schema_rejection(self):
        doc = item()
        doc["stac_extensions"] = [
            "https://stac-extensions.github.io/file/v2.1.0/schema.json"
        ]
        doc["assets"] = {
            "data": {"href": "data.parquet", "file:size": "not-an-integer"}
        }
        self.write("catalog.json", doc)
        self.runner.run()
        self.assertTrue(self.runner.failures)
        self.assertIn("<instance>", self.runner.failures[0].message)

    def test_spatial_errors_in_report_and_summary(self):
        self.write(
            "catalog.json",
            catalog(
                [
                    {"rel": "item", "href": "range.json"},
                    {"rel": "item", "href": "bounds.json"},
                ]
            ),
        )
        out_of_range = item("range")
        out_of_range["geometry"]["coordinates"] = [0, 95]
        out_of_range["bbox"] = [0, 95, 0, 95]
        mismatch = item("bounds")
        mismatch["bbox"] = [-1, -1, 1, 1]
        self.write("range.json", out_of_range)
        self.write("bounds.json", mismatch)
        self.runner.run()
        report = self.runner.finish()
        self.assertFalse(report["valid"])
        failures = report["errors"]
        self.assertTrue(
            any(
                "latitude" in f["message"] and f["file"].endswith("range.json")
                for f in failures
            )
        )
        self.assertTrue(
            any(
                "don't match" in f["message"] and f["file"].endswith("bounds.json")
                for f in failures
            )
        )
        self.assertIn("geometry/bbox consistency", self.runner.summary.read_text())
