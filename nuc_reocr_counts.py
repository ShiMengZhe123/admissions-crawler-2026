import csv
import json
import sys
from pathlib import Path

import numpy as np
from paddleocr import PaddleOCR
from PIL import Image

import nuc as repair
from admissions_common import ROOT, ensure_utf8_stdio

ensure_utf8_stdio()
SOURCE = ROOT
TEST_RESULTS = SOURCE / "results" / "nuc"
SIDECAR_ROOT = SOURCE / "ocr_results" / "nuc" / "_count_reocr"


def detect_count_center(boxes):
    height = max(box["y2"] for box in boxes)
    width = max(box["x2"] for box in boxes)
    candidates = [
        box
        for box in boxes
        if box["text"].isdigit()
        and 1 <= int(box["text"]) <= 999
        and box["y"] > height * 0.03
        and 0.50 <= box["x"] / width <= 0.78
    ]
    if not candidates:
        return width * 0.64
    bins = {}
    bin_width = 24
    for box in candidates:
        key = int(box["x"] // bin_width)
        bins.setdefault(key, []).append(box)
    best = max(
        bins.values(),
        key=lambda group: (
            len(group),
            len({round(box["y"] / 20) for box in group}),
        ),
    )
    return sum(box["x"] for box in best) / len(best)


def should_reocr(row):
    parsed_rows = int(row["parsed_rows"])
    source_summary = row.get("source_summary", "").strip()
    return parsed_rows == 0 or (
        source_summary
        and int(row["parsed_count"]) != int(source_summary)
    )


with (TEST_RESULTS / "nuc_page_summary.csv").open(
    encoding="utf-8-sig", newline=""
) as handle:
    targets = [row for row in csv.DictReader(handle) if should_reocr(row)]

print("TARGET_PAGES", len(targets))
ocr = PaddleOCR(
    lang="ch",
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
)

for target_index, target in enumerate(targets, 1):
    province = target["province"]
    image_name = target["image_name"]
    result_file = SOURCE / "ocr_results" / "nuc" / province / f"{image_name}_res.json"
    image_file = SOURCE / "images" / "nuc" / province / f"{image_name}.png"
    boxes = repair.load_boxes(result_file)
    center = detect_count_center(boxes)
    half_width = 65
    image = Image.open(image_file)
    segment_height = 850
    overlap = 30
    count_boxes = []

    top = 0
    while top < image.height:
        bottom = min(image.height, top + segment_height)
        crop = image.crop(
            (
                max(0, int(center - half_width)),
                top,
                min(image.width, int(center + half_width)),
                bottom,
            )
        )
        crop = crop.resize(
            (crop.width * 3, crop.height * 3),
            Image.Resampling.LANCZOS,
        )
        results = ocr.predict(np.asarray(crop.convert("RGB")))
        for result in results:
            payload = result.json
            payload = payload.get("res", payload)
            for text, score, box in zip(
                payload.get("rec_texts", []),
                payload.get("rec_scores", []),
                payload.get("rec_boxes", []),
            ):
                text = str(text).strip()
                if not text.isdigit() or not (1 <= int(text) <= 999):
                    continue
                x1, y1, x2, y2 = map(float, box)
                original_box = [
                    x1 / 3 + max(0, center - half_width),
                    y1 / 3 + top,
                    x2 / 3 + max(0, center - half_width),
                    y2 / 3 + top,
                ]
                y = (original_box[1] + original_box[3]) / 2
                if any(abs(y - existing["y"]) < 5 for existing in count_boxes):
                    continue
                count_boxes.append(
                    {
                        "text": text,
                        "score": float(score),
                        "box": original_box,
                        "y": y,
                    }
                )
        if bottom >= image.height:
            break
        top = bottom - overlap

    count_boxes.sort(key=lambda item: item["y"])
    output_dir = SIDECAR_ROOT / province
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{image_name}_counts.json"
    if output_file.exists():
        print("SKIP_EXISTING", province, image_name, output_file)
        continue
    output_file.write_text(
        json.dumps(
            {
                "province": province,
                "image_name": image_name,
                "count_center": center,
                "numbers": count_boxes,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        f"[{target_index}/{len(targets)}]",
        province,
        image_name,
        len(count_boxes),
        "=>",
        output_file,
    )
