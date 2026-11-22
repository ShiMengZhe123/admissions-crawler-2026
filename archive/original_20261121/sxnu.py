"""抓取山西师范大学 2026 年本科招生来源计划主表。"""

import argparse
import re
from collections import Counter
from getpass import getpass
from io import StringIO
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd
from lxml import html


URL = "https://zsb.sxnu.edu.cn/info/1199/4459.htm"
YEAR = 2026
SCHOOL = "山西师范大学"
HEADER = ("科类", "计划类别", "专业", "总计", "不分省")
ROW_SAMPLE = ("文史/历史类", "普通类", "020101", "经济学")
TOTAL = "总计"

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS admission_plan (
    admission_year SMALLINT UNSIGNED NOT NULL,
    school VARCHAR(40) NOT NULL,
    province VARCHAR(24) NOT NULL,
    subject_type VARCHAR(40) NOT NULL,
    plan_type VARCHAR(40) NOT NULL,
    major_code VARCHAR(16) NOT NULL,
    major_name VARCHAR(160) NOT NULL,
    planned_count INT UNSIGNED NOT NULL,
    source_url VARCHAR(512) NOT NULL,
    extraction_method VARCHAR(12) NOT NULL,
    PRIMARY KEY (admission_year, school, province, subject_type,
                 plan_type, major_code, major_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin
"""

INSERT_ROWS = """
INSERT INTO admission_plan (
    admission_year, school, province, subject_type, plan_type,
    major_code, major_name, planned_count, source_url, extraction_method
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


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
    if not any(str(YEAR) in node.text_content() for node in document.xpath("//title")):
        raise ValueError("网页标题没有 2026 年，请检查来源页面。")

    for row in document.xpath("//table//tr"):
        cells = [compact(cell.text_content()) for cell in row.xpath("./th|./td")]
        if tuple(cells[:5]) == HEADER:
            table = row.xpath("ancestor::table[1]")[0]
            # 统一使用普通单元格，避免表头被 read_html 自动移到列名里。
            for cell in table.xpath(".//th"):
                cell.tag = "td"
            for section in table.xpath("./thead|./tfoot"):
                section.tag = "tbody"
            table_text = html.tostring(table, encoding="unicode")
            return pd.read_html(StringIO(table_text), flavor="lxml",
                                keep_default_na=False, displayed_only=False)[0]

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

    for row_number, row in enumerate(table.itertuples(index=False, name=None), start=1):
        labels = tuple(compact(value) for value in row[:5])
        if labels == HEADER:
            provinces = tuple(compact(value) for value in row[4:])
            if len(provinces) != len(set(provinces)) or "山西" not in provinces or "" in provinces:
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
        match = re.fullmatch(r"[（(]\s*([0-9A-Za-z]+)\s*[)）]\s*(.+)", major)
        if not match or not plan_type:
            raise ValueError(f"第 {row_number} 行专业或计划类别无法解析。")
        major_code, major_name = match.groups()

        counts = tuple(parse_count(value) for value in row[4:])
        if sum(counts) != parse_count(row[3]):
            raise ValueError(f"第 {row_number} 行的分省人数与该行总计不符。")
        for province, count in zip(provinces, counts, strict=True):
            if count == 0:
                continue
            key = (YEAR, SCHOOL, province, subject, plan_type, major_code, major_name)
            if key in keys:
                raise ValueError(f"第 {row_number} 行出现重复的招生明细。")
            keys.add(key)
            records.append((*key, count, URL, "HTML"))
            actual[province] += count

    if provinces is None or expected != (sum(actual.values()), *(actual[p] for p in provinces)):
        raise ValueError("解析后的人数与官网总计或分省合计不一致。")
    sample = (YEAR, SCHOOL, "山西", *ROW_SAMPLE, 62, URL, "HTML")
    if sample not in records:
        raise ValueError("官网样例未通过校验，山西省文史/历史类经济学应为 62 人。")
    return records


def save_to_mysql(records, host, port, user):
    import mysql.connector

    password = getpass("请输入 MySQL 密码（输入不显示）: ")
    with mysql.connector.connect(host=host, port=port, user=user, password=password,
                                 database="admissions", charset="utf8mb4",
                                 connection_timeout=10) as connection:
        with connection.cursor() as cursor:
            cursor.execute(CREATE_TABLE)
            # 先完整解析和校验，再在同一事务中更新该来源的明细。
            cursor.execute(
                "DELETE FROM admission_plan WHERE admission_year = %s AND school = %s"
                " AND source_url = %s",
                (YEAR, SCHOOL, URL),
            )
            cursor.executemany(INSERT_ROWS, records)
        connection.commit()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="抓取并校验，跳过数据库")
    parser.add_argument("--html", type=Path, help="读取另存为的官网 HTML")
    parser.add_argument("--host", default="127.0.0.1", help="MySQL 主机")
    parser.add_argument("--port", type=int, default=3306, help="MySQL 端口")
    parser.add_argument("--user", default="root", help="MySQL 用户名")
    args = parser.parse_args()

    try:
        records = parse_plan(get_page(args.html))
        total = sum(row[7] for row in records)
        print(f"解析通过：{len(records)} 条招生明细，计划合计 {total} 人。")
        print("核对样例：山西｜文史/历史类｜普通类｜020101 经济学｜62 人")
        if not args.check:
            save_to_mysql(records, args.host, args.port, args.user)
            print(f"已提交 {len(records)} 条明细到 admissions.admission_plan。")
    except (OSError, ValueError) as error:
        parser.exit(1, f"运行失败：{error}\n")


if __name__ == "__main__":
    main()
