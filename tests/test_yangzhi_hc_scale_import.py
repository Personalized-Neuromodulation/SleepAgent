from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook

from sleep_ai_scientist.feature_extraction.yangzhi_hc_scale_import import parse_yangzhi_hc_source


SOURCE_HEADERS = [
    "ID                项目",
    "姓名",
    "睡眠效率",
    "睡眠潜伏期",
    "睡眠时间",
    "睡眠障碍",
    "睡眠质量",
    "药物",
    "日间功能障碍",
    "PSQI",
    "睡眠延迟Q2",
    "ISI",
    "嗜睡",
    "BAI",
    "BDI",
]


def _write_source(path: Path, rows: list[list[object]]) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(SOURCE_HEADERS)
    for row in rows:
        sheet.append(row)
    workbook.save(path)


def test_parse_yangzhi_hc_source_uses_exact_namespace_mapping(tmp_path: Path) -> None:
    source = tmp_path / "healthy.xlsx"
    _write_source(
        source,
        [["YZ_HC_020", "王浩", 0, 2, 0, 1, 2, 0, 2, 7, "37.5min", 7, 9, 9, 7]],
    )

    records = parse_yangzhi_hc_source(source)

    assert records == [
        {
            "source_id": "YZ_HC_020",
            "subject_id": "sub-YZHC020",
            "睡眠效率": 0,
            "睡眠潜伏期": 2,
            "睡眠时间": 0,
            "睡眠障碍": 1,
            "睡眠质量": 2,
            "药物": 0,
            "日间功能障碍": 2,
            "PSQI": 7,
            "睡眠延迟Q2": "37.5min",
            "ISI": 7,
            "嗜睡": 9,
            "BAI": 9,
            "BDI": 7,
        }
    ]


def test_parse_yangzhi_hc_source_rejects_non_hc_identifier(tmp_path: Path) -> None:
    source = tmp_path / "invalid.xlsx"
    _write_source(
        source,
        [["YZ_ISM_020", "某人", 0, 2, 0, 1, 2, 0, 2, 7, "37.5min", 7, 9, 9, 7]],
    )

    with pytest.raises(ValueError, match="YZ_ISM_020"):
        parse_yangzhi_hc_source(source)
