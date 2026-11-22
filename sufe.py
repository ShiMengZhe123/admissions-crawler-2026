"""上海财经大学 2026 招生计划采集与人工查询结果导入。

官网查询页要求四位数字验证码。本脚本不会破解或绕过验证码，只在校方
公开页面允许的流程下支持人工完成查询后导入 HTML 或 CSV。
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
    request_with_retries,
    write_csv,
    write_json,
)
from gaokao_enrollment import write_gaokao_records


SOURCE_PAGE = "https://zs.sufe.edu.cn/zsjh/list.htm"
PLAN_HIGHLIGHTS = (
    "https://zs.sufe.edu.cn/0b/08/c3343a264968/page.htm"
)
PROGRAM_CATALOG = (
    "https://zs.sufe.edu.cn/08/c0/c3343a264384/page.htm"
)
QUERY_IFRAME = (
    "https://zs.sufe.edu.cn/_web/_apps/commonquery/commonquery/"
    "api/queryMatch/26.rst?_p=YXM9OTYmdD02MDUmcD0xJm09TiY_&mongo=false"
)
OUTPUT_ROOT = RESULTS / "sufe"


def source_evidence() -> dict[str, object]:
    session = make_session()
    evidence = {
        "source_page": SOURCE_PAGE,
        "query_iframe": QUERY_IFRAME,
        "status": "blocked_by_captcha",
        "captcha_required": True,
        "notes": (
            "校方历年招生计划查询使用 commonquery/26，要求四位数字验证码；"
            "未尝试绕过。招生亮点页没有分省明细；专业目录页当前重定向到"
            " page.psp 并返回 410，因此不作为数据源。"
        ),
    }
    for name, url in (
        ("page", SOURCE_PAGE),
        ("iframe", QUERY_IFRAME),
        ("plan_highlights", PLAN_HIGHLIGHTS),
        ("program_catalog", PROGRAM_CATALOG),
    ):
        try:
            response = request_with_retries(session, url)
            response.encoding = response.apparent_encoding or "utf-8"
            soup = BeautifulSoup(response.text, "html.parser")
            evidence[name] = {
                "url": response.url,
                "http_status": response.status_code,
                "title": soup.title.get_text(" ", strip=True)
                if soup.title
                else "",
                "bytes": len(response.content),
                "has_validate_image": "validateimage" in response.text,
                "has_2026_option": "2026" in response.text,
            }
        except Exception as exc:
            evidence[name] = {"url": url, "error": str(exc)}
    write_json(OUTPUT_ROOT / "source_evidence.json", evidence)
    return evidence


def records_from_frame(frame: pd.DataFrame) -> list[dict[str, object]]:
    aliases = {
        "year": ["年份", "admission_year"],
        "province": ["省市", "省份", "province"],
        "subject": ["科类名称", "科类", "subject_type"],
        "college": ["院系名称", "学院", "college_name"],
        "major": ["专业名称", "专业", "major_name"],
        "count": ["计划数", "planned_count"],
        "note": ["备注", "note"],
    }
    columns = {}
    for key, names in aliases.items():
        for name in names:
            if name in frame.columns:
                columns[key] = name
                break
    required = {"year", "province", "subject", "major", "count"}
    if not required.issubset(columns):
        raise ValueError(f"结果缺少字段: {sorted(required - set(columns))}")
    records = []
    for row_number, row in frame.iterrows():
        if str(row[columns["year"]]).strip() != "2026":
            continue
        count_text = re.sub(r"\D", "", str(row[columns["count"]]))
        if not count_text or int(count_text) <= 0:
            continue
        records.append(
            {
                "admission_year": 2026,
                "school": "上海财经大学",
                "province": normalize(row[columns["province"]]),
                "college_name": normalize(row[columns.get("college", "")])
                if "college" in columns
                else "",
                "major_code": "",
                "major_name": normalize(row[columns["major"]]),
                "subject_type": normalize(row[columns["subject"]]),
                "batch_name": "",
                "plan_type": "",
                "selection_subject": "",
                "fee_text": "",
                "planned_count": int(count_text),
                "source_url": SOURCE_PAGE,
                "source_image": "",
                "source_row": int(row_number) + 1,
                "source_box": [],
                "extraction_method": "HTML-MANUAL",
                "review_status": "待复核",
                "review_reason": "官方查询结果人工完成验证码后导入",
            }
        )
    return records


def parse_input(path: Path) -> list[dict[str, object]]:
    if path.suffix.lower() in {".html", ".htm"}:
        tables = pd.read_html(str(path))
        target = next(
            (
                table
                for table in tables
                if {"年份", "省市", "专业名称", "计划数"}.issubset(table.columns)
            ),
            None,
        )
        if target is None:
            raise ValueError("HTML 中未找到上海财大招生计划结果表")
        return records_from_frame(target)
    if path.suffix.lower() == ".csv":
        frame = pd.read_csv(path, dtype=str).fillna("")
        return records_from_frame(frame)
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
    evidence = source_evidence() if args.check_source else None
    if args.henan_official:
        from provincial_henan import fetch_official_plans

        records = fetch_official_plans("上海财经大学")
        write_csv(OUTPUT_ROOT / "sufe_henan_candidates.csv", records)
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
        print("官网查询需要人工完成四位验证码。")
        print(f"查询入口: {SOURCE_PAGE}")
        print(
            "完成查询后，将结果表保存为 HTML/CSV，再运行 "
            "python sufe.py --input <文件> [--write-db]"
        )
        if evidence:
            print(evidence)
        return
    records = parse_input(args.input)
    write_csv(OUTPUT_ROOT / "sufe_candidates.csv", records)
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
