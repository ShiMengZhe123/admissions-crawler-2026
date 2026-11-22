"""Read-only audit of existing admissions data."""

from __future__ import annotations

import json

from admissions_common import (
    RESULTS,
    connect_database,
    ensure_utf8_stdio,
    write_json,
)


QUERIES = {
    "admission_plan_summary": """
        SELECT admission_year, school, COUNT(*) AS rows_count,
               COUNT(DISTINCT province) AS province_count,
               SUM(planned_count) AS planned_total
        FROM admission_plan
        GROUP BY admission_year, school
        ORDER BY admission_year, school
    """,
    "admission_plan_quality": """
        SELECT admission_year, school,
               SUM(major_name = '') AS empty_major,
               SUM(province = '') AS empty_province,
               SUM(subject_type = '') AS empty_subject,
               SUM(plan_type = '') AS empty_plan_type,
               SUM(source_url = '') AS empty_source,
               SUM(planned_count <= 0) AS invalid_count
        FROM admission_plan
        GROUP BY admission_year, school
    """,
    "admission_plan_provinces": """
        SELECT school, province, COUNT(*) AS rows_count,
               SUM(planned_count) AS planned_total
        FROM admission_plan
        GROUP BY school, province
        ORDER BY school, province
    """,
    "nuc_raw_summary": """
        SELECT province, COUNT(*) AS text_boxes,
               COUNT(DISTINCT image_name) AS images
        FROM nuc_ocr_raw
        WHERE admission_year = 2026 AND school = '中北大学'
        GROUP BY province
        ORDER BY province
    """,
    "nuc_parsed_summary": """
        SELECT province, COUNT(*) AS rows_count,
               SUM(planned_count) AS planned_total,
               SUM(review_status = '待复核') AS pending_review
        FROM nuc_plan_parsed
        WHERE admission_year = 2026 AND school = '中北大学'
        GROUP BY province
        ORDER BY province
    """,
    "nuc_v2_summary": """
        SELECT province, COUNT(*) AS rows_count,
               SUM(planned_count) AS planned_total,
               SUM(review_status = '待复核') AS pending_review
        FROM nuc_plan_v2
        WHERE admission_year = 2026 AND school = '中北大学'
        GROUP BY province
        ORDER BY province
    """,
    "nuc_v2_suspicious": """
        SELECT COUNT(*) AS suspicious_rows
        FROM nuc_plan_v2
        WHERE admission_year = 2026 AND school = '中北大学'
          AND (
              college_name IN ('合计', '总计', '小计')
              OR major_name IN ('合计', '总计', '小计', '总结')
              OR planned_count IS NULL
              OR planned_count <= 0
          )
    """,
    "nuc_validation_summary": """
        SELECT COUNT(*) AS rows_count,
               SUM(is_correct IS NOT NULL) AS reviewed_rows,
               SUM(is_correct = 1) AS correct_rows
        FROM nuc_ocr_validation
    """,
}


def main() -> None:
    ensure_utf8_stdio()
    connection = connect_database(prompt=False)
    output = {}
    try:
        with connection.cursor(dictionary=True) as cursor:
            for name, sql in QUERIES.items():
                cursor.execute(sql)
                output[name] = cursor.fetchall()
    finally:
        connection.close()
    path = RESULTS / "database" / "existing_data_audit.json"
    write_json(path, output)
    print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
    print("OUTPUT", path)


if __name__ == "__main__":
    main()
