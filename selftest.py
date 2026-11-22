"""Executable acceptance checks that do not require the MySQL password."""

from __future__ import annotations

import csv
import json
import os
import re
import sys
from pathlib import Path

import pandas as pd
from PIL import Image

from admissions_common import (
    ROOT,
    connect_database,
    ensure_utf8_stdio,
    get_database_config,
)
from hebut import records_from_frame as hebut_records
from sufe import records_from_frame as sufe_records


def read_csv(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def check_python_files():
    failures = []
    for path in ROOT.glob("*.py"):
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except SyntaxError as exc:
            failures.append(f"{path.name}: {exc}")
    assert not failures, failures
    print("PASS python syntax")


def check_nuc():
    path = ROOT / "results" / "nuc" / "nuc_candidates_final.csv"
    rows = read_csv(path)
    provinces = {row["province"] for row in rows}
    assert len(provinces) == 31, provinces
    assert len(rows) >= 1000, len(rows)
    assert all(int(row["planned_count"]) > 0 for row in rows)
    assert not [
        row
        for row in rows
        if re.search(r"^(合计|总计|小计)$", row["major_name"])
    ]
    xinjiang = [row for row in rows if row["province"] == "新疆"]
    assert len(xinjiang) == 54, len(xinjiang)
    assert sum(int(row["planned_count"]) for row in xinjiang) == 88
    assert len({row["plan_type"] for row in xinjiang}) == 4
    print("PASS NUC", len(rows), "rows", len(provinces), "provinces")


def check_nuc_assets():
    images = list((ROOT / "images" / "nuc").rglob("page_*.png"))
    raw = list((ROOT / "ocr_results" / "nuc").rglob("*_res.json"))
    if not images and not raw:
        print("SKIP NUC raw OCR assets: not included in repository")
        return
    assert len(images) == 42, len(images)
    assert len(raw) == 42, len(raw)
    for image in images:
        target = (
            ROOT
            / "ocr_results"
            / "nuc"
            / image.parent.name
            / f"{image.stem}_res.json"
        )
        assert target.exists(), target
    print("PASS NUC assets", len(images), "images")


def check_sxnu():
    rows = read_csv(ROOT / "results" / "sxnu" / "sxnu_candidates.csv")
    assert len(rows) == 758, len(rows)
    assert sum(int(row["planned_count"]) for row in rows) == 5100
    print("PASS SXNU", len(rows), "rows / 5100 planned")


def check_neu():
    images = list((ROOT / "images" / "neu").glob("*.png"))
    ocr = list((ROOT / "ocr_results" / "neu").glob("*_res.json"))
    if not images and not ocr:
        print("SKIP NEU raw OCR assets: not included in repository")
        path = ROOT / "results" / "neu" / "neu_candidates.csv"
        rows = read_csv(path)
        provinces = {row["province"] for row in rows}
        assert len(provinces) == 31, provinces
        print("PASS NEU", len(rows), "rows", len(provinces), "provinces")
        return
    assert len(images) == 31, len(images)
    if len(ocr) < 31:
        print("PARTIAL NEU OCR", len(ocr), "/ 31")
        return
    path = ROOT / "results" / "neu" / "neu_candidates.csv"
    rows = read_csv(path)
    provinces = {row["province"] for row in rows}
    assert len(provinces) == 31, provinces
    assert all(int(row["planned_count"]) > 0 for row in rows)
    assert not [
        row
        for row in rows
        if re.search(r"(招生专业|合计|总计)", row["major_name"])
    ]
    print("PASS NEU", len(rows), "rows", len(provinces), "provinces")


def check_manual_import_parsers():
    sufe = sufe_records(
        pd.DataFrame(
            [
                {
                    "年份": "2026",
                    "省市": "上海",
                    "科类名称": "综合改革",
                    "院系名称": "金融学院",
                    "专业名称": "金融学",
                    "计划数": "3",
                    "备注": "",
                }
            ]
        )
    )
    assert len(sufe) == 1 and sufe[0]["planned_count"] == 3
    hebut = hebut_records(
        pd.DataFrame(
            [
                {
                    "年份": "2026",
                    "省份": "河北",
                    "学院": "机械工程学院",
                    "专业": "机械设计制造及其自动化",
                    "科类": "物理类",
                    "批次": "本科批",
                    "计划数": "4",
                }
            ]
        ),
        "synthetic",
    )
    assert len(hebut) == 1 and hebut[0]["planned_count"] == 4
    print("PASS manual SUFE/HEBUT import parsers")


def check_ocr_validation():
    result_path = (
        ROOT / "results" / "validation" / "ocr_validation_result.json"
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["sample_rows"] == 144, result
    assert result["verified_rows"] == 144, result
    assert result["correct_rows"] == 144, result
    assert result["incorrect_rows"] == 0, result
    assert result["accuracy"] >= 0.95, result
    assert result["threshold_95_reached"] is True, result
    assert (
        ROOT / "results" / "validation" / "ocr_validation_sample_144.csv"
    ).exists()
    sheets = list(
        (ROOT / "results" / "validation" / "contact_sheets").glob("*.png")
    )
    assert len(sheets) == 12, len(sheets)
    print(
        "PASS OCR validation",
        result["verified_rows"],
        "rows",
        result["accuracy"],
        "accuracy",
    )


def check_database_screenshot():
    path = ROOT / "results" / "database" / "datagrip_query_result.png"
    with Image.open(path) as image:
        assert image.width >= 1000 and image.height >= 500, image.size
        size = image.size
    print("PASS DataGrip screenshot", size[0], "x", size[1])


def check_database():
    config = get_database_config(prompt=False)
    if not config.password:
        print("SKIP MySQL tests: MYSQL_PASSWORD not configured")
        return
    connection = connect_database(prompt=False)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*), COUNT(DISTINCT school),
                       SUM(planned_count)
                FROM admission_plan_v2
                WHERE admission_year = 2026
                """
            )
            rows, schools, planned = cursor.fetchone()
        assert rows == 3047, rows
        assert schools == 5, schools
        assert int(planned) == 17447, planned
        print("PASS MySQL", rows, "rows", schools, "schools", planned, "planned")
    finally:
        connection.close()


def check_secrets():
    suspicious = []
    for path in ROOT.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(
            r"(?i)(?:password|passwd|pwd)\s*=\s*['\"]([^'\"]+)['\"]",
            text,
        ):
            value = match.group(1)
            if value and value not in {"input", "hidden", "password"}:
                suspicious.append(path.name)
    assert not suspicious, suspicious
    print("PASS no hard-coded DB secrets")


def check_imports():
    required = [
        "bs4",
        "lxml",
        "mysql.connector",
        "numpy",
        "paddle",
        "paddleocr",
        "pandas",
        "PIL",
        "requests",
    ]
    for name in required:
        module = __import__(name)
        print("PASS import", name, getattr(module, "__version__", ""))


def main():
    ensure_utf8_stdio()
    check_python_files()
    check_imports()
    check_secrets()
    check_nuc_assets()
    check_nuc()
    check_sxnu()
    check_neu()
    check_manual_import_parsers()
    check_ocr_validation()
    check_database_screenshot()
    check_database()
    print("ALL LOCAL CHECKS PASSED")


if __name__ == "__main__":
    main()
