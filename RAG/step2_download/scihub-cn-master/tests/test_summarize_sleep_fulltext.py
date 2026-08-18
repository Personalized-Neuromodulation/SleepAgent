import csv

from summarize_sleep_fulltext import summarize_root


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["doi", "title"])
        writer.writeheader()
        writer.writerows(rows)


def test_summarize_root_counts_papers_unique_dois_and_fulltext_formats(tmp_path):
    write_csv(
        tmp_path / "cell" / "Cell" / "sleep_related_a.csv",
        [
            {"doi": "10.1000/A", "title": "A"},
            {"doi": "https://doi.org/10.1000/a", "title": "A duplicate"},
            {"doi": "10.1000/B", "title": "B"},
        ],
    )
    write_csv(
        tmp_path / "nature" / "Nature" / "sleep_related_b.csv",
        [{"doi": "doi:10.2000/C", "title": "C"}],
    )

    cell_fulltext = tmp_path / "cell" / "Cell" / "full_text"
    cell_fulltext.mkdir()
    for name in ("a.pdf", "b.xml", "c.md", "d.json", "legacy.txt", "pending.html"):
        (cell_fulltext / name).write_text("content", encoding="utf-8")
    nature_fulltext = tmp_path / "nature" / "Nature" / "full_text"
    nature_fulltext.mkdir()
    (nature_fulltext / "c.pdf").write_text("content", encoding="utf-8")
    write_csv(
        tmp_path / "cell" / "archive" / "old" / "sleep_related_old.csv",
        [{"doi": "10.9999/old", "title": "Archived"}],
    )
    archived_fulltext = tmp_path / "cell" / "archive" / "old" / "full_text"
    archived_fulltext.mkdir()
    (archived_fulltext / "old.pdf").write_text("content", encoding="utf-8")

    report = summarize_root(tmp_path)

    assert [row.journal_type for row in report.rows] == ["cell", "nature"]
    cell = report.rows[0]
    assert cell.csv_files == 1
    assert cell.paper_rows == 3
    assert cell.unique_dois == 2
    assert (cell.pdf, cell.xml, cell.md, cell.json, cell.txt) == (1, 1, 1, 1, 1)
    assert cell.fulltext_total == 5
    assert cell.html == 1

    assert report.total.paper_rows == 4
    assert report.total.unique_dois == 3
    assert report.total.pdf == 2
    assert report.total.fulltext_total == 6
    assert report.total.html == 1
