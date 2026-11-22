"""Migrate existing 2026 plans into gaokao_2026_enrollment."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from admissions_common import (
    RESULTS,
    connect_database,
    ensure_utf8_stdio,
    load_csv_records,
    write_csv,
    write_json,
)
from gaokao_enrollment import (
    GAOKAO_SCHEMA,
    IDENTITY_COLUMNS,
    LEDGER_TABLE,
    OPERATE_FLAG,
    OPERATE_ID,
    OPERATE_IP,
    TARGET_COLUMNS,
    TARGET_TABLE,
    write_gaokao_records,
)


SOURCE_TABLE = "admission_plan_v2"
SOURCE_CSVS = {
    "中北大学": RESULTS / "nuc" / "nuc_candidates_final.csv",
    "山西师范大学": RESULTS / "sxnu" / "sxnu_candidates.csv",
    "东北大学": RESULTS / "neu" / "neu_candidates.csv",
    "上海财经大学": RESULTS / "sufe" / "sufe_henan_candidates.csv",
    "河北工业大学": RESULTS / "hebut" / "hebut_henan_candidates.csv",
}
REPORT_ROOT = RESULTS / "gaokao_2026_enrollment"
COMPARISON_FIELDS = [
    "school",
    "source_records",
    "target_records",
    "records_match",
    "source_planned",
    "target_planned",
    "planned_match",
    "source_provinces",
    "target_provinces",
    "provinces_match",
    "scope_note",
]


def source_from_table(connection) -> list[dict[str, object]]:
    columns = [
        "admission_year",
        "school",
        "province",
        "college_name",
        "major_code",
        "major_name",
        "subject_type",
        "batch_name",
        "plan_type",
        "selection_subject",
        "planned_count",
        "source_url",
        "source_image",
        "source_row",
        "review_status",
        "record_hash",
    ]
    with connection.cursor(dictionary=True) as cursor:
        cursor.execute(
            f"SELECT {', '.join(f'`{column}`' for column in columns)} "
            f"FROM `{SOURCE_TABLE}` WHERE admission_year = 2026"
        )
        return cursor.fetchall()


def source_from_csv() -> list[dict[str, object]]:
    rows = []
    for school, path in SOURCE_CSVS.items():
        school_rows = load_csv_records(path)
        for row in school_rows:
            row["school"] = school
        rows.extend(school_rows)
    return rows


def load_source(connection, mode: str) -> tuple[list[dict[str, object]], str]:
    if mode in {"auto", "table"}:
        try:
            rows = source_from_table(connection)
            if rows:
                return rows, SOURCE_TABLE
            if mode == "table":
                raise RuntimeError(f"{SOURCE_TABLE} 没有 2026 数据")
        except Exception:
            if mode == "table":
                raise
    return source_from_csv(), "CSV"


def summarize(records: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped = defaultdict(
        lambda: {"records": 0, "planned_count": 0, "provinces": set()}
    )
    for record in records:
        school = str(record["school"])
        grouped[school]["records"] += 1
        grouped[school]["planned_count"] += int(record["planned_count"])
        grouped[school]["provinces"].add(str(record["province"]))
    return [
        {
            "school": school,
            "records": value["records"],
            "planned_count": value["planned_count"],
            "province_count": len(value["provinces"]),
            "provinces": sorted(value["provinces"]),
        }
        for school, value in sorted(grouped.items())
    ]


def target_summary(connection) -> list[dict[str, object]]:
    with connection.cursor(dictionary=True) as cursor:
        cursor.execute(
            f"""
            SELECT UNIV_NAME AS school,
                   COUNT(*) AS records,
                   SUM(ENROLLMENT_NUM) AS planned_count,
                   COUNT(DISTINCT REGION_NAME) AS province_count
            FROM `{TARGET_TABLE}`
            WHERE GAOKAO_DATE = '2026'
            GROUP BY UNIV_NAME
            ORDER BY UNIV_NAME
            """
        )
        summary = cursor.fetchall()
        for row in summary:
            cursor.execute(
                f"""
                SELECT DISTINCT REGION_NAME
                FROM `{TARGET_TABLE}`
                WHERE GAOKAO_DATE = '2026' AND UNIV_NAME = %s
                ORDER BY REGION_NAME
                """,
                (row["school"],),
            )
            row["provinces"] = [item["REGION_NAME"] for item in cursor.fetchall()]
    return summary


def target_duplicates(connection) -> list[dict[str, object]]:
    columns = ", ".join(f"`{column}`" for column in IDENTITY_COLUMNS)
    with connection.cursor(dictionary=True) as cursor:
        cursor.execute(
            f"""
            SELECT {columns}, COUNT(*) AS copies
            FROM `{TARGET_TABLE}`
            GROUP BY {columns}
            HAVING COUNT(*) > 1
            ORDER BY copies DESC
            """
        )
        return cursor.fetchall()


def schema_details(connection) -> dict[str, object]:
    with connection.cursor(dictionary=True) as cursor:
        cursor.execute(f"SHOW CREATE TABLE `{TARGET_TABLE}`")
        create_row = cursor.fetchone()
        cursor.execute(
            """
            SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT,
                   CHARACTER_SET_NAME, COLLATION_NAME
            FROM information_schema.columns
            WHERE table_schema = DATABASE() AND table_name = %s
            ORDER BY ORDINAL_POSITION
            """,
            (TARGET_TABLE,),
        )
        columns = cursor.fetchall()
        cursor.execute(
            """
            SELECT INDEX_NAME, COLUMN_NAME, NON_UNIQUE, SEQ_IN_INDEX
            FROM information_schema.statistics
            WHERE table_schema = DATABASE() AND table_name = %s
            ORDER BY INDEX_NAME, SEQ_IN_INDEX
            """,
            (TARGET_TABLE,),
        )
        indexes = cursor.fetchall()
    return {
        "create_table": create_row.get("Create Table")
        or next(iter(create_row.values())),
        "columns": columns,
        "indexes": indexes,
    }


def compare_summaries(
    source: list[dict[str, object]],
    target: list[dict[str, object]],
) -> list[dict[str, object]]:
    target_by_school = {row["school"]: row for row in target}
    rows = []
    for source_row in source:
        target_row = target_by_school.get(source_row["school"], {})
        rows.append(
            {
                "school": source_row["school"],
                "source_records": source_row["records"],
                "target_records": target_row.get("records", 0),
                "records_match": source_row["records"]
                == target_row.get("records", 0),
                "source_planned": source_row["planned_count"],
                "target_planned": int(target_row.get("planned_count") or 0),
                "planned_match": source_row["planned_count"]
                == int(target_row.get("planned_count") or 0),
                "source_provinces": source_row["province_count"],
                "target_provinces": target_row.get("province_count", 0),
                "provinces_match": source_row["province_count"]
                == target_row.get("province_count", 0),
                "scope_note": (
                    "仅覆盖河南省"
                    if source_row["school"]
                    in {"上海财经大学", "河北工业大学"}
                    and source_row["provinces"] == ["河南"]
                    else ""
                ),
            }
        )
    return rows


def main() -> None:
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-number", type=int, required=True)
    parser.add_argument(
        "--source",
        choices=("auto", "table", "csv"),
        default="auto",
    )
    args = parser.parse_args()

    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    connection = connect_database()
    try:
        records, source_kind = load_source(connection, args.source)
        source_counts = summarize(records)
        operate_time = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        import_result = write_gaokao_records(
            connection,
            records,
            operate_time=operate_time,
        )
        after_source = summarize(records)
        after_target = target_summary(connection)
        comparison = compare_summaries(after_source, after_target)
        duplicates = target_duplicates(connection)
        schema = schema_details(connection)

        write_csv(
            REPORT_ROOT / f"school_comparison_run_{args.run_number}.csv",
            comparison,
            COMPARISON_FIELDS,
        )
        write_csv(
            REPORT_ROOT / f"conflicts_run_{args.run_number}.csv",
            import_result["conflicts"],
            [
                "reason",
                "UNIV_NAME",
                "REGION_NAME",
                "BRANCH_NAME",
                "ADMISSIONBATCH_NAME",
                "SPECIALTY_NAME",
                "ENROLLMENT_DESC",
                "ENROLLMENT_NUM",
                "source_record_hash",
                "source_url",
                "source_row",
                "source_college",
                "source_major_code",
            ],
        )
        payload = {
            "run_number": args.run_number,
            "source_kind": source_kind,
            "operate_time": operate_time,
            "source_records": len(records),
            "source_schools": source_counts,
            "import_result": import_result,
            "target_schools": after_target,
            "comparison": comparison,
            "duplicate_target_groups": len(duplicates),
            "duplicate_target_rows": sum(int(row["copies"]) for row in duplicates),
            "missing_fields": import_result["missing_fields"],
            "univ_id": "NULL（未找到可靠的院校 ID 映射）",
            "enrollment_id": "NULL（未找到可靠的招生计划 ID 映射）",
            "constants": {
                "OPERATE_ID": OPERATE_ID,
                "OPERATE_FLAG": OPERATE_FLAG,
                "OPERATE_IP": OPERATE_IP,
            },
            "schema": schema,
        }
        output = REPORT_ROOT / f"run_{args.run_number}.json"
        write_json(output, payload)
        print(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
        print("OUTPUT", output)
    finally:
        connection.close()


if __name__ == "__main__":
    main()
