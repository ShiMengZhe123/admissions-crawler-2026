"""Parallel worker for NEU official plan images.

Only the plan-relevant upper-left table region is recognized. The original
image remains untouched, and output boxes remain in original-image coordinates.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from paddleocr import PaddleOCR
from PIL import Image

from admissions_common import ROOT, ensure_utf8_stdio


IMAGE_ROOT = ROOT / "images" / "neu"
OCR_ROOT = ROOT / "ocr_results" / "neu"


def main() -> None:
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shard", type=int, required=True)
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--fast", action="store_true")
    parser.add_argument("--names", nargs="*")
    args = parser.parse_args()
    pending = [
        image
        for image in sorted(IMAGE_ROOT.glob("*"))
        if image.is_file()
        and not (OCR_ROOT / f"{image.stem}_res.json").exists()
    ]
    if args.names:
        name_set = set(args.names)
        selected = [path for path in pending if path.stem in name_set]
    else:
        selected = pending[args.shard::args.workers]
    if not selected:
        print("SHARD_EMPTY", args.shard)
        return
    OCR_ROOT.mkdir(parents=True, exist_ok=True)
    options = dict(
        lang="ch",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )
    if args.fast:
        options.update(
            text_det_limit_side_len=2800,
            text_det_limit_type="max",
            text_recognition_batch_size=8,
        )
    ocr = PaddleOCR(**options)
    for image_path in selected:
        output = OCR_ROOT / f"{image_path.stem}_res.json"
        if output.exists():
            continue
        image = Image.open(image_path)
        crop = image.crop(
            (
                0,
                0,
                int(image.width * 0.70),
                int(image.height * 0.80),
            )
        ).convert("RGB")
        outputs = ocr.predict(np.asarray(crop))
        payload = {
            "input_path": str(image_path),
            "model_settings": {
                "use_doc_preprocessor": False,
                "use_textline_orientation": False,
            },
            "crop_box": [0, 0, crop.width, crop.height],
            "rec_texts": [],
            "rec_scores": [],
            "rec_boxes": [],
        }
        for result in outputs:
            data = result.json
            data = data.get("res", data)
            payload["rec_texts"].extend(data.get("rec_texts", []))
            payload["rec_scores"].extend(data.get("rec_scores", []))
            payload["rec_boxes"].extend(data.get("rec_boxes", []))
        output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(
            "OCR_DONE",
            args.shard,
            image_path.name,
            len(payload["rec_texts"]),
        )


if __name__ == "__main__":
    main()
