from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl import Workbook

from sleep_ai_scientist.feature_extraction.extractors.scale_feature_extractor import ScaleFeatureExtractor


def _write_workbook(root: Path, subject: str, visits: list[tuple[str, int]]) -> None:
    target = root / subject / "scales" / f"{subject}_scales.xlsx"
    target.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    sheet = workbook.active
    for visit, isi in visits:
        sheet.append([f"id评估（{visit}）", "PSQI", "ISI", "嗜睡", "BAI", "BDI"])
        sheet.append([subject, 7, isi, 2, 5, 6])
        sheet.append([])
    workbook.save(target)


def test_scale_feature_extractor_writes_long_and_baseline_xlsx_tables(tmp_path: Path) -> None:
    _write_workbook(tmp_path, "sub-ISM035", [("0w", 18), ("2w", 15)])
    _write_workbook(tmp_path, "sub-NOBASE", [("6w", 7), ("2w", 12)])

    table = ScaleFeatureExtractor({"input_root": str(tmp_path)}).run(
        plan_id="plan_scale",
        output_dir=tmp_path / "out",
    )

    assert table is not None
    assert table.modality == "scales"
    assert Path(table.path).name == "scale_features.csv"
    baseline = pd.read_csv(table.path).set_index("subject_id")
    long_frame = pd.read_csv(table.metadata["long_table"])
    assert len(long_frame) == 4
    assert baseline.loc["sub-ISM035", "ISI"] == 18
    assert baseline.loc["sub-ISM035", "baseline_source_visit"] == "0w"
    assert baseline.loc["sub-NOBASE", "ISI"] == 12
    assert baseline.loc["sub-NOBASE", "baseline_source_visit"] == "2w"
    assert bool(baseline.loc["sub-NOBASE", "baseline_is_substituted"]) is True
    assert table.metadata["workbook_audit"]["parsed_file_count"] == 2
    assert table.metadata["baseline_audit"]["substituted_baseline_count"] == 1


def test_scale_feature_extractor_preserves_tabular_fallback(tmp_path: Path) -> None:
    source = tmp_path / "existing_scale_features.csv"
    pd.DataFrame([{"subject_id": "sub-CSV001", "ISI": 14, "PSQI": 8}]).to_csv(source, index=False)

    table = ScaleFeatureExtractor({"features_csv": str(source)}).run(
        plan_id="plan_csv",
        output_dir=tmp_path / "out",
    )

    assert table is not None
    output = pd.read_csv(table.path)
    assert output.loc[0, "subject_id"] == "sub-CSV001"
    assert output.loc[0, "ISI"] == 14
    assert table.metadata["extraction"] == "questionnaire_table_summary"
