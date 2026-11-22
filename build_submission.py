"""Assemble a reproducible submission directory without deleting originals."""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

from admissions_common import ADMISSION_FIELDS, RESULTS, ROOT, SUBMISSION


SCRIPTS = [
    "admissions_common.py",
    "gaokao_enrollment.py",
    "nuc.py",
    "nuc_reocr_counts.py",
    "sxnu.py",
    "neu.py",
    "neu_ocr_worker.py",
    "sufe.py",
    "hebut.py",
    "provincial_henan.py",
    "migrate_gaokao_2026.py",
    "verify_gaokao_2026.py",
    "db_tools.py",
    "db_connection_check.py",
    "db_data_audit.py",
    "ocr_validation.py",
    "quality_report.py",
    "selftest.py",
]
RESULT_CSVS = {
    "中北大学": RESULTS / "nuc" / "nuc_candidates_final.csv",
    "山西师范大学": RESULTS / "sxnu" / "sxnu_candidates.csv",
    "东北大学": RESULTS / "neu" / "neu_candidates.csv",
    "上海财经大学": RESULTS / "sufe" / "sufe_henan_candidates.csv",
    "河北工业大学": RESULTS / "hebut" / "hebut_henan_candidates.csv",
}


def main():
    SUBMISSION.mkdir(parents=True, exist_ok=True)
    scripts_dir = SUBMISSION / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    for name in SCRIPTS:
        source = ROOT / name
        if source.exists():
            shutil.copy2(source, scripts_dir / name)
    for name in (
        "README.md",
        "PROJECT_AUDIT.md",
        "PROGRESS.md",
        "DATA_QUALITY.md",
        "DATABASE_AUDIT.md",
        "GAOKAO_2026_ENROLLMENT_MIGRATION.md",
        "OCR_VERIFICATION.md",
        "SOURCE_ACCESS.md",
        "TEST_REPORT.md",
        "FINAL_REPORT.md",
        "requirements.txt",
    ):
        source = ROOT / name
        if source.exists():
            shutil.copy2(source, SUBMISSION / name)
    for name in (".env.example", ".gitignore"):
        source = ROOT / name
        if source.exists():
            shutil.copy2(source, SUBMISSION / name)

    data_dir = SUBMISSION / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    combined = []
    manifest = {}
    for school, path in RESULT_CSVS.items():
        if not path.exists():
            manifest[school] = {"status": "not_available"}
            continue
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        for row in rows:
            if row.get("school") == school:
                combined.append(row)
        manifest[school] = {
            "status": "included",
            "source": str(path.relative_to(ROOT)).replace("\\", "/"),
            "rows": len(rows),
            "planned_count": sum(
                int(row.get("planned_count") or 0) for row in rows
            ),
        }
        shutil.copy2(path, SUBMISSION / "data" / path.name)
    evidence = SUBMISSION / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    for path in (
        RESULTS / "nuc" / "nuc_page_summary.csv",
        RESULTS / "nuc" / "nuc_parse_errors.csv",
        RESULTS / "nuc" / "nuc_province_summary.csv",
        RESULTS / "nuc" / "nuc_review_priority.csv",
        RESULTS / "nuc" / "source_urls.json",
        RESULTS / "neu" / "source_pages.json",
        ROOT / "data" / "nuc_manual_corrections.csv",
        ROOT / "data" / "official_sources.csv",
    ):
        if path.exists():
            shutil.copy2(path, evidence / path.name)
    for school in ("sufe", "hebut"):
        source = RESULTS / school / "source_evidence.json"
        if source.exists():
            target = evidence / school
            target.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target / "source_evidence.json")
    count_sidecars = ROOT / "ocr_results" / "nuc" / "_count_reocr"
    if count_sidecars.exists():
        shutil.copytree(
            count_sidecars,
            evidence / "nuc_count_reocr",
            dirs_exist_ok=True,
        )
    henan_sources = ROOT / "evidence" / "official_sources" / "henan"
    if henan_sources.exists():
        shutil.copytree(
            henan_sources,
            evidence / "henan_official",
            dirs_exist_ok=True,
        )
    for source_dir, target_dir in (
        (RESULTS / "data_quality", SUBMISSION / "data_quality"),
        (RESULTS / "validation", SUBMISSION / "validation"),
        (RESULTS / "logs", SUBMISSION / "logs"),
        (RESULTS / "integrity", SUBMISSION / "integrity"),
    ):
        if source_dir.exists():
            shutil.copytree(source_dir, target_dir, dirs_exist_ok=True)
    database_dir = SUBMISSION / "database"
    database_dir.mkdir(parents=True, exist_ok=True)
    for name in (
        "database_audit.json",
        "duplicate_check.csv",
        "existing_data_audit.json",
        "null_check.csv",
        "province_summary.csv",
        "review_summary.csv",
        "school_summary.csv",
        "datagrip_query.sql",
        "datagrip_query_result.png",
    ):
        source = RESULTS / "database" / name
        if source.exists():
            shutil.copy2(source, database_dir / name)
    gaokao_reports = RESULTS / "gaokao_2026_enrollment"
    if gaokao_reports.exists():
        shutil.copytree(
            gaokao_reports,
            database_dir / "gaokao_2026_enrollment",
            dirs_exist_ok=True,
        )
    with (data_dir / "combined_candidates.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=ADMISSION_FIELDS,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(combined)
    (SUBMISSION / "manifest.json").write_text(
        json.dumps(
            {
                "schools": manifest,
                "combined_rows": len(combined),
                "combined_planned_count": sum(
                    int(row.get("planned_count") or 0) for row in combined
                ),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print("SUBMISSION", SUBMISSION)
    print("COMBINED", len(combined))


if __name__ == "__main__":
    main()
