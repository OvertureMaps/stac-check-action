import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
from generate_catalog import catalog, item

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run as validator


def result(code=0, out="", err=""):
    return subprocess.CompletedProcess([], code, out, err)


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.env = {
            "IN_FILE": str(self.root / "catalog.json"),
            "IN_RECURSIVE": "true",
            "IN_STREAM_OUTPUT": "false",
            "GITHUB_OUTPUT": str(self.root / "outputs"),
        }
        self.work = self.root / "work"
        self.work.mkdir()
        self.runner = validator.Runner(self.env, self.work)
        self.capture = io.StringIO()
        self.redirect = contextlib.redirect_stdout(self.capture)
        self.redirect.__enter__()
        self.addCleanup(self.redirect.__exit__, None, None, None)

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def crawl(self, depth=None, recursive=True):
        self.runner.crawl(self.root / "catalog.json", recursive, depth)
        return [doc.path.name for doc in self.runner.documents]

    def tree(self):
        self.write(
            "catalog.json",
            catalog(
                [
                    {"rel": "child", "href": "sub/c.json"},
                    {"rel": "parent", "href": "do-not-read.json"},
                ]
            ),
        )
        self.write(
            "sub/c.json",
            catalog(
                [
                    {"rel": "item", "href": "../item.json"},
                    {"rel": "child", "href": "../catalog.json"},
                    {"rel": "item", "href": "../item.json"},
                ],
                "Collection",
            ),
        )
        self.write("item.json", item())

    def test_crawl_cycles_dedup_relative(self):
        self.tree()
        self.assertEqual(self.crawl(), ["catalog.json", "c.json", "item.json"])

    def test_depth_and_nonrecursive(self):
        self.tree()
        self.assertEqual(self.crawl(0), ["catalog.json"])
        self.runner.documents.clear()
        self.assertEqual(self.crawl(1), ["catalog.json", "c.json"])
        self.runner.documents.clear()
        self.assertEqual(self.crawl(recursive=False), ["catalog.json"])

    def test_absolute_public_links_resolve_locally_without_network(self):
        self.write(
            "catalog.json",
            catalog(
                [
                    {"rel": "self", "href": "https://example.test/stac/catalog.json"},
                    {"rel": "child", "href": "https://example.test/stac/sub/c.json"},
                    {"rel": "child", "href": "https://other.test/remote.json"},
                    {"rel": "child", "href": "https://example.test/outside.json"},
                ]
            ),
        )
        self.write("sub/c.json", catalog())
        self.assertEqual(self.crawl(), ["catalog.json", "c.json"])
        self.assertEqual(self.runner.skipped_remote, 2)
        self.assertIn("does not validate those targets", self.capture.getvalue())

    def test_equivalent_origins_resolve_locally(self):
        self.write(
            "catalog.json",
            catalog(
                [
                    {"rel": "self", "href": "https://example.test/stac/catalog.json"},
                    {"rel": "child", "href": "https://EXAMPLE.TEST/stac/a.json"},
                    {"rel": "child", "href": "https://example.test:443/stac/b.json"},
                    {"rel": "child", "href": "https://example.test:8443/stac/c.json"},
                ]
            ),
        )
        self.write("a.json", catalog())
        self.write("b.json", catalog())
        self.assertEqual(self.crawl(), ["catalog.json", "a.json", "b.json"])
        self.assertEqual(self.runner.skipped_remote, 1)

    def test_pathless_links_resolve_to_source_document(self):
        self.write(
            "catalog.json",
            catalog(
                [
                    {"rel": "child", "href": "#frag"},
                    {"rel": "child", "href": "?revision=1"},
                ]
            ),
        )
        self.assertEqual(self.crawl(), ["catalog.json"])
        self.assertEqual(self.runner.failures, [])

    def test_malformed_link_does_not_block_valid_siblings(self):
        self.write(
            "catalog.json",
            catalog([{"rel": "item", "href": 42}, {"rel": "child", "href": "a.json"}]),
        )
        self.write("a.json", catalog())
        self.assertEqual(self.crawl(), ["catalog.json", "a.json"])
        self.assertEqual(len(self.runner.failures), 1)

    def test_absolute_missing_target_does_not_fetch_remote(self):
        self.write(
            "catalog.json",
            catalog(
                [
                    {"rel": "self", "href": "https://example.test/catalog.json"},
                    {"rel": "child", "href": "https://example.test/missing.json"},
                ]
            ),
        )
        self.crawl()
        self.assertIn("missing.json", self.runner.failures[0].file)

    def test_unmapped_remote_skipped(self):
        self.write(
            "catalog.json", catalog([{"rel": "item", "href": "//host/item.json"}])
        )
        self.assertEqual(self.crawl(), ["catalog.json"])
        self.assertEqual(self.runner.skipped_remote, 1)

    def test_encoded_url_traversal_skipped(self):
        self.write(
            "catalog.json",
            catalog(
                [
                    {"rel": "self", "href": "https://host/stac/catalog.json"},
                    {"rel": "item", "href": "https://host/stac/%2e%2e/outside.json"},
                ]
            ),
        )
        self.crawl()
        self.assertEqual(self.runner.skipped_remote, 1)

    def test_file_uri_and_percent_encoded_relative_path(self):
        child = self.write("a b.json", item())
        self.write(
            "catalog.json",
            catalog(
                [
                    {"rel": "item", "href": child.as_uri()},
                    {"rel": "item", "href": "a%20b.json"},
                ]
            ),
        )
        self.assertEqual(self.crawl(), ["catalog.json", "a b.json"])

    def test_bad_files_and_links(self):
        for value, message in [
            ([], "Expected a STAC"),
            ({}, "Expected type"),
            (catalog("bad"), "links must"),
            (catalog([{}]), "links[0] must"),
            (catalog([42]), "links[0] must"),
            (catalog([{"href": 1}]), "links[0] must"),
        ]:
            with self.subTest(value=value):
                self.runner.failures.clear()
                self.write("catalog.json", value)
                self.crawl()
                self.assertIn(message, self.runner.failures[0].message)
        (self.root / "catalog.json").write_text("{bad", encoding="utf-8")
        self.runner.failures.clear()
        self.crawl()
        self.assertIn("Expecting", self.runner.failures[0].message)

    def test_unsupported_scheme_and_network_file_uri(self):
        for href in ("s3://bucket/item.json", "file://remote/share/item.json"):
            with self.subTest(href=href):
                self.runner.failures.clear()
                self.write("catalog.json", catalog([{"rel": "item", "href": href}]))
                self.crawl()
                self.assertTrue(self.runner.failures)

    def test_asset_checks(self):
        doc = item()
        doc["assets"] = {
            "exists": {"href": "data.parquet"},
            "missing": {"href": "missing.parquet"},
            "cloud": {"href": "s3://bucket/file"},
            "remote": {"href": "https://elsewhere/file"},
            "bad": {},
        }
        (self.root / "data.parquet").touch()
        self.env["IN_VALIDATE_ASSETS"] = "true"
        self.write("catalog.json", doc)
        self.crawl()
        self.assertEqual(self.runner.checked_assets, 2)
        self.assertEqual(self.runner.skipped_remote, 2)
        self.assertEqual(len(self.runner.failures), 2)
        doc["assets"] = []
        self.write("catalog.json", doc)
        self.crawl()
        self.assertIn("assets must", self.runner.failures[-1].message)

    def test_assets_not_checked_by_default(self):
        doc = item()
        doc["assets"] = {"missing": {"href": "missing"}}
        self.write("catalog.json", doc)
        self.crawl()
        self.assertFalse(self.runner.failures)

    def test_invocation_fixed_formats_quoted_path_timeout(self):
        self.runner.extra_args = ["--verbose"]
        target = self.root / "a b.json"
        target.write_text("{}")
        with patch.object(validator.subprocess, "run", return_value=result()) as call:
            self.runner.invoke(target, "json")
        args, kwargs = call.call_args
        self.assertEqual(args[0][-2:], ["--verbose", str(self.root / "a b.json")])
        self.assertIn("--output-format", args[0])
        self.assertEqual(kwargs["timeout"], 120)
        self.assertTrue(kwargs["capture_output"])

    def test_timeout_scales_with_input_size(self):
        target = self.root / "big.ndjson"
        self.runner.extra_args = []
        target.write_bytes(b"x" * (5 * 1024 * 1024))
        with patch.object(validator.subprocess, "run", return_value=result()) as call:
            self.runner.invoke(target, "ndjson")
        self.assertEqual(call.call_args.kwargs["timeout"], 170)

    def test_many_items_one_batch_and_temp_cleanup(self):
        docs = [
            validator.Document(self.root / f"{i}.json", item(str(i)))
            for i in range(1000)
        ]

        def invoke(path, format):
            self.assertEqual(format, "ndjson")
            self.assertEqual(len(path.read_text().splitlines()), 1000)
            return result()

        with patch.object(self.runner, "invoke", side_effect=invoke) as call:
            self.runner.validate_group(docs)
        self.assertEqual(call.call_count, 1)
        self.assertFalse(list(self.work.glob("*.ndjson")))

    def test_failed_batch_isolated_with_duplicate_ids(self):
        docs = [
            validator.Document(
                self.write(f"{i}.json", item("duplicate")), item("duplicate")
            )
            for i in range(4)
        ]

        def invoke(path, format):
            if format == "ndjson" or path.name == "2.json":
                return result(1, json.dumps([{"error": '{"x":2} is invalid'}]))
            return result()

        with patch.object(self.runner, "invoke", side_effect=invoke):
            self.runner.validate_group(docs)
        self.assertEqual(
            [f.file for f in self.runner.failures], [str(self.root / "2.json")]
        )
        self.assertEqual(self.runner.failures[0].message, "<instance> is invalid")

    def test_batch_cleanup_on_timeout(self):
        docs = [validator.Document(self.root / "i.json", item())] * 2
        with patch.object(
            self.runner, "invoke", side_effect=subprocess.TimeoutExpired("rustac", 120)
        ):
            with self.assertRaises(subprocess.TimeoutExpired):
                self.runner.validate_group(docs)
        self.assertFalse(list(self.work.glob("*.ndjson")))

    def test_shared_batch_failures_do_not_split(self):
        docs = [validator.Document(self.root / f"{i}.json", item()) for i in range(100)]
        for failure in [
            result(1, "", "ERROR: schema server unavailable"),
            result(1, "", "ERROR: one or more validation errors"),
            result(2, "", "unexpected CLI failure"),
            result(1, "[]", ""),
            result(1, '[{"unexpected": "format"}]', ""),
        ]:
            with self.subTest(failure=failure):
                with patch.object(
                    self.runner, "invoke", return_value=failure
                ) as invoke:
                    with self.assertRaisesRegex(ValueError, "isolation stopped"):
                        self.runner.validate_group(docs)
                self.assertEqual(invoke.call_count, 1)
                self.assertFalse(list(self.work.glob("*.ndjson")))

    def test_parse_failure_still_isolates_items(self):
        docs = [
            validator.Document(self.write(f"{i}.json", item()), item())
            for i in range(2)
        ]

        def invoke(path, format):
            if format == "ndjson" or path.name == "1.json":
                return result(
                    1,
                    "",
                    "ERROR: data did not match any variant of untagged enum Value\n",
                )
            return result()

        with patch.object(self.runner, "invoke", side_effect=invoke):
            self.runner.validate_group(docs)
        self.assertEqual(len(self.runner.failures), 1)
        self.assertTrue(self.runner.failures[0].file.endswith("1.json"))

    def test_bad_link_and_assets_do_not_hide_siblings(self):
        self.env["IN_VALIDATE_ASSETS"] = "true"
        doc = catalog(
            [
                {"rel": "item", "href": "s3://bucket/unsupported.json"},
                {"rel": "item", "href": "good.json"},
            ]
        )
        doc["assets"] = []
        self.write("catalog.json", doc)
        self.write("good.json", item())
        self.assertEqual(self.crawl(), ["catalog.json", "good.json"])
        self.assertEqual(len(self.runner.failures), 2)

    def test_container_exception_preserves_sibling_results(self):
        self.tree()

        def invoke(path, format):
            if path.name == "catalog.json":
                raise subprocess.TimeoutExpired("rustac", 120)
            if path.name == "c.json":
                return result(1, "", "container schema failure")
            return result()

        with patch.object(self.runner, "invoke", side_effect=invoke):
            self.runner.run()
        self.assertEqual(len(self.runner.failures), 2)
        self.assertEqual(
            {Path(f.file).name for f in self.runner.failures},
            {"catalog.json", "c.json"},
        )

    def test_error_formats(self):
        doc = validator.Document(self.root / "broken.json", item())
        for output, stderr, expected in [
            ("not json", "", "not json"),
            ("", "ERROR: untagged enum Value", "Check required fields"),
            ("", "network failed", "network failed"),
            ("", "", "rustac exited 9"),
            ("[]", "", "[]"),
            ('[{"oops":2}]', "", "Unrecognized"),
            ('["oops"]', "", "Unrecognized"),
            ('[{"error":"invalid field"}]', "", "invalid field"),
        ]:
            with self.subTest(output=output, stderr=stderr):
                self.runner.consume_error(doc, result(9, output, stderr))
                self.assertIn(expected, self.runner.failures[-1].message)

    def test_verbose_raw_output_in_log(self):
        self.env["IN_VERBOSE"] = "true"
        self.runner.consume_error(
            validator.Document(self.root / "x", item()), result(1, "", "raw detail")
        )
        self.assertIn("Raw rustac output", self.runner.log.read_text())

    def test_run_mixed_types(self):
        self.tree()
        with patch.object(self.runner, "invoke", return_value=result()):
            self.runner.run()
        self.assertEqual(self.runner.calls, 3)
        self.assertEqual(len(self.runner.documents), 3)

    def test_container_errors(self):
        self.write("catalog.json", catalog())
        with patch.object(
            self.runner, "invoke", return_value=result(1, "", "bad container")
        ):
            self.runner.run()
        self.assertIn("bad container", self.runner.failures[0].message)

    def test_spatial_failure_is_authoritative_when_cli_passes(self):
        doc = item()
        doc["bbox"] = [-1, -1, 1, 1]
        self.write("catalog.json", doc)
        with patch.object(self.runner, "invoke", return_value=result()):
            self.runner.run()
        report = self.runner.finish()
        self.assertFalse(report["valid"])
        self.assertTrue(
            all(f["file"].endswith("catalog.json") for f in report["errors"])
        )
        self.assertIn("exit-code=1", (self.root / "outputs").read_text())
        self.assertIn("::error", self.capture.getvalue())

    def test_missing_link_does_not_stop_other_documents(self):
        self.write(
            "catalog.json",
            catalog(
                [
                    {"rel": "item", "href": "missing.json"},
                    {"rel": "item", "href": "good.json"},
                ]
            ),
        )
        self.write("good.json", item())
        self.assertEqual(self.crawl(), ["catalog.json", "good.json"])
        self.assertEqual(len(self.runner.failures), 1)

    def test_unsupported_inputs_fail_explicitly(self):
        for name, value in [
            ("EXTRA_ARGS", "--input-format parquet"),
            ("EXTRA_ARGS", "'unterminated"),
            ("MAX_DEPTH", "-1"),
            ("MAX_DEPTH", "abc"),
            ("FILE", ""),
            ("FILE", "https://host/catalog.json"),
            ("FILE", "ftp://host/catalog.json"),
            ("FILE", "s3a://bucket/catalog.json"),
            ("RECURSIVE", "yes"),
        ]:
            with self.subTest(name=name, value=value):
                runner = validator.Runner({**self.env, f"IN_{name}": value}, self.work)
                with self.assertRaises(ValueError):
                    runner.run()

    def test_input_errors_are_readable(self):
        for name, value, message in [
            ("MAX_DEPTH", "abc", "max-depth must be a non-negative integer"),
            ("FILE", "ftp://host/catalog.json", "file must be a local path"),
        ]:
            with self.subTest(name=name):
                runner = validator.Runner({**self.env, f"IN_{name}": value}, self.work)
                with self.assertRaisesRegex(ValueError, message):
                    runner.run()

    def test_supported_args(self):
        self.write("catalog.json", catalog())
        self.env["IN_EXTRA_ARGS"] = "-v --quiet"
        with patch.object(self.runner, "invoke", return_value=result()):
            self.runner.run()
        self.assertEqual(self.runner.extra_args, ["-v", "--quiet"])

    def test_summary_json_outputs_and_escaping(self):
        self.tree()
        with patch.object(self.runner, "invoke", return_value=result()):
            self.runner.run()
        self.runner.fail("<script>,x\n::warning::", "<img> & ```")
        report = self.runner.finish()
        self.assertFalse(report["valid"])
        self.assertEqual(report["objects"], 3)
        self.assertEqual(report["collections"], 1)
        summary = self.runner.summary.read_text()
        self.assertIn("&lt;img&gt;", summary)
        self.assertNotIn("<script>", summary)
        self.assertIn("No best-practice linting", summary)
        outputs = (self.root / "outputs").read_text()
        self.assertIn("valid=false", outputs)
        self.assertIn("report-path=", outputs)
        self.assertIn("%2Cx%0A", self.capture.getvalue())

    def test_success_summary_no_output_env_and_quiet(self):
        self.env.pop("GITHUB_OUTPUT")
        report = self.runner.finish()
        self.assertTrue(report["valid"])
        self.assertIn("Passed", self.runner.summary.read_text())

    def test_error_limits(self):
        for i in range(55):
            self.runner.fail("file", str(i) + "x" * 2500)
        self.runner.finish()
        self.assertEqual(self.capture.getvalue().count("::error"), 50)
        self.assertIn("Some errors are omitted", self.runner.summary.read_text())
        self.assertLess(len(self.runner.summary.read_text()), 55000)
        self.assertEqual(len(json.loads(self.runner.report.read_text())["errors"]), 55)

    def test_streaming_and_annotation_escape(self):
        self.env["IN_STREAM_OUTPUT"] = "true"
        self.runner.write("hi\n::error::untrusted")
        self.assertIn("[rustac] ::error::untrusted", self.capture.getvalue())
        self.assertEqual(validator.escaped("a%\r\n"), "a%25%0D%0A")
        self.assertEqual(validator.concise("plain error"), "plain error")

    def test_main_errors_and_output_file(self):
        self.write("catalog.json", catalog())
        self.env.update(
            RUNNER_TEMP=str(self.root), IN_OUTPUT_FILE=str(self.root / "out.txt")
        )
        for side_effect in [
            None,
            FileNotFoundError("rustac not found"),
            subprocess.TimeoutExpired("rustac", 120),
        ]:
            with self.subTest(error=side_effect):
                with (
                    patch.dict(os.environ, self.env, clear=True),
                    patch.object(validator.Runner, "run", side_effect=side_effect),
                ):
                    self.assertEqual(validator.main(), 0)
        self.assertTrue((self.root / "out.txt").is_file())
        self.assertIn("valid=false", (self.root / "outputs").read_text())
        self.env["IN_OUTPUT_FILE"] = str(self.root / "absent" / "out")
        with (
            patch.dict(os.environ, self.env, clear=True),
            patch.object(validator.Runner, "run"),
        ):
            validator.main()
        self.assertIn("Couldn't write output-file", self.capture.getvalue())

    def test_main_without_github_output(self):
        self.env.pop("GITHUB_OUTPUT")
        self.env["RUNNER_TEMP"] = str(self.root)
        with (
            patch.dict(os.environ, self.env, clear=True),
            patch.object(validator.Runner, "run"),
        ):
            self.assertEqual(validator.main(), 0)

    def test_nonrecursive_ignores_depth(self):
        self.write("catalog.json", catalog())
        self.env.update(IN_RECURSIVE="false", IN_MAX_DEPTH="ignored")
        with patch.object(self.runner, "invoke", return_value=result()):
            self.runner.run()

    def test_main_success_streaming(self):
        self.write("catalog.json", catalog())
        self.env.update(RUNNER_TEMP=str(self.root), IN_STREAM_OUTPUT="true")
        with (
            patch.dict(os.environ, self.env, clear=True),
            patch.object(validator.Runner, "invoke", return_value=result()),
        ):
            self.assertEqual(validator.main(), 0)
        self.assertIn("valid=true", (self.root / "outputs").read_text())

    def action_step(self, name, env, prelude=""):
        action = yaml.safe_load(
            (Path(__file__).resolve().parents[1] / "action.yml").read_text(
                encoding="utf-8"
            )
        )
        step = next(step for step in action["runs"]["steps"] if step["name"] == name)
        return subprocess.run(
            [shutil.which("bash"), "-c", prelude + "\n" + step["run"]],
            env={**os.environ, **env},
            capture_output=True,
            text=True,
            check=False,
        )

    def test_step_summary_uses_markdown_report(self):
        summary = self.root / "summary.md"
        destination = self.root / "github-summary"
        summary.write_text("## Report\nFailed: object.json\n", encoding="utf-8")
        proc = self.action_step(
            "Write to job summary",
            {
                "ENABLED": "true",
                "SUMMARY_PATH": str(summary),
                "GITHUB_STEP_SUMMARY": str(destination),
            },
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(summary.read_text(), destination.read_text())
        self.assertIn("Published validation report", proc.stdout)

    def test_install_logs_package_and_cli_versions(self):
        prelude = """
        python() {
          if [ "$1" = -c ]; then
            echo 'Installed rustac package: 0.9.17'
          else
            printf 'python %s\\n' "$*"
          fi
        }
        rustac() {
          test "$1" = --version || return 1
          echo 'rustac 0.2.14'
        }
        """
        for version, requirement in [
            ("v0.9.17", "rustac==0.9.17"),
            ("latest", "--quiet rustac"),
        ]:
            with self.subTest(version=version):
                proc = self.action_step(
                    "Install validator",
                    {"VERSION": version, "ACTION_PATH": str(self.root)},
                    prelude,
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertIn(requirement, proc.stdout)
                self.assertIn("Installed rustac package: 0.9.17", proc.stdout)
                self.assertIn("rustac 0.2.14", proc.stdout)

    def test_optional_steps_log_noops_without_external_calls(self):
        prelude = "gh() { echo 'unexpected gh call' >&2; return 99; }"
        for step, env, message in [
            ("Write to job summary", {"ENABLED": "false"}, "disabled"),
            ("Write to job summary", {"ENABLED": "true"}, "No validation summary"),
            ("Post PR comment", {"ENABLED": "false"}, "disabled"),
            (
                "Post PR comment",
                {"ENABLED": "true", "EVENT_NAME": "push"},
                "Not a pull_request",
            ),
            (
                "Post PR comment",
                {"ENABLED": "true", "EVENT_NAME": "pull_request"},
                "No validation summary",
            ),
        ]:
            with self.subTest(step=step, env=env):
                proc = self.action_step(step, {"SUMMARY_PATH": "", **env}, prelude)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertIn(message, proc.stdout)

    def test_final_action_status(self):
        for code, valid, outcome, expected in [
            ("0", "true", "success", 0),
            ("1", "false", "success", 1),
            ("0", "false", "success", 1),
            ("", "", "failure", 1),
            ("", "", "success", 1),
        ]:
            with self.subTest(code=code, valid=valid, outcome=outcome):
                proc = self.action_step(
                    "Fail on issues",
                    {
                        "EXIT_CODE": code,
                        "VALID": valid,
                        "RUN_OUTCOME": outcome,
                    },
                )
                self.assertEqual(proc.returncode, expected, proc.stderr)
                self.assertTrue(proc.stdout.strip())
                if expected == 0:
                    self.assertIn("no issues found", proc.stdout)

    def test_sticky_comment_create_and_update_without_network(self):
        summary = self.root / "summary.md"
        summary.write_text("## STAC validation\nPassed\n", encoding="utf-8")
        calls = self.root / "gh-calls"
        env = {
            "ENABLED": "true",
            "EVENT_NAME": "pull_request",
            "SUMMARY_PATH": str(summary),
            "RUNNER_TEMP": str(self.root),
            "REPO": "example/repo",
            "PR_NUMBER": "42",
            "GH_CALLS": str(calls),
        }
        prelude = """
        gh() {
          printf '%s\\n' "$*" >> "$GH_CALLS"
          if [ "$1" = api ] && [ "$2" = --paginate ]; then
            printf '%s' "$EXISTING_COMMENT"
          fi
        }
        """
        for existing, expected in [("", "pr comment 42"), ("123", "--method PATCH")]:
            with self.subTest(existing=existing):
                if calls.exists():
                    calls.unlink()
                proc = self.action_step(
                    "Post PR comment", {**env, "EXISTING_COMMENT": existing}, prelude
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertIn(expected, calls.read_text())
                self.assertIn("Published validation PR comment", proc.stdout)
                body = (self.root / "stac-check-comment.md").read_text()
                self.assertTrue(body.startswith("<!-- stac-check-action -->"))
                self.assertIn(summary.read_text(), body)

    def test_action_inputs_are_wired_without_shell_interpolation(self):
        root = Path(__file__).resolve().parents[1]
        action = yaml.safe_load((root / "action.yml").read_text(encoding="utf-8"))
        steps = action["runs"]["steps"]
        runner = next(step for step in steps if step.get("id") == "run")
        self.assertIn("scripts/run.py", runner["run"])
        self.assertNotIn("backend", action["inputs"])
        for name in (
            "stac-check-version",
            "pydantic",
            "fast",
            "fast-linting",
            "config",
        ):
            self.assertNotIn(name, action["inputs"])
        for name in action["inputs"]:
            if name in ("rustac-version", "job-summary", "comment-pr"):
                continue
            variable = "IN_" + name.upper().replace("-", "_")
            self.assertEqual(runner["env"][variable], "${{ inputs." + name + " }}")
        for step in steps:
            self.assertNotIn("${{", step.get("run", ""))


if __name__ == "__main__":
    unittest.main()
