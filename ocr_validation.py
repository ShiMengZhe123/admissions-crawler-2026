"""Deterministic sampling and manual OCR validation.

The script never marks a row correct automatically. It creates crops for human
comparison and only computes accuracy from an explicitly filled verified column.
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import math
import random
from pathlib import Path

from PIL import Image

from admissions_common import RESULTS, ROOT, ensure_utf8_stdio, write_csv


SOURCES = [
    RESULTS / "nuc" / "nuc_candidates_final.csv",
    RESULTS / "sxnu" / "sxnu_candidates.csv",
    RESULTS / "neu" / "neu_candidates.csv",
    RESULTS / "sufe" / "sufe_candidates.csv",
    RESULTS / "hebut" / "hebut_candidates.csv",
]
OUTPUT_ROOT = RESULTS / "validation"


def parse_box(value: str):
    if not value:
        return None
    try:
        box = json.loads(value)
    except json.JSONDecodeError:
        try:
            box = ast.literal_eval(value)
        except (SyntaxError, ValueError):
            return None
    if isinstance(box, list) and len(box) == 4:
        return [float(value) for value in box]
    return None


def load_records():
    records = []
    for source in SOURCES:
        if not source.exists():
            continue
        with source.open(encoding="utf-8-sig", newline="") as handle:
            for index, row in enumerate(csv.DictReader(handle), start=1):
                if not row.get("major_name") or not row.get("planned_count"):
                    continue
                row["_source_csv"] = str(source.relative_to(ROOT))
                row["_source_line"] = index + 1
                records.append(row)
    return records


def stratified_sample(records, size=200, seed=2026):
    rng = random.Random(seed)
    groups = {}
    for record in records:
        key = (
            record.get("school", ""),
            record.get("province", ""),
            record.get("extraction_method", ""),
            record.get("source_image", ""),
        )
        groups.setdefault(key, []).append(record)
    keys = list(groups)
    rng.shuffle(keys)
    for key in keys:
        rng.shuffle(groups[key])
    sample = []
    while len(sample) < min(size, len(records)):
        progressed = False
        for key in keys:
            if groups[key] and len(sample) < size:
                sample.append(groups[key].pop())
                progressed = True
        if not progressed:
            break
    return sample


def make_crop(record, sample_id):
    source_image = record.get("source_image", "")
    if not source_image:
        return ""
    image_path = ROOT / source_image
    if not image_path.exists():
        return ""
    box = parse_box(record.get("source_box", ""))
    if not box:
        return ""
    image = Image.open(image_path)
    y_center = (box[1] + box[3]) / 2
    top = max(0, int(y_center - 70))
    bottom = min(image.height, int(y_center + 70))
    crop = image.crop((0, top, image.width, bottom))
    output = OUTPUT_ROOT / "crops" / f"{sample_id:03d}.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    crop.save(output)
    return str(output.relative_to(ROOT)).replace("\\", "/")


def create_sample(size: int):
    records = load_records()
    if len(records) < size:
        raise RuntimeError(f"当前仅有 {len(records)} 条结构化记录，少于 {size}")
    sample = stratified_sample(records, size=size)
    prepared = []
    for index, record in enumerate(sample, start=1):
        prepared.append(
            {
                "sample_id": index,
                "school": record.get("school", ""),
                "province": record.get("province", ""),
                "college_name": record.get("college_name", ""),
                "major_name": record.get("major_name", ""),
                "subject_type": record.get("subject_type", ""),
                "batch_name": record.get("batch_name", ""),
                "planned_count": record.get("planned_count", ""),
                "source_url": record.get("source_url", ""),
                "source_image": record.get("source_image", ""),
                "source_row": record.get("source_row", ""),
                "crop_path": make_crop(record, index),
                "verified": "",
                "verified_major": "",
                "verified_count": "",
                "error_fields": "",
                "reviewer_notes": "",
            }
        )
    write_csv(
        OUTPUT_ROOT / "ocr_validation_sample_200.csv",
        prepared,
        [
            "sample_id", "school", "province", "college_name",
            "major_name", "subject_type", "batch_name", "planned_count",
            "source_url", "source_image", "source_row", "crop_path",
            "verified", "verified_major", "verified_count",
            "error_fields", "reviewer_notes",
        ],
    )
    print("SAMPLE", len(prepared))
    print("OUTPUT", OUTPUT_ROOT / "ocr_validation_sample_200.csv")
    print("状态：未完成人工验证；禁止据此宣称 95%。")


def finalize(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    verified = [
        row
        for row in rows
        if row.get("verified", "").strip() in {"正确", "错误"}
    ]
    correct = sum(row["verified"].strip() == "正确" for row in verified)
    summary = {
        "sample_rows": len(rows),
        "verified_rows": len(verified),
        "correct_rows": correct,
        "incorrect_rows": len(verified) - correct,
        "accuracy": correct / len(verified) if verified else None,
        "threshold_95_reached": (
            len(verified) == len(rows)
            and len(verified) > 0
            and correct / len(verified) >= 0.95
        ),
    }
    with (OUTPUT_ROOT / "ocr_validation_result.json").open(
        "w", encoding="utf-8"
    ) as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def main():
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=int, default=200)
    parser.add_argument("--finalize", type=Path)
    args = parser.parse_args()
    if args.finalize:
        finalize(args.finalize)
    else:
        create_sample(args.sample)


if __name__ == "__main__":
    main()
