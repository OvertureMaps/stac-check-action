from __future__ import annotations

import html
import json
import os
import shlex
import subprocess
import tempfile
import time
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit
from urllib.request import url2pathname

from geometry import check_geometry


@dataclass
class Document:
    path: Path
    value: dict


@dataclass
class Failure:
    file: str
    message: str


def escaped(value: str, properties: bool = False) -> str:
    value = value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    return value.replace(",", "%2C").replace(":", "%3A") if properties else value


def annotation(level: str, message: str, file: str = "") -> None:
    prop = f" file={escaped(file, True)}" if file else ""
    print(f"::{level}{prop}::{escaped(message)}", flush=True)


def concise(message: str) -> str:
    try:
        _, end = json.JSONDecoder().raw_decode(message)
    except json.JSONDecodeError:
        return message
    return "<instance>" + message[end:]


class Runner:
    def __init__(self, env: dict[str, str], work: Path):
        self.env = env
        self.work = work
        self.failures: list[Failure] = []
        self.documents: list[Document] = []
        self.skipped_remote = 0
        self.checked_assets = 0
        self.calls = 0
        self.started = time.monotonic()
        self.log = work / "validation.log"
        self.summary = work / "summary.md"
        self.report = work / "report.json"
        self.log.touch()

    def write(self, text: str) -> None:
        with self.log.open("a", encoding="utf-8") as handle:
            handle.write(text + "\n")
        if self.env.get("IN_STREAM_OUTPUT", "true") == "true":
            for line in text.splitlines():
                print(f"[rustac] {line}", flush=True)

    def fail(self, path: Path | str, message: str) -> None:
        self.failures.append(Failure(str(path), message))
        self.write(f"FAIL {path}: {message}")
        if len(self.failures) <= 50:
            annotation("error", message[:2000], str(path))

    def local_path(self, href: str, source: Path, base: str) -> Path | None:
        url = urlsplit(href)
        if url.scheme in ("http", "https") or (not url.scheme and url.netloc):
            target = urlsplit(urljoin(base, href))
            root = urlsplit(base)
            if root.scheme and (target.scheme, target.netloc) == (
                root.scheme,
                root.netloc,
            ):
                target_path, root_path = unquote(target.path), unquote(root.path)
                if target_path.startswith(root_path):
                    path = (self.root / target_path[len(root_path) :]).resolve()
                    if path.is_relative_to(self.root):
                        return path
            self.skipped_remote += 1
            return None
        if url.scheme == "file":
            if url.netloc:
                raise ValueError(f"Network file URI isn't supported: {href}")
            return Path(url2pathname(url.path)).resolve()
        if url.scheme:
            raise ValueError(f"Unsupported link scheme: {url.scheme}")
        return (source.parent / unquote(url.path)).resolve()

    def crawl(self, file: Path, recursive: bool, max_depth: int | None) -> None:
        self.root = file.parent
        pending = deque([(file, 0)])
        seen: set[Path] = set()
        base = ""
        while pending:
            path, depth = pending.popleft()
            if path in seen:
                continue
            seen.add(path)
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(value, dict):
                    raise ValueError("Expected a STAC JSON object")
                if value.get("type") not in ("Catalog", "Collection", "Feature"):
                    raise ValueError("Expected type Catalog, Collection, or Feature")
                links = value.get("links", [])
                if not isinstance(links, list) or any(
                    not isinstance(link, dict) or not isinstance(link.get("href"), str)
                    for link in links
                ):
                    raise ValueError(
                        "links must be an array of objects with string hrefs"
                    )
                if path == file:
                    self_href = next(
                        (link["href"] for link in links if link.get("rel") == "self"),
                        "",
                    )
                    base = (
                        urljoin(self_href, "./") if urlsplit(self_href).scheme else ""
                    )
                self.documents.append(Document(path, value))
                if self.env.get("IN_VALIDATE_ASSETS") == "true":
                    try:
                        self.assets(path, value, base)
                    except (OSError, ValueError) as error:
                        self.fail(path, f"Asset checks: {error}")
                if recursive and (max_depth is None or depth < max_depth):
                    for link in links:
                        if link.get("rel") in ("child", "item"):
                            try:
                                target = self.local_path(link["href"], path, base)
                            except (OSError, ValueError) as error:
                                self.fail(path, f"Link {link['href']}: {error}")
                                continue
                            if target is not None:
                                pending.append((target, depth + 1))
            except (OSError, ValueError) as error:
                self.fail(path, str(error))
        self.write(f"Discovered {len(self.documents)} STAC objects")
        if self.skipped_remote:
            annotation(
                "warning",
                f"Skipped {self.skipped_remote} remote links/assets outside the local catalog. "
                "This run does not validate those targets.",
            )

    def assets(self, path: Path, value: dict, base: str) -> None:
        assets = value.get("assets", {})
        if not isinstance(assets, dict):
            raise ValueError("assets must be an object")
        for name, asset in assets.items():
            if not isinstance(asset, dict) or not isinstance(asset.get("href"), str):
                self.fail(path, f"Asset {name}: expected an object with a string href")
                continue
            href = asset["href"]
            # Assets in cloud storage aren't local files and never need a HEAD request.
            if urlsplit(href).scheme not in ("", "file", "http", "https"):
                self.skipped_remote += 1
                continue
            target = self.local_path(href, path, base)
            if target is not None:
                self.checked_assets += 1
                if not target.is_file():
                    self.fail(path, f"Asset {name}: local file not found: {target}")

    def invoke(self, file: Path, format: str) -> subprocess.CompletedProcess[str]:
        args = [
            "rustac",
            "validate",
            "--input-format",
            format,
            "--output-format",
            "json",
            *self.extra_args,
            str(file),
        ]
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )

    def validate_group(self, documents: list[Document]) -> None:
        if not documents:
            return
        # A failing batch is split to attribute errors even when IDs repeat across collections.
        if len(documents) == 1:
            file, format = documents[0].path, "json"
            result = self.invoke(file, format)
        else:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".ndjson",
                dir=self.work,
                encoding="utf-8",
                delete=False,
            ) as handle:
                for doc in documents:
                    handle.write(json.dumps(doc.value) + "\n")
                file = Path(handle.name)
            try:
                result = self.invoke(file, "ndjson")
            finally:
                file.unlink()
        self.calls += 1
        if result.returncode == 0:
            return
        if len(documents) > 1:
            try:
                errors = json.loads(result.stdout)
            except json.JSONDecodeError:
                errors = None
            schema_errors = (
                isinstance(errors, list)
                and bool(errors)
                and all(
                    isinstance(error, dict) and isinstance(error.get("error"), str)
                    for error in errors
                )
            )
            parse_error = (
                not result.stdout.strip()
                and result.stderr.strip()
                == "ERROR: data did not match any variant of untagged enum Value"
            )
            if not schema_errors and not parse_error:
                diagnostic = result.stderr.strip() or result.stdout.strip()
                raise ValueError(
                    f"Item batch failed without object-specific diagnostics "
                    f"(rustac exit {result.returncode}); isolation stopped to avoid "
                    f"repeating operational failures. {diagnostic}"
                )
            middle = len(documents) // 2
            self.validate_group(documents[:middle])
            self.validate_group(documents[middle:])
            return
        self.consume_error(documents[0], result)

    def consume_error(
        self, doc: Document, result: subprocess.CompletedProcess[str]
    ) -> None:
        detail = result.stdout.strip()
        try:
            errors = json.loads(detail)
        except json.JSONDecodeError:
            errors = None
        if isinstance(errors, list) and errors:
            for error in errors:
                message = error.get("error") if isinstance(error, dict) else None
                if not isinstance(message, str):
                    self.fail(
                        doc.path, f"Unrecognized rustac error: {str(error)[:2000]}"
                    )
                else:
                    self.fail(doc.path, concise(message))
        else:
            message = (
                detail or result.stderr.strip() or f"rustac exited {result.returncode}"
            )
            if "untagged enum Value" in message:
                message = (
                    "rustac couldn't parse this STAC object. Check required fields, datetime, "
                    "bbox and geometry types. " + message
                )
            self.fail(doc.path, message)
        if self.env.get("IN_VERBOSE") == "true":
            self.write(
                f"Raw rustac output for {doc.path}:\n{result.stdout}\n{result.stderr}"
            )

    def run(self) -> None:
        for name in (
            "RECURSIVE",
            "VALIDATE_ASSETS",
            "VERBOSE",
            "STREAM_OUTPUT",
        ):
            value = self.env.get(f"IN_{name}", "")
            if value and value not in ("true", "false"):
                raise ValueError(
                    f"{name.lower().replace('_', '-')} must be true or false"
                )
        self.extra_args = shlex.split(self.env.get("IN_EXTRA_ARGS", ""))
        if any(
            arg not in ("--verbose", "-v", "--quiet", "-q") for arg in self.extra_args
        ):
            raise ValueError(
                "rustac extra-args only supports --verbose/-v and --quiet/-q. "
                "Format/input overrides would bypass the wrapper's validation contract. "
                "stac-check CLI arguments aren't supported."
            )
        raw_depth = self.env.get("IN_MAX_DEPTH", "")
        max_depth = (
            int(raw_depth)
            if raw_depth and self.env.get("IN_RECURSIVE") == "true"
            else None
        )
        if max_depth is not None and max_depth < 0:
            raise ValueError(
                "max-depth must be a non-negative integer (root is depth 0)"
            )
        file = self.env.get("IN_FILE", "")
        if not file:
            raise ValueError("file is required")
        if urlsplit(file).scheme in ("http", "https", "s3", "gs", "az"):
            raise ValueError("file must be a local path")
        self.crawl(
            Path(file).resolve(), self.env.get("IN_RECURSIVE") == "true", max_depth
        )
        items = [doc for doc in self.documents if doc.value["type"] == "Feature"]
        for doc in items:
            for message in check_geometry(doc.value):
                self.fail(doc.path, message)
        self.write(f"Validating {len(items)} items in one batch")
        self.validate_group(items)
        containers = [doc for doc in self.documents if doc.value["type"] != "Feature"]
        # CLI validation only batches Items; containers use bounded parallel processes.
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(self.validate_container, doc) for doc in containers]
            for doc, future in zip(containers, futures):
                self.calls += 1
                try:
                    result = future.result()
                except (OSError, ValueError, subprocess.TimeoutExpired) as error:
                    self.fail(doc.path, f"Validation could not complete: {error}")
                    continue
                if result.returncode:
                    self.consume_error(doc, result)
        self.write(f"Finished validation: {len(self.failures)} errors")

    def validate_container(self, doc: Document) -> subprocess.CompletedProcess[str]:
        return self.invoke(doc.path, "json")

    def finish(self) -> dict:
        counts = Counter(doc.value["type"] for doc in self.documents)
        report = {
            "backend": "rustac",
            "valid": not self.failures,
            "objects": len(self.documents),
            "items": counts["Feature"],
            "collections": counts["Collection"],
            "catalogs": counts["Catalog"],
            "errors": [asdict(failure) for failure in self.failures],
            "skipped_remote": self.skipped_remote,
            "checked_assets": self.checked_assets,
            "cli_calls": self.calls,
            "seconds": round(time.monotonic() - self.started, 2),
        }
        self.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        rows = [
            "## STAC validation (rustac)",
            "",
            f"**Result: {'Failed' if self.failures else 'Passed'}**",
            "",
            "| Items | Collections | Catalogs | Errors | Seconds |",
            "|---:|---:|---:|---:|---:|",
            f"| {counts['Feature']} | {counts['Collection']} | {counts['Catalog']} | "
            f"{len(self.failures)} | {report['seconds']} |",
            "",
            "Checks: core and declared extension schemas, coordinate ranges, and "
            "geometry/bbox consistency. No best-practice linting or geometric topology checks.",
            "",
            f"Local assets checked: {self.checked_assets}. "
            f"Remote links/assets skipped: {self.skipped_remote}.",
        ]
        if self.failures:
            rows += ["", "### Errors", ""]
            shown = 0
            for failure in self.failures[:50]:
                if sum(map(len, rows)) > 45000:
                    break
                rows += [
                    f"<pre>{html.escape(failure.file[:1000])}\n"
                    f"{html.escape(failure.message[:2000])}</pre>",
                    "",
                ]
                shown += 1
            if shown < len(self.failures):
                rows += ["Some errors are omitted. See the full log/report.", ""]
        self.summary.write_text("\n".join(rows) + "\n", encoding="utf-8")
        output = self.env.get("GITHUB_OUTPUT")
        if output:
            with open(output, "a", encoding="utf-8") as handle:
                handle.write(
                    f"valid={str(report['valid']).lower()}\n"
                    f"exit-code={0 if report['valid'] else 1}\n"
                    f"log-path={self.log}\nsummary-path={self.summary}\nreport-path={self.report}\n"
                )
        if self.env.get("IN_STREAM_OUTPUT", "true") != "true":
            for line in self.log.read_text(encoding="utf-8").splitlines():
                print(f"[rustac] {line}")
        return report


def main() -> int:
    env = dict(os.environ)
    work = Path(tempfile.mkdtemp(prefix="stac-validation-", dir=env.get("RUNNER_TEMP")))
    runner = Runner(env, work)
    output = env.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"log-path={runner.log}\n")
    try:
        runner.run()
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        runner.fail(env.get("IN_FILE", ""), f"Validation could not complete: {error}")
    if env.get("IN_OUTPUT_FILE"):
        try:
            Path(env["IN_OUTPUT_FILE"]).write_text(
                runner.log.read_text(encoding="utf-8"), encoding="utf-8"
            )
        except OSError as error:
            runner.fail(env["IN_OUTPUT_FILE"], f"Couldn't write output-file: {error}")
    runner.finish()
    # The final action step raises validation failures after publishing the reports.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
