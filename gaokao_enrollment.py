"""Shared mapping and idempotent importer for gaokao_2026_enrollment."""

from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from datetime import datetime
from typing import Iterable, Mapping

from admissions_common import normalize, record_hash


TARGET_TABLE = "gaokao_2026_enrollment"
LEDGER_TABLE = "gaokao_2026_enrollment_import_ledger"
IMPORT_LOCK = "gaokao_2026_enrollment_import"

OPERATE_ID = "GK010101000000000000"
OPERATE_FLAG = "1"
OPERATE_IP = "127.0.0.1"

TARGET_COLUMNS = [
    "ENROLLMENT_ID",
    "UNIV_ID",
    "UNIV_NAME",
    "GAOKAO_DATE",
    "REGION_NAME",
    "BRANCH_NAME",
    "ADMISSIONBATCH_NAME",
    "SPECIALTY_NAME",
    "ENROLLMENT_DESC",
    "ENROLLMENT_NUM",
    "OPERATE_ID",
    "OPERATE_FLAG",
    "OPERATE_TIME",
    "OPERATE_IP",
]

IDENTITY_COLUMNS = [
    "UNIV_NAME",
    "GAOKAO_DATE",
    "REGION_NAME",
    "BRANCH_NAME",
    "ADMISSIONBATCH_NAME",
    "SPECIALTY_NAME",
    "ENROLLMENT_DESC",
    "ENROLLMENT_NUM",
]

# The table columns, types, charset, and indexes come from the client's DDL.
# IF NOT EXISTS only makes repeated local setup safe.
GAOKAO_SCHEMA = """
CREATE TABLE IF NOT EXISTS `gaokao_2026_enrollment` (
  `ENROLLMENT_ID` varchar(100) DEFAULT NULL COMMENT '招生计划',
  `UNIV_ID` char(20) DEFAULT NULL COMMENT '院校信息',
  `UNIV_NAME` varchar(200) NOT NULL DEFAULT '' COMMENT '学院名称',
  `GAOKAO_DATE` varchar(29) DEFAULT NULL COMMENT '高考年份',
  `REGION_NAME` varchar(400) CHARACTER SET utf8 DEFAULT NULL COMMENT '高考省份',
  `BRANCH_NAME` varchar(200) CHARACTER SET utf8 DEFAULT NULL COMMENT '科类选择',
  `ADMISSIONBATCH_NAME` varchar(1000) DEFAULT NULL COMMENT '录取批次',
  `SPECIALTY_NAME` varchar(200) CHARACTER SET utf8 DEFAULT NULL COMMENT '专业名称',
  `ENROLLMENT_DESC` varchar(1000) DEFAULT NULL COMMENT '招生类型-样式：招生类型：（例如普通类），选课要求：',
  `ENROLLMENT_NUM` int(50) NOT NULL COMMENT '招生人数',
  `OPERATE_ID` char(20) NOT NULL COMMENT '操作人员-默认GK010101000000000000',
  `OPERATE_FLAG` char(1) NOT NULL COMMENT '操作动作-默认1',
  `OPERATE_TIME` char(19) NOT NULL COMMENT '操作时间',
  `OPERATE_IP` varchar(40) NOT NULL COMMENT '操作地址默认：127.0.0.1',
  KEY `IX_UNIV` (`UNIV_ID`),
  KEY `IX_SPECIALTY` (`SPECIALTY_NAME`),
  KEY `IX_ENROLLMENT` (`ENROLLMENT_DESC`),
  KEY `IX_OPERATE` (`OPERATE_FLAG`),
  KEY `IX_OPERATETIME` (`OPERATE_TIME`)
) ENGINE=InnoDB DEFAULT CHARSET=gbk
"""

# The target table intentionally has no key. This auxiliary table is not a
# modification to the client DDL; it makes repeated imports deterministic.
LEDGER_SCHEMA = """
CREATE TABLE IF NOT EXISTS `gaokao_2026_enrollment_import_ledger` (
  `TARGET_KEY_HASH` char(64) NOT NULL,
  `SOURCE_RECORD_HASH` char(64) NOT NULL,
  `UNIV_NAME` varchar(200) NOT NULL,
  `REGION_NAME` varchar(400) NOT NULL,
  `FIRST_IMPORTED_AT` datetime NOT NULL,
  `LAST_SEEN_AT` datetime NOT NULL,
  `OPERATE_TIME` char(19) NOT NULL,
  PRIMARY KEY (`TARGET_KEY_HASH`),
  KEY `IX_LEDGER_SOURCE` (`SOURCE_RECORD_HASH`),
  KEY `IX_LEDGER_SCHOOL_PROVINCE` (`UNIV_NAME`, `REGION_NAME`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
"""

INSERT_SQL = """
INSERT INTO `gaokao_2026_enrollment` (
    `ENROLLMENT_ID`, `UNIV_ID`, `UNIV_NAME`, `GAOKAO_DATE`,
    `REGION_NAME`, `BRANCH_NAME`, `ADMISSIONBATCH_NAME`,
    `SPECIALTY_NAME`, `ENROLLMENT_DESC`, `ENROLLMENT_NUM`,
    `OPERATE_ID`, `OPERATE_FLAG`, `OPERATE_TIME`, `OPERATE_IP`
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

LEDGER_SQL = """
INSERT INTO `gaokao_2026_enrollment_import_ledger` (
    `TARGET_KEY_HASH`, `SOURCE_RECORD_HASH`, `UNIV_NAME`,
    `REGION_NAME`, `FIRST_IMPORTED_AT`, `LAST_SEEN_AT`, `OPERATE_TIME`
) VALUES (%s, %s, %s, %s, %s, %s, %s)
"""

LOCK_SQL = "SELECT GET_LOCK(%s, 30)"
UNLOCK_SQL = "SELECT RELEASE_LOCK(%s)"


def clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def build_enrollment_desc(record: Mapping[str, object]) -> str:
    parts = []
    plan_type = normalize(record.get("plan_type", ""))
    selection = normalize(record.get("selection_subject", ""))
    if plan_type:
        parts.append(f"招生类型：{plan_type}")
    if selection:
        parts.append(f"选课要求：{selection}")
    return "，".join(parts)


def map_record(
    record: Mapping[str, object],
    operate_time: str,
) -> dict[str, object]:
    source_record_hash = clean_text(record.get("record_hash", ""))
    if not source_record_hash:
        source_record_hash = record_hash(record)
    return {
        "ENROLLMENT_ID": None,
        "UNIV_ID": None,
        "UNIV_NAME": normalize(record.get("school", "")),
        "GAOKAO_DATE": str(record.get("admission_year", "")).strip(),
        "REGION_NAME": normalize(record.get("province", "")),
        "BRANCH_NAME": normalize(record.get("subject_type", "")),
        "ADMISSIONBATCH_NAME": normalize(record.get("batch_name", "")),
        "SPECIALTY_NAME": normalize(record.get("major_name", "")),
        "ENROLLMENT_DESC": build_enrollment_desc(record),
        "ENROLLMENT_NUM": int(record.get("planned_count") or 0),
        "OPERATE_ID": OPERATE_ID,
        "OPERATE_FLAG": OPERATE_FLAG,
        "OPERATE_TIME": operate_time,
        "OPERATE_IP": OPERATE_IP,
        "_SOURCE_RECORD_HASH": source_record_hash,
        "_SOURCE_URL": clean_text(record.get("source_url", "")),
        "_SOURCE_ROW": record.get("source_row"),
        "_SOURCE_COLLEGE": clean_text(record.get("college_name", "")),
        "_SOURCE_MAJOR_CODE": clean_text(record.get("major_code", "")),
    }


def identity_tuple(mapped: Mapping[str, object]) -> tuple[object, ...]:
    return tuple(mapped[column] for column in IDENTITY_COLUMNS)


def identity_hash(mapped: Mapping[str, object]) -> str:
    payload = "\x1f".join(
        "" if mapped[column] is None else str(mapped[column])
        for column in IDENTITY_COLUMNS
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def prepare_records(
    records: Iterable[Mapping[str, object]],
    operate_time: str,
) -> dict[str, object]:
    grouped: dict[tuple[object, ...], list[dict[str, object]]] = defaultdict(list)
    missing = Counter()
    mapped_count = 0
    for record in records:
        mapped = map_record(record, operate_time)
        mapped_count += 1
        grouped[identity_tuple(mapped)].append(mapped)
        for field, source_field in (
            ("BRANCH_NAME", "subject_type"),
            ("ADMISSIONBATCH_NAME", "batch_name"),
        ):
            if not mapped[field]:
                missing[source_field] += 1
        if not clean_text(record.get("plan_type", "")):
            missing["plan_type"] += 1
        if not clean_text(record.get("selection_subject", "")):
            missing["selection_subject"] += 1

    importable = []
    conflicts = []
    duplicate_sources = 0
    for key, rows in grouped.items():
        source_hashes = {row["_SOURCE_RECORD_HASH"] for row in rows}
        if len(source_hashes) > 1:
            for row in rows:
                conflicts.append(
                    {
                        "reason": "不同源记录映射到相同目标字段，目标表无法区分",
                        "UNIV_NAME": row["UNIV_NAME"],
                        "REGION_NAME": row["REGION_NAME"],
                        "BRANCH_NAME": row["BRANCH_NAME"],
                        "ADMISSIONBATCH_NAME": row["ADMISSIONBATCH_NAME"],
                        "SPECIALTY_NAME": row["SPECIALTY_NAME"],
                        "ENROLLMENT_DESC": row["ENROLLMENT_DESC"],
                        "ENROLLMENT_NUM": row["ENROLLMENT_NUM"],
                        "source_record_hash": row["_SOURCE_RECORD_HASH"],
                        "source_url": row["_SOURCE_URL"],
                        "source_row": row["_SOURCE_ROW"],
                        "source_college": row["_SOURCE_COLLEGE"],
                        "source_major_code": row["_SOURCE_MAJOR_CODE"],
                    }
                )
            continue
        duplicate_sources += len(rows) - 1
        selected = sorted(
            rows,
            key=lambda row: (
                str(row["_SOURCE_URL"]),
                int(row["_SOURCE_ROW"] or 0),
            ),
        )[0]
        selected["_TARGET_KEY_HASH"] = identity_hash(selected)
        importable.append(selected)

    return {
        "mapped_count": mapped_count,
        "unique_target_count": len(grouped),
        "importable_count": len(importable),
        "duplicate_source_count": duplicate_sources,
        "conflict_count": len(conflicts),
        "conflicts": conflicts,
        "missing_fields": dict(missing),
        "records": importable,
    }


def ensure_schema(connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute(GAOKAO_SCHEMA)
        cursor.execute(LEDGER_SCHEMA)
    connection.commit()


def target_tuple(row: Mapping[str, object]) -> tuple[object, ...]:
    return tuple(row[column] for column in IDENTITY_COLUMNS)


def write_gaokao_records(
    connection,
    records: Iterable[Mapping[str, object]],
    *,
    operate_time: str | None = None,
) -> dict[str, object]:
    operate_time = (
        operate_time or datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
    )
    prepared = prepare_records(records, operate_time)
    ensure_schema(connection)
    inserted = 0
    existing_skipped = 0
    ledger_created = 0

    with connection.cursor(dictionary=True) as cursor:
        cursor.execute(LOCK_SQL, (IMPORT_LOCK,))
        lock_row = cursor.fetchone()
        lock_value = next(iter(lock_row.values()))
        if lock_value != 1:
            raise RuntimeError("未能获取 gaokao_2026_enrollment 导入锁")
        try:
            cursor.execute(
                f"SELECT {', '.join(f'`{column}`' for column in IDENTITY_COLUMNS)} "
                f"FROM `{TARGET_TABLE}`"
            )
            existing_targets = {
                tuple(row[column] for column in IDENTITY_COLUMNS)
                for row in cursor.fetchall()
            }
            cursor.execute(
                f"SELECT `TARGET_KEY_HASH` FROM `{LEDGER_TABLE}`"
            )
            existing_ledger = {
                row["TARGET_KEY_HASH"] for row in cursor.fetchall()
            }

            # mysql-connector may implicitly open a transaction for the
            # preceding SELECTs. End it before starting the managed DML one.
            connection.commit()
            connection.start_transaction()
            for row in prepared["records"]:
                target_key = target_tuple(row)
                key_hash = row["_TARGET_KEY_HASH"]
                if target_key in existing_targets or key_hash in existing_ledger:
                    existing_skipped += 1
                    if key_hash not in existing_ledger:
                        cursor.execute(
                            LEDGER_SQL,
                            (
                                key_hash,
                                row["_SOURCE_RECORD_HASH"],
                                row["UNIV_NAME"],
                                row["REGION_NAME"],
                                operate_time,
                                operate_time,
                                operate_time,
                            ),
                        )
                        ledger_created += 1
                        existing_ledger.add(key_hash)
                    continue

                cursor.execute(
                    INSERT_SQL,
                    tuple(row[column] for column in TARGET_COLUMNS),
                )
                cursor.execute(
                    LEDGER_SQL,
                    (
                        key_hash,
                        row["_SOURCE_RECORD_HASH"],
                        row["UNIV_NAME"],
                        row["REGION_NAME"],
                        operate_time,
                        operate_time,
                        operate_time,
                    ),
                )
                inserted += 1
                ledger_created += 1
                existing_targets.add(target_key)
                existing_ledger.add(key_hash)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.execute(UNLOCK_SQL, (IMPORT_LOCK,))
            cursor.fetchall()

    prepared.pop("records")
    prepared.update(
        {
            "operate_time": operate_time,
            "inserted": inserted,
            "existing_skipped": existing_skipped,
            "ledger_created": ledger_created,
        }
    )
    return prepared
