import csv
import os
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from tools.batch_download_fulltext_exports import (
    DownloadTask,
    apply_api_env,
    build_api_env,
    discover_subjournal_tasks,
    load_existing_success_dois,
    load_existing_result_rows,
    load_task_rows,
    write_partitioned_download_csvs,
)


class BatchDownloadFulltextExportsTests(unittest.TestCase):
    def write_csv(self, path, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["title", "doi", "link"])
            writer.writeheader()
            writer.writerows(rows)

    def test_discovers_subjournal_tasks_from_exports_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "exports" / "sleep"
            self.write_csv(
                root / "nature" / "Nature Genetics" / "sleep_related_2020-01-01_2027-07-28.csv",
                [{"title": "Sleep paper", "doi": "10.1000/a", "link": "https://doi.org/10.1000/a"}],
            )
            self.write_csv(
                root / "cell" / "Cell" / "sleep_related_2020-01-01_2027-07-28.csv",
                [{"title": "Cell paper", "doi": "10.1000/b", "link": "https://doi.org/10.1000/b"}],
            )

            tasks = discover_subjournal_tasks(root)

        self.assertEqual([(task.journal_type, task.subjournal) for task in tasks], [
            ("cell", "Cell"),
            ("nature", "Nature Genetics"),
        ])
        self.assertEqual(len(tasks[0].files), 1)

    def test_load_task_rows_dedupes_by_doi_across_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "exports" / "sleep"
            sub = root / "nature" / "Nature Genetics"
            first = sub / "sleep_related_a.csv"
            second = sub / "sleep_related_b.csv"
            self.write_csv(first, [
                {"title": "Original title", "doi": "https://doi.org/10.1000/a", "link": "https://doi.org/10.1000/a"},
            ])
            self.write_csv(second, [
                {"title": "Duplicate title", "doi": "10.1000/a", "link": "https://doi.org/10.1000/a"},
                {"title": "New title", "doi": "10.1000/b", "link": "https://doi.org/10.1000/b"},
            ])
            task = DownloadTask("nature", "Nature Genetics", sub, [first, second])

            rows = load_task_rows(task)

        self.assertEqual([row["doi"] for row in rows], ["10.1000/a", "10.1000/b"])
        self.assertEqual(rows[0]["title"], "Original title")
        self.assertEqual(rows[0]["journal_type"], "nature")
        self.assertEqual(rows[0]["subjournal"], "Nature Genetics")

    def test_load_existing_success_dois_reads_final_and_partial_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            fulltext = Path(tmp) / "fulltext"
            self.write_csv(fulltext / "download_results.csv", [
                {"title": "Done", "doi": "10.1000/done", "link": "https://doi.org/10.1000/done"},
            ])
            with (fulltext / "download_results.partial.csv").open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["title", "doi", "link", "fulltext_status"])
                writer.writeheader()
                writer.writerow({
                    "title": "Partial",
                    "doi": "10.1000/partial",
                    "link": "https://doi.org/10.1000/partial",
                    "fulltext_status": "downloaded",
                })
                writer.writerow({
                    "title": "Failed",
                    "doi": "10.1000/failed",
                    "link": "https://doi.org/10.1000/failed",
                    "fulltext_status": "failed",
                })

            # Rewrite final with the expected status column.
            with (fulltext / "download_results.csv").open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["title", "doi", "link", "fulltext_status"])
                writer.writeheader()
                writer.writerow({
                    "title": "Done",
                    "doi": "10.1000/done",
                    "link": "https://doi.org/10.1000/done",
                    "fulltext_status": "duplicate_doi_downloaded",
                })

            dois = load_existing_success_dois(fulltext, retry_failed=False)
            retry_dois = load_existing_success_dois(fulltext, retry_failed=True)

            self.assertEqual(dois, {"10.1000/done", "10.1000/partial", "10.1000/failed"})
            self.assertEqual(retry_dois, {"10.1000/done", "10.1000/partial"})

    def test_load_existing_result_rows_preserves_only_success_when_retry_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            fulltext = Path(tmp) / "fulltext"
            fulltext.mkdir(parents=True, exist_ok=True)
            with (fulltext / "download_results.csv").open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["title", "doi", "fulltext_status"])
                writer.writeheader()
                writer.writerow({"title": "Done", "doi": "10.1000/done", "fulltext_status": "downloaded"})
                writer.writerow({"title": "Failed", "doi": "10.1000/failed", "fulltext_status": "failed"})

            default_rows = load_existing_result_rows(fulltext, retry_failed=False)
            retry_rows = load_existing_result_rows(fulltext, retry_failed=True)

        self.assertEqual({row["doi"] for row in default_rows}, {"10.1000/done", "10.1000/failed"})
        self.assertEqual({row["doi"] for row in retry_rows}, {"10.1000/done"})

    def test_write_partitioned_download_csvs_splits_success_and_failed_rows(self):
        rows = [
            {"title": "Done", "doi": "10.1000/done", "fulltext_status": "downloaded"},
            {"title": "Existing", "doi": "10.1000/existing", "fulltext_status": "skipped_existing"},
            {"title": "Failed", "doi": "10.1000/failed", "fulltext_status": "failed"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "fulltext"
            counts = write_partitioned_download_csvs(output_dir, rows, ["title", "doi", "fulltext_status"])
            with (output_dir / "fulltext_download_success.csv").open("r", encoding="utf-8-sig") as handle:
                success = list(csv.DictReader(handle))
            with (output_dir / "fulltext_download_failed.csv").open("r", encoding="utf-8-sig") as handle:
                failed = list(csv.DictReader(handle))

        self.assertEqual(counts, {"success": 2, "failed": 1})
        self.assertEqual({row["doi"] for row in success}, {"10.1000/done", "10.1000/existing"})
        self.assertEqual([row["doi"] for row in failed], ["10.1000/failed"])

    def test_downloader_can_stop_after_first_non_pdf_fulltext(self):
        import importlib.util
        import sys

        script_path = Path(r"D:\crawler2025\test.py")
        if not script_path.exists():
            self.skipTest("D:\\crawler2025\\test.py is not available")
        spec = importlib.util.spec_from_file_location("test_downloader_stop_first", script_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        calls = []
        downloader = module.Downloader(
            out_dir=Path(tempfile.mkdtemp()),
            email="user@example.com",
            sources=["unpaywall", "openalex"],
            stop_after_first_fulltext=True,
        )

        def unpaywall(_doi, _stem):
            calls.append("unpaywall")
            return module.Result("downloaded", source="Unpaywall", fmt="html", file=__file__)

        def openalex(_doi, _stem):
            calls.append("openalex")
            return module.Result("downloaded", source="OpenAlex", fmt="pdf", file=__file__)

        downloader.unpaywall = unpaywall
        downloader.openalex = openalex
        downloader.validate_fulltext_file = lambda result: True

        result = downloader.one("10.1000/example", "Example")

        self.assertEqual(result.fmt, "html")
        self.assertEqual(calls, ["unpaywall"])

    def test_downloader_keeps_pdf_priority_by_default(self):
        import importlib.util
        import sys

        script_path = Path(r"D:\crawler2025\test.py")
        if not script_path.exists():
            self.skipTest("D:\\crawler2025\\test.py is not available")
        spec = importlib.util.spec_from_file_location("test_downloader_pdf_priority", script_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        calls = []
        downloader = module.Downloader(
            out_dir=Path(tempfile.mkdtemp()),
            email="user@example.com",
            sources=["unpaywall", "openalex"],
        )

        def unpaywall(_doi, _stem):
            calls.append("unpaywall")
            return module.Result("downloaded", source="Unpaywall", fmt="html", file=__file__)

        def openalex(_doi, _stem):
            calls.append("openalex")
            return module.Result("downloaded", source="OpenAlex", fmt="pdf", file=__file__)

        downloader.unpaywall = unpaywall
        downloader.openalex = openalex
        downloader.validate_fulltext_file = lambda result: True

        result = downloader.one("10.1000/example", "Example")

        self.assertEqual(result.fmt, "pdf")
        self.assertEqual(calls, ["unpaywall", "openalex"])

    def test_downloader_reads_semantic_scholar_api_key_env_alias(self):
        import importlib.util
        import sys

        script_path = Path(r"D:\crawler2025\test.py")
        if not script_path.exists():
            self.skipTest("D:\\crawler2025\\test.py is not available")
        spec = importlib.util.spec_from_file_location("test_downloader_env_alias", script_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        old_value = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
        old_s2 = os.environ.get("S2_API_KEY")
        os.environ["SEMANTIC_SCHOLAR_API_KEY"] = "test-semantic-key"
        os.environ.pop("S2_API_KEY", None)
        try:
            downloader = module.Downloader(
                out_dir=Path(tempfile.mkdtemp()),
                email="user@example.com",
            )
        finally:
            if old_value is None:
                os.environ.pop("SEMANTIC_SCHOLAR_API_KEY", None)
            else:
                os.environ["SEMANTIC_SCHOLAR_API_KEY"] = old_value
            if old_s2 is not None:
                os.environ["S2_API_KEY"] = old_s2

        self.assertEqual(downloader.s2_api_key, "test-semantic-key")

    def test_batch_script_builds_and_applies_api_env(self):
        args = Namespace(
            email="contact@example.com",
            openalex_api_key="openalex-test",
            semantic_scholar_api_key="semantic-test",
            ncbi_api_key="ncbi-test",
            ncbi_email="ncbi@example.com",
            ncbi_tool="crawler-test",
            europe_pmc_email="epmc@example.com",
        )
        api_env = build_api_env(args)
        old_values = {key: os.environ.get(key) for key in api_env}
        try:
            apply_api_env(api_env)
            self.assertEqual(os.environ["OPENALEX_API_KEY"], "openalex-test")
            self.assertEqual(os.environ["SEMANTIC_SCHOLAR_API_KEY"], "semantic-test")
            self.assertEqual(os.environ["NCBI_API_KEY"], "ncbi-test")
            self.assertEqual(os.environ["NCBI_EMAIL"], "ncbi@example.com")
            self.assertEqual(os.environ["NCBI_TOOL"], "crawler-test")
            self.assertEqual(os.environ["EUROPE_PMC_EMAIL"], "epmc@example.com")
            self.assertEqual(os.environ["UNPAYWALL_EMAIL"], "contact@example.com")
        finally:
            for key, value in old_values.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
