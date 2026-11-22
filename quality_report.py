"""Generate data-quality metrics from available structured CSVs."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

from admissions_common import RESULTS, ROOT, ensure_utf8_stdio, write_csv


SOURCES = {
    "中北大学": RESULTS / "nuc" / "nuc_candidates_final.csv",
    "山西师范大学": RESULTS / "sxnu" / "sxnu_candidates.csv",
    "东北大学": RESULTS / "neu" / "neu_candidates.csv",
    "上海财经大学": RESULTS / "sufe" / "sufe_henan_candidates.csv",
    "河北工业大学": RESULTS / "hebut" / "hebut_henan_candidates.csv",
}
EXPECTED_PROVINCES = {
    "中北大学": 31,
    "山西师范大学": 29,
    "东北大学": 31,
    "上海财经大学": 31,
    "河北工业大学": 31,
}


def load(path: Path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def metrics(school: str, path: Path):
    rows = load(path)
    if not rows:
        return {
            "school": school,
            "status": "no_structured_data",
            "rows": 0,
            "provinces": 0,
            "planned_count": 0,
        }
    keys = Counter(
        (
            row.get("province", ""),
            row.get("college_name", ""),
            row.get("major_name", ""),
            row.get("subject_type", ""),
            row.get("batch_name", ""),
            row.get("plan_type", ""),
            row.get("selection_subject", ""),
        )
        for row in rows
    )
    province_count = len({row.get("province", "") for row in rows})
    expected = EXPECTED_PROVINCES.get(school)
    return {
        "school": school,
        "status": (
            "partial"
            if expected is not None and province_count < expected
            else "available"
        ),
        "rows": len(rows),
        "provinces": province_count,
        "planned_count": sum(int(row.get("planned_count") or 0) for row in rows),
        "empty_major": sum(not row.get("major_name", "").strip() for row in rows),
        "empty_subject": sum(
            not row.get("subject_type", "").strip() for row in rows
        ),
        "empty_source": sum(
            not row.get("source_url", "").strip() for row in rows
        ),
        "duplicate_business_keys": sum(
            count > 1 for count in keys.values()
        ),
        "review_status": dict(
            Counter(row.get("review_status", "") or "未标注" for row in rows)
        ),
    }


def main():
    ensure_utf8_stdio()
    summary = [metrics(school, path) for school, path in SOURCES.items()]
    output_root = RESULTS / "data_quality"
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "data_quality.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_csv(
        output_root / "data_quality.csv",
        summary,
        [
            "school", "status", "rows", "provinces", "planned_count",
            "empty_major", "empty_subject", "empty_source",
            "duplicate_business_keys",
        ],
    )
    issues = []
    for item in summary:
        if item["status"] != "available":
            issues.append(
                {
                    "school": item["school"],
                    "issue": "尚无结构化数据",
                    "count": "",
                }
            )
            continue
        for field in (
            "empty_major",
            "empty_subject",
            "empty_source",
            "duplicate_business_keys",
        ):
            if item.get(field):
                issues.append(
                    {
                        "school": item["school"],
                        "issue": field,
                        "count": item[field],
                    }
                )
    write_csv(
        output_root / "quality_issues.csv",
        issues,
        ["school", "issue", "count"],
    )
    for item in summary:
        print(item)
    print("OUTPUT", output_root)


if __name__ == "__main__":
    main()
