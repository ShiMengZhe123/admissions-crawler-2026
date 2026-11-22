"""MySQL audit, safe schema setup, CSV import and query export."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from admissions_common import (
    RESULTS,
    connect_database,
    ensure_unified_schema,
    ensure_utf8_stdio,
    load_csv_records,
    upsert_admission_records,
    write_csv,
    write_json,
)


QUERIES = {
    "school_summary": """
        SELECT school, COUNT(*) AS record_count,
               SUM(planned_count) AS planned_total
        FROM admission_plan_v2
        WHERE admission_year = 2026
        GROUP BY school
        ORDER BY school
    """,
    "province_summary": """
        SELECT school, province, COUNT(*) AS record_count,
               SUM(planned_count) AS planned_total
        FROM admission_plan_v2
        WHERE admission_year = 2026
        GROUP BY school, province
        ORDER BY school, province
    """,
    "null_check": """
        SELECT school,
               SUM(major_name IS NULL OR major_name = '') AS empty_major,
               SUM(planned_count IS NULL OR planned_count <= 0) AS invalid_count,
               SUM(source_url IS NULL OR source_url = '') AS empty_source
        FROM admission_plan_v2
        WHERE admission_year = 2026
        GROUP BY school
        ORDER BY school
    """,
    "duplicate_check": """
        SELECT school, province, college_name, major_name,
               subject_type, batch_name, plan_type,
               selection_subject, COUNT(*) AS copies
        FROM admission_plan_v2
        WHERE admission_year = 2026
        GROUP BY school, province, college_name, major_name,
                 subject_type, batch_name, plan_type, selection_subject
        HAVING COUNT(*) > 1
        ORDER BY copies DESC, school, province
    """,
    "review_summary": """
        SELECT school, review_status, COUNT(*) AS rows_count,
               SUM(planned_count) AS planned_total
        FROM admission_plan_v2
        WHERE admission_year = 2026
        GROUP BY school, review_status
        ORDER BY school, review_status
    """,
}


def audit() -> None:
    connection = connect_database()
    audit_data = {}
    try:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT DATABASE() AS db, VERSION() AS version")
            audit_data["connection"] = cursor.fetchone()
            cursor.execute(
                """
                SELECT table_name, table_type
                FROM information_schema.tables
                WHERE table_schema = DATABASE()
                ORDER BY table_name
                """
            )
            tables = cursor.fetchall()
            audit_data["tables"] = tables
            for table in tables:
                if table["TABLE_TYPE"] != "BASE TABLE":
                    continue
                name = table["TABLE_NAME"]
                cursor.execute(
                    f"SELECT COUNT(*) AS rows_count FROM `{name}`"
                )
                table["rows"] = cursor.fetchone()["rows_count"]
                cursor.execute(
                    """
                    SELECT column_name, column_type, is_nullable, column_key,
                           column_default, extra
                    FROM information_schema.columns
                    WHERE table_schema = DATABASE() AND table_name = %s
                    ORDER BY ordinal_position
                    """,
                    (name,),
                )
                table["columns"] = cursor.fetchall()
            if any(
                table["TABLE_NAME"] == "admission_plan_v2"
                for table in tables
            ):
                cursor.execute(
                    """
                    SELECT school, COUNT(*) AS rows_count,
                           SUM(planned_count) AS planned_total
                    FROM admission_plan_v2
                    WHERE admission_year = 2026
                    GROUP BY school
                    ORDER BY school
                    """
                )
                audit_data["schools"] = cursor.fetchall()
    finally:
        connection.close()
    output = RESULTS / "database" / "database_audit.json"
    write_json(output, audit_data)
    print(json.dumps(audit_data, ensure_ascii=False, indent=2, default=str))
    print("OUTPUT", output)


def migrate() -> None:
    connection = connect_database()
    try:
        ensure_unified_schema(connection)
        print("已确保 admissions.admission_plan_v2 存在。")
    finally:
        connection.close()


def backup(table: str) -> None:
    if not table.replace("_", "").isalnum():
        raise ValueError("无效表名")
    stem = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = f"{table}_backup_{stem}"
    connection = connect_database()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE TABLE `{target}` LIKE `{table}`"
            )
            cursor.execute(
                f"INSERT INTO `{target}` SELECT * FROM `{table}`"
            )
            cursor.execute(
                f"SELECT COUNT(*) FROM `{target}`"
            )
            count = cursor.fetchone()[0]
        connection.commit()
        print("BACKUP_TABLE", target, "ROWS", count)
    finally:
        connection.close()


def import_csv(path: Path) -> None:
    records = load_csv_records(path)
    connection = connect_database()
    try:
        print("DB_UPSERTED", upsert_admission_records(connection, records))
    finally:
        connection.close()


def export_queries() -> None:
    output = RESULTS / "database"
    connection = connect_database()
    try:
        ensure_unified_schema(connection)
        with connection.cursor(dictionary=True) as cursor:
            for name, sql in QUERIES.items():
                cursor.execute(sql)
                rows = cursor.fetchall()
                fields = (
                    list(rows[0].keys())
                    if rows
                    else [column[0] for column in cursor.description]
                )
                write_csv(output / f"{name}.csv", rows, fields)
                print(name, len(rows))
    finally:
        connection.close()


def main() -> None:
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("audit")
    subparsers.add_parser("migrate")
    backup_parser = subparsers.add_parser("backup")
    backup_parser.add_argument("table")
    import_parser = subparsers.add_parser("import-csv")
    import_parser.add_argument("path", type=Path)
    subparsers.add_parser("queries")
    args = parser.parse_args()
    if args.command == "audit":
        audit()
    elif args.command == "migrate":
        migrate()
    elif args.command == "backup":
        backup(args.table)
    elif args.command == "import-csv":
        import_csv(args.path)
    elif args.command == "queries":
        export_queries()


if __name__ == "__main__":
    main()
