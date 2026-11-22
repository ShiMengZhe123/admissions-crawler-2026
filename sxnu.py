"""山西师范大学 2026 年本科招生来源计划爬虫。

官网当前为 HTML 主表。脚本先完整校验分省人数和官网样例，再选择是否写库。
"""

from __future__ import annotations

import argparse
import re
from collections import Counter
from io import StringIO
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd
from lxml import html

from admissions_common import (
    connect_database,
    ensure_utf8_stdio,
    make_session,
    normalize,
    write_csv,
)
from gaokao_enrollment import write_gaokao_records


URL = "https://zsb.sxnu.edu.cn/info/1199/4459.htm"
YEAR = 2026
SCHOOL = "山西师范大学"
HEADER = ("科类", "计划类别", "专业", "总计", "不分省")
ROW_SAMPLE = ("文史/历史类", "普通类", "020101", "经济学")
TOTAL = "总计"


def compact(value):
    return "".join(str(value).split())


def get_page(local_html):
    if local_html:
        return local_html.read_bytes()
    request = Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=30) as response:
        return response.read()


def find_plan_table(page):
    document = html.fromstring(page)
    titles = " ".join(node.text_content() for node in document.xpath("//title"))
    if str(YEAR) not in titles:
        raise ValueError("网页标题没有 2026 年，请检查来源页面。")
    for row in document.xpath("//table//tr"):
        cells = [compact(cell.text_content()) for cell in row.xpath("./th|./td")]
        if tuple(cells[:5]) == HEADER:
            table = row.xpath("ancestor::table[1]")[0]
            for cell in table.xpath(".//th"):
                cell.tag = "td"
            for section in table.xpath("./thead|./tfoot"):
                section.tag = "tbody"
            table_text = html.tostring(table, encoding="unicode")
            return pd.read_html(
                StringIO(table_text),
                flavor="lxml",
                keep_default_na=False,
                displayed_only=False,
            )[0]
    raise ValueError("未找到包含科类、计划类别、专业和总计的主表。")


def parse_count(value):
    value = compact(value)
    if value in {"", "-", "—", "–"}:
        return 0
    if re.fullmatch(r"[0-9]+(?:\.0+)?", value):
        return int(value.split(".")[0])
    raise ValueError(f"无法解析计划人数 {value!r}")


def parse_plan(page):
    table = find_plan_table(page)
    provinces = None
    expected = None
    actual = Counter()
    records = []
    keys = set()

    for row_number, row in enumerate(
        table.itertuples(index=False, name=None), start=1
    ):
        labels = tuple(compact(value) for value in row[:5])
        if labels == HEADER:
            provinces = tuple(compact(value) for value in row[4:])
            if (
                len(provinces) != len(set(provinces))
                or "山西" not in provinces
                or "" in provinces
            ):
                raise ValueError("省份表头重复或缺失。")
            continue
        if provinces is None or all(compact(value) == "" for value in row):
            continue
        subject, plan_type, major = (str(value).strip() for value in row[:3])
        if subject.startswith(("注：", "注:")):
            continue
        if TOTAL in (compact(subject), compact(plan_type), compact(major)):
            expected = tuple(parse_count(value) for value in row[3:])
            continue
        match = re.fullmatch(
            r"[（(]\s*([0-9A-Za-z]+)\s*[)）]\s*(.+)", major
        )
        if not match or not plan_type:
            raise ValueError(f"第 {row_number} 行专业或计划类别无法解析。")
        major_code, major_name = match.groups()
        counts = tuple(parse_count(value) for value in row[4:])
        if sum(counts) != parse_count(row[3]):
            raise ValueError(
                f"第 {row_number} 行的分省人数与该行总计不符。"
            )
        for province, count in zip(provinces, counts, strict=True):
            if count == 0:
                continue
            key = (
                YEAR,
                SCHOOL,
                province,
                subject,
                plan_type,
                major_code,
                major_name,
            )
            if key in keys:
                raise ValueError(f"第 {row_number} 行出现重复的招生明细。")
            keys.add(key)
            records.append(
                {
                    "admission_year": YEAR,
                    "school": SCHOOL,
                    "province": province,
                    "college_name": "",
                    "major_code": major_code,
                    "major_name": normalize(major_name),
                    "subject_type": normalize(subject),
                    "batch_name": "",
                    "plan_type": normalize(plan_type),
                    "selection_subject": "",
                    "fee_text": "",
                    "planned_count": int(count),
                    "source_url": URL,
                    "source_image": "",
                    "source_row": row_number,
                    "source_box": [],
                    "extraction_method": "HTML",
                    "review_status": "自动校验通过",
                    "review_reason": "",
                }
            )
            actual[province] += count

    if provinces is None or expected != (
        sum(actual.values()),
        *(actual[province] for province in provinces),
    ):
        raise ValueError("解析后的人数与官网总计或分省合计不一致。")
    sample = next(
        (
            row
            for row in records
            if (
                row["province"],
                row["subject_type"],
                row["plan_type"],
                row["major_code"],
                row["major_name"],
            )
            == ("山西", *ROW_SAMPLE)
        ),
        None,
    )
    if not sample or sample["planned_count"] != 62:
        raise ValueError("官网样例未通过校验：山西/文史历史类/经济学应为 62 人。")
    return records


def main() -> None:
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="只抓取并校验")
    parser.add_argument("--html", type=Path, help="读取另存为的官网 HTML")
    parser.add_argument("--write-db", action="store_true")
    args = parser.parse_args()
    try:
        records = parse_plan(get_page(args.html))
        total = sum(row["planned_count"] for row in records)
        print(
            f"解析通过：{len(records)} 条招生明细，计划合计 {total} 人。"
        )
        write_csv(Path("results") / "sxnu" / "sxnu_candidates.csv", records)
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
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"运行失败：{error}\n")


if __name__ == "__main__":
    main()
