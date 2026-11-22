"""河北工业大学 2026 招生计划采集与官方导出结果导入。

截至审计时刻，校方招生子站对当前网络返回 HTTP 403。脚本记录真实证据，
支持在学校恢复访问或用户人工保存官方结果后导入 HTML/CSV。
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from admissions_common import (
    RESULTS,
    connect_database,
    ensure_utf8_stdio,
    make_session,
    normalize,
    write_csv,
    write_json,
)
from gaokao_enrollment import write_gaokao_records


OFFICIAL_URL = "https://zs.hebut.edu.cn/"
MAIN_SOURCE = "https://www.hebut.edu.cn/"
PLAN_PAGE = "https://zs.hebut.edu.cn/Baokao/fenshu.html"
OUTPUT_ROOT = RESULTS / "hebut"


def check_source() -> dict[str, object]:
    session = make_session()
    evidence = {
        "official_url": OFFICIAL_URL,
        "main_source": MAIN_SOURCE,
        "plan_page": PLAN_PAGE,
        "status": "blocked_http_403",
        "notes": (
            "校方本科生招生入口由学校主站公开发布，但招生子站及其"
            "“录取分数及计划”公开路径均返回 403。"
        ),
    }
    for name, url in (
        ("main", MAIN_SOURCE),
        ("admissions", OFFICIAL_URL),
        ("plan_page", PLAN_PAGE),
    ):
        try:
            response = session.get(url, timeout=20, allow_redirects=True)
            response.encoding = response.apparent_encoding or "utf-8"
            soup = BeautifulSoup(response.text, "html.parser")
            evidence[name] = {
                "requested_url": url,
                "final_url": response.url,
                "http_status": response.status_code,
                "title": soup.title.get_text(" ", strip=True)
                if soup.title
                else "",
                "bytes": len(response.content),
            }
        except Exception as exc:
            evidence[name] = {"requested_url": url, "error": str(exc)}
    write_json(OUTPUT_ROOT / "source_evidence.json", evidence)
    return evidence


def records_from_frame(frame: pd.DataFrame, source: str) -> list[dict[str, object]]:
    aliases = {
        "province": ["省份", "省市", "province"],
        "college": ["学院", "院系", "college_name"],
        "major": ["专业", "专业名称", "major_name"],
        "subject": ["科类", "科类名称", "subject_type"],
        "batch": ["批次", "录取批次", "batch_name"],
        "count": ["计划数", "招生计划", "计划人数", "planned_count"],
        "year": ["年份", "admission_year"],
    }
    columns = {}
    for key, names in aliases.items():
        for name in names:
            if name in frame.columns:
                columns[key] = name
                break
    required = {"province", "major", "count"}
    if not required.issubset(columns):
        return []
    records = []
    for row_number, row in frame.iterrows():
        year = str(row[columns.get("year", "")]).strip() if "year" in columns else "2026"
        if year and year not in {"2026", "2026.0"}:
            continue
        count_text = re.sub(r"\D", "", str(row[columns["count"]]))
        if not count_text or int(count_text) <= 0:
            continue
        records.append(
            {
                "admission_year": 2026,
                "school": "河北工业大学",
                "province": normalize(row[columns["province"]]),
                "college_name": normalize(row[columns["college"]])
                if "college" in columns
                else "",
                "major_code": "",
                "major_name": normalize(row[columns["major"]]),
                "subject_type": normalize(row[columns["subject"]])
                if "subject" in columns
                else "",
                "batch_name": normalize(row[columns["batch"]])
                if "batch" in columns
                else "",
                "plan_type": "",
                "selection_subject": "",
                "fee_text": "",
                "planned_count": int(count_text),
                "source_url": source,
                "source_image": "",
                "source_row": int(row_number) + 1,
                "source_box": [],
                "extraction_method": "HTML-MANUAL",
                "review_status": "待复核",
                "review_reason": "校方子站当前拒绝自动访问，来自人工保存的官方结果",
            }
        )
    return records


def parse_input(path: Path) -> list[dict[str, object]]:
    source = f"file:{path.resolve()}"
    if path.suffix.lower() in {".html", ".htm"}:
        tables = pd.read_html(str(path))
        for table in tables:
            records = records_from_frame(table, source)
            if records:
                return records
        raise ValueError("HTML 中未找到可识别的招生计划表")
    if path.suffix.lower() == ".csv":
        return records_from_frame(
            pd.read_csv(path, dtype=str).fillna(""),
            source,
        )
    raise ValueError("仅支持 .html/.htm/.csv")


def main() -> None:
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-source", action="store_true")
    parser.add_argument(
        "--henan-official",
        action="store_true",
        help="采集河南省阳光高考官方院校计划页面",
    )
    parser.add_argument("--input", type=Path)
    parser.add_argument("--write-db", action="store_true")
    args = parser.parse_args()
    evidence = check_source() if args.check_source else None
    if args.henan_official:
        from provincial_henan import fetch_official_plans

        records = fetch_official_plans("河北工业大学")
        write_csv(OUTPUT_ROOT / "hebut_henan_candidates.csv", records)
        print(
            "HENAN_ROWS", len(records),
            "PLANNED", sum(row["planned_count"] for row in records),
        )
        if args.write_db:
            connection = connect_database()
            try:
                result = write_gaokao_records(connection, records)
                print(
                    "GAOKAO_IMPORTED",
                    result["inserted"],
                    "SKIPPED",
                    result["existing_skipped"],
                    "TARGET",
                    "gaokao_2026_enrollment",
                )
            finally:
                connection.close()
        return
    if args.input is None:
        print(evidence or {"status": "not_checked"})
        print(
            "官方入口当前需要人工浏览器访问。保存 2026 年官方结果后运行 "
            "python hebut.py --input <文件> [--write-db]"
        )
        return
    records = parse_input(args.input)
    write_csv(OUTPUT_ROOT / "hebut_candidates.csv", records)
    print("ROWS", len(records), "PLANNED", sum(row["planned_count"] for row in records))
    if args.write_db:
        connection = connect_database()
        try:
            result = write_gaokao_records(connection, records)
            print(
                "GAOKAO_IMPORTED",
                result["inserted"],
                "SKIPPED",
                result["existing_skipped"],
                "TARGET",
                "gaokao_2026_enrollment",
            )
        finally:
            connection.close()


if __name__ == "__main__":
    main()
