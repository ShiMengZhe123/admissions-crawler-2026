"""Common helpers for the five-school admissions-plan project.

The module never stores database credentials. Set MYSQL_PASSWORD in the
process environment, or allow connect_database() to prompt with getpass.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import requests


ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"
SUBMISSION = ROOT / "submission"
ADMISSION_FIELDS = [
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
    "fee_text",
    "planned_count",
    "source_url",
    "source_image",
    "source_row",
    "source_box",
    "extraction_method",
    "review_status",
    "review_reason",
]


def _load_local_env() -> None:
    path = ROOT / ".env.local"
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


_load_local_env()


UNIFIED_SCHEMA = """
CREATE TABLE IF NOT EXISTS admission_plan_v2 (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    admission_year SMALLINT UNSIGNED NOT NULL,
    school VARCHAR(40) NOT NULL,
    province VARCHAR(40) NOT NULL,
    college_name VARCHAR(200) NULL,
    major_code VARCHAR(32) NULL,
    major_name VARCHAR(240) NOT NULL,
    subject_type VARCHAR(80) NULL,
    batch_name VARCHAR(120) NULL,
    plan_type VARCHAR(120) NULL,
    selection_subject TEXT NULL,
    fee_text VARCHAR(160) NULL,
    planned_count INT UNSIGNED NOT NULL,
    source_url VARCHAR(1000) NOT NULL,
    source_image VARCHAR(500) NULL,
    source_row INT NULL,
    source_box TEXT NULL,
    extraction_method VARCHAR(16) NOT NULL,
    review_status VARCHAR(32) NOT NULL DEFAULT '未验证',
    review_reason TEXT NULL,
    record_hash CHAR(64) NOT NULL,
    fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uniq_record_hash (record_hash),
    KEY idx_school_year_province
        (school, admission_year, province),
    KEY idx_review_status (review_status),
    CONSTRAINT chk_plan_count CHECK (planned_count > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin
"""


INSERT_SQL = """
INSERT INTO admission_plan_v2 (
    admission_year, school, province, college_name, major_code,
    major_name, subject_type, batch_name, plan_type,
    selection_subject, fee_text, planned_count, source_url,
    source_image, source_row, source_box, extraction_method,
    review_status, review_reason, record_hash
) VALUES (
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
)
ON DUPLICATE KEY UPDATE
    college_name = VALUES(college_name),
    major_name = VALUES(major_name),
    subject_type = VALUES(subject_type),
    batch_name = VALUES(batch_name),
    plan_type = VALUES(plan_type),
    selection_subject = VALUES(selection_subject),
    fee_text = VALUES(fee_text),
    planned_count = VALUES(planned_count),
    source_url = VALUES(source_url),
    source_image = VALUES(source_image),
    source_row = VALUES(source_row),
    source_box = VALUES(source_box),
    extraction_method = VALUES(extraction_method),
    review_status = VALUES(review_status),
    review_reason = VALUES(review_reason)
"""


def ensure_utf8_stdio() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass


def normalize(text: object) -> str:
    value = str(text or "")
    value = value.replace("（", "(").replace("）", ")")
    value = value.replace("，", ",").replace("；", ";")
    return re.sub(r"\s+", "", value)


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/131 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
        }
    )
    return session


def request_with_retries(
    session: requests.Session,
    url: str,
    *,
    attempts: int = 3,
    timeout: int = 30,
    delay: float = 1.0,
    **kwargs,
) -> requests.Response:
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            response = session.get(url, timeout=timeout, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(delay * attempt)
    raise RuntimeError(f"请求失败: {url}: {last_error}") from last_error


def record_hash(record: Mapping[str, object]) -> str:
    keys = (
        "admission_year",
        "school",
        "province",
        "college_name",
        "major_code",
        "major_name",
        "subject_type",
        "selection_subject",
        "batch_name",
        "plan_type",
    )
    payload = "\x1f".join(normalize(record.get(key, "")) for key in keys)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def write_csv(
    path: Path,
    rows: Iterable[Mapping[str, object]],
    fields: Sequence[str] = ADMISSION_FIELDS,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row_list = list(rows)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(row_list)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )


@dataclass(frozen=True)
class DatabaseConfig:
    host: str
    port: int
    user: str
    password: str
    database: str = "admissions"


def get_database_config(prompt: bool = True) -> DatabaseConfig:
    password = os.getenv("MYSQL_PASSWORD", "")
    if not password and prompt:
        from getpass import getpass

        password = getpass("请输入 MySQL 密码（输入不显示）：")
    if password is None:
        password = ""
    return DatabaseConfig(
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER", "root"),
        password=password,
        database=os.getenv("MYSQL_DATABASE", "admissions"),
    )


def connect_database(prompt: bool = True):
    import mysql.connector

    config = get_database_config(prompt=prompt)
    return mysql.connector.connect(
        host=config.host,
        port=config.port,
        user=config.user,
        password=config.password,
        database=config.database,
        charset="utf8mb4",
        connection_timeout=10,
        autocommit=False,
    )


def ensure_unified_schema(connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute(UNIFIED_SCHEMA)
    connection.commit()


def upsert_admission_records(connection, records: Iterable[Mapping[str, object]]) -> int:
    rows = []
    for record in records:
        merged = dict(record)
        merged["record_hash"] = record_hash(merged)
        source_box_value = merged.get("source_box")
        if isinstance(source_box_value, str):
            source_box_json = source_box_value or None
        elif source_box_value is None:
            source_box_json = None
        else:
            source_box_json = json.dumps(
                source_box_value,
                ensure_ascii=False,
            )
        rows.append(
            (
                int(merged["admission_year"]),
                normalize(merged["school"]),
                normalize(merged["province"]),
                normalize(merged.get("college_name", "")),
                normalize(merged.get("major_code", "")),
                normalize(merged["major_name"]),
                normalize(merged.get("subject_type", "")),
                normalize(merged.get("batch_name", "")),
                normalize(merged.get("plan_type", "")),
                normalize(merged.get("selection_subject", "")),
                normalize(merged.get("fee_text", "")),
                int(merged["planned_count"]),
                str(merged["source_url"]),
                normalize(merged.get("source_image", "")),
                int(merged["source_row"]) if merged.get("source_row") else None,
                source_box_json,
                normalize(merged.get("extraction_method", "OCR")),
                normalize(merged.get("review_status", "未验证")),
                str(merged.get("review_reason", "")),
                merged["record_hash"],
            )
        )
    if not rows:
        return 0
    ensure_unified_schema(connection)
    with connection.cursor() as cursor:
        cursor.executemany(INSERT_SQL, rows)
    connection.commit()
    return len(rows)


def school_summary(records: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], dict[str, object]] = {}
    for record in records:
        key = (str(record["school"]), str(record["province"]))
        item = grouped.setdefault(
            key,
            {
                "school": key[0],
                "province": key[1],
                "records": 0,
                "planned_count": 0,
            },
        )
        item["records"] = int(item["records"]) + 1
        item["planned_count"] = int(item["planned_count"]) + int(
            record["planned_count"]
        )
    return sorted(grouped.values(), key=lambda row: (row["school"], row["province"]))


def load_csv_records(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [
            {key: (value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(handle)
        ]
