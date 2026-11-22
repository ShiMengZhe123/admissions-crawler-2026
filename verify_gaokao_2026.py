"""Verify gaokao_2026_enrollment and export DataGrip-ready result sets."""

from __future__ import annotations

import json
from pathlib import Path

from admissions_common import (
    RESULTS,
    connect_database,
    ensure_utf8_stdio,
    write_csv,
    write_json,
)
from gaokao_enrollment import TARGET_COLUMNS, TARGET_TABLE


REPORT_ROOT = RESULTS / "gaokao_2026_enrollment"


def main() -> None:
    ensure_utf8_stdio()
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    connection = connect_database()
    try:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute(
                f"""
                SELECT
                    UNIV_NAME,
                    COUNT(*) AS RECORD_COUNT,
                    SUM(ENROLLMENT_NUM) AS PLANNED_TOTAL,
                    COUNT(DISTINCT REGION_NAME) AS PROVINCE_COUNT
                FROM `{TARGET_TABLE}`
                WHERE GAOKAO_DATE = '2026'
                GROUP BY UNIV_NAME
                UNION ALL
                SELECT
                    '合计',
                    COUNT(*),
                    SUM(ENROLLMENT_NUM),
                    COUNT(DISTINCT REGION_NAME)
                FROM `{TARGET_TABLE}`
                WHERE GAOKAO_DATE = '2026'
                ORDER BY CASE WHEN UNIV_NAME = '合计' THEN 1 ELSE 0 END,
                         UNIV_NAME
                """
            )
            school_summary = cursor.fetchall()
            write_csv(
                REPORT_ROOT / "final_school_summary.csv",
                school_summary,
                [
                    "UNIV_NAME",
                    "RECORD_COUNT",
                    "PLANNED_TOTAL",
                    "PROVINCE_COUNT",
                ],
            )

            cursor.execute(
                f"""
                SELECT UNIV_NAME, REGION_NAME, COUNT(*) AS RECORD_COUNT,
                       SUM(ENROLLMENT_NUM) AS PLANNED_TOTAL
                FROM `{TARGET_TABLE}`
                WHERE GAOKAO_DATE = '2026'
                GROUP BY UNIV_NAME, REGION_NAME
                ORDER BY UNIV_NAME, REGION_NAME
                """
            )
            province_rows = cursor.fetchall()
            write_csv(
                REPORT_ROOT / "final_province_coverage.csv",
                province_rows,
                [
                    "UNIV_NAME",
                    "REGION_NAME",
                    "RECORD_COUNT",
                    "PLANNED_TOTAL",
                ],
            )

            cursor.execute(
                f"""
                SELECT {', '.join(f'`{column}`' for column in TARGET_COLUMNS)}
                FROM `{TARGET_TABLE}`
                WHERE GAOKAO_DATE = '2026'
                ORDER BY UNIV_NAME, REGION_NAME, SPECIALTY_NAME
                """
            )
            details = cursor.fetchall()
            write_csv(
                REPORT_ROOT / "final_details.csv",
                details,
                TARGET_COLUMNS,
            )

            cursor.execute(
                f"""
                SELECT
                    COUNT(*) AS TOTAL_ROWS,
                    SUM(OPERATE_ID = 'GK010101000000000000') AS VALID_OPERATE_ID,
                    SUM(OPERATE_FLAG = '1') AS VALID_OPERATE_FLAG,
                    SUM(OPERATE_IP = '127.0.0.1') AS VALID_OPERATE_IP,
                    SUM(OPERATE_TIME REGEXP '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}} '
                        '[0-9]{{2}}:[0-9]{{2}}:[0-9]{{2}}$') AS VALID_OPERATE_TIME,
                    SUM(UNIV_ID IS NULL) AS NULL_UNIV_ID,
                    SUM(ENROLLMENT_ID IS NULL) AS NULL_ENROLLMENT_ID,
                    SUM(BRANCH_NAME IS NULL OR BRANCH_NAME = '') AS EMPTY_BRANCH,
                    SUM(ADMISSIONBATCH_NAME IS NULL OR ADMISSIONBATCH_NAME = '')
                        AS EMPTY_BATCH,
                    SUM(ENROLLMENT_DESC IS NULL OR ENROLLMENT_DESC = '')
                        AS EMPTY_DESC
                FROM `{TARGET_TABLE}`
                WHERE GAOKAO_DATE = '2026'
                """
            )
            validation = cursor.fetchone()

            identity = [
                "UNIV_NAME",
                "GAOKAO_DATE",
                "REGION_NAME",
                "BRANCH_NAME",
                "ADMISSIONBATCH_NAME",
                "SPECIALTY_NAME",
                "ENROLLMENT_DESC",
                "ENROLLMENT_NUM",
            ]
            cursor.execute(
                f"""
                SELECT {', '.join(f'`{column}`' for column in identity)},
                       COUNT(*) AS COPIES
                FROM `{TARGET_TABLE}`
                GROUP BY {', '.join(f'`{column}`' for column in identity)}
                HAVING COUNT(*) > 1
                """
            )
            duplicate_rows = cursor.fetchall()

            cursor.execute(f"SELECT COUNT(*) FROM `{TARGET_TABLE}`")
            total_rows = cursor.fetchone()["COUNT(*)"]

        report = {
            "school_summary": school_summary,
            "validation": validation,
            "duplicate_groups": len(duplicate_rows),
            "total_rows": total_rows,
            "province_coverage_rows": len(province_rows),
            "detail_rows_exported": len(details),
            "notes": {
                "SUFE_HEBUT_SCOPE": (
                    "上海财经大学和河北工业大学仅覆盖河南省"
                ),
                "UNIV_ID": "NULL，待确认可靠编号映射",
                "ENROLLMENT_ID": "NULL，待确认可靠编号映射",
            },
        }
        write_json(REPORT_ROOT / "final_verification.json", report)
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
