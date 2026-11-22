"""东北大学 2026 招生计划：官方图片增量采集、PaddleOCR 和结构化输出。"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from admissions_common import (
    RESULTS,
    ROOT,
    connect_database,
    ensure_utf8_stdio,
    make_session,
    normalize,
    request_with_retries,
    school_summary,
    upsert_admission_records,
    write_csv,
    write_json,
)


LIST_ROOT = "https://zs.neu.edu.cn/2026n/"
PLAN_LIST_URL = f"{LIST_ROOT}list.htm"
IMAGE_ROOT = ROOT / "images" / "neu"
OCR_ROOT = ROOT / "ocr_results" / "neu"
OUTPUT_ROOT = RESULTS / "neu"
PROVINCES = [
    "北京", "天津", "河北", "山西", "内蒙古", "辽宁", "吉林", "黑龙江",
    "上海", "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南",
    "湖北", "湖南", "广东", "广西", "海南", "重庆", "四川", "贵州",
    "云南", "西藏", "陕西", "甘肃", "青海", "宁夏", "新疆",
]


def discover_images(session) -> dict[str, dict[str, str]]:
    result = {}
    response = request_with_retries(session, PLAN_LIST_URL)
    response.encoding = response.apparent_encoding or "utf-8"
    soup = BeautifulSoup(response.text, "html.parser")
    for anchor in soup.find_all("a", href=True):
        province = normalize(anchor.get_text(" ", strip=True))
        if province not in PROVINCES:
            continue
        image_url = urljoin(response.url, anchor["href"])
        result[province] = {
            "image_url": image_url,
            "list_url": PLAN_LIST_URL,
        }
    missing = [province for province in PROVINCES if province not in result]
    write_json(
        OUTPUT_ROOT / "source_pages.json",
        {
            "list_root": LIST_ROOT,
            "plan_list_url": PLAN_LIST_URL,
            "provinces": result,
            "missing": missing,
        },
    )
    if missing:
        raise RuntimeError(f"东北大学官方计划页缺少省份: {missing}")
    return result


def download_images(session, sources) -> None:
    IMAGE_ROOT.mkdir(parents=True, exist_ok=True)
    for province in PROVINCES:
        url = sources[province]["image_url"]
        extension = Path(urlparse(url).path).suffix.lower()
        if extension not in {".png", ".jpg", ".jpeg"}:
            extension = ".png"
        target = IMAGE_ROOT / f"{province}{extension}"
        if target.exists() and target.stat().st_size >= 15000:
            continue
        response = request_with_retries(session, url, timeout=45)
        if len(response.content) < 15000:
            raise RuntimeError(f"图片过小，疑似错误页: {url}")
        target.write_bytes(response.content)
        print("下载", province, target.stat().st_size)
        time.sleep(0.3)


def recognize_missing() -> None:
    pending = [
        path
        for path in sorted(IMAGE_ROOT.glob("*"))
        if path.is_file()
        and not (OCR_ROOT / f"{path.stem}_res.json").exists()
    ]
    if not pending:
        return
    from paddleocr import PaddleOCR

    OCR_ROOT.mkdir(parents=True, exist_ok=True)
    ocr = PaddleOCR(
        lang="ch",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )
    for path in pending:
        print("OCR", path.name)
        for result in ocr.predict(str(path)):
            result.save_to_json(str(OCR_ROOT))


def load_boxes(path: Path) -> list[dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload = payload.get("res", payload)
    boxes = []
    for text, score, raw_box in zip(
        payload.get("rec_texts", []),
        payload.get("rec_scores", []),
        payload.get("rec_boxes", []),
    ):
        value = normalize(text)
        if not value:
            continue
        x1, y1, x2, y2 = map(float, raw_box)
        if x2 <= x1 or y2 <= y1:
            continue
        boxes.append(
            {
                "text": value,
                "score": float(score),
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "x": (x1 + x2) / 2,
                "y": (y1 + y2) / 2,
            }
        )
    return boxes


def find_header(boxes, token, width, height, exact=True):
    matches = [
        box
        for box in boxes
        if (
            (box["text"] == token if exact else token in box["text"])
            and height * 0.09 < box["y"] < height * 0.22
        )
    ]
    return min(matches, key=lambda box: (box["y"], -box["score"])) if matches else None


def column_for(x, edges):
    names = ["major", "subject", "selection", "language", "fee", "count", "history"]
    for name, edge in zip(names, edges):
        if x < edge:
            return name
    return names[-1]


def join_cell(boxes, name, edges):
    selected = [box for box in boxes if column_for(box["x"], edges) == name]
    selected.sort(key=lambda box: (round(box["y"] / 2), box["x"]))
    return normalize("".join(box["text"] for box in selected))


def parse_image(path: Path, image_path: Path, source_url: str):
    boxes = load_boxes(path)
    width = max(box["x2"] for box in boxes)
    height = max(box["y2"] for box in boxes)
    headers = {
        "major": find_header(boxes, "招生专业(类)", width, height),
        "subject": find_header(boxes, "科类", width, height),
        "selection": find_header(boxes, "选考科目", width, height),
        "language": find_header(boxes, "语种", width, height),
        "fee": find_header(boxes, "学年学费", width, height),
        "count": find_header(
            boxes,
            "招生计划",
            width,
            height,
            exact=False,
        ),
    }
    centers = {
        "major": headers["major"]["x"] if headers["major"] else 0.15 * width,
        "subject": headers["subject"]["x"] if headers["subject"] else 0.32 * width,
        "selection": headers["selection"]["x"] if headers["selection"] else 0.38 * width,
        "language": headers["language"]["x"] if headers["language"] else 0.44 * width,
        "fee": headers["fee"]["x"] if headers["fee"] else 0.52 * width,
        "count": headers["count"]["x"] if headers["count"] else 0.60 * width,
        "history": min(
            [
                box["x"]
                for box in boxes
                if box["text"] == "最高分"
                and height * 0.09 < box["y"] < height * 0.22
            ]
            or [0.69 * width]
        ),
    }
    if headers["selection"] is None and headers["subject"] and headers["language"]:
        centers["selection"] = (
            centers["subject"] + centers["language"]
        ) / 2
    if headers["fee"] is None and headers["language"] and headers["count"]:
        centers["fee"] = (centers["language"] + centers["count"]) / 2
    names = [
        "major", "subject", "selection", "language",
        "fee", "count", "history",
    ]
    ordered = [centers[name] for name in names]
    if any(left >= right for left, right in zip(ordered, ordered[1:])):
        raise ValueError(f"列边界异常: {path.name}")
    edges = [(left + right) / 2 for left, right in zip(ordered, ordered[1:])]
    header_bottom = max(
        [box["y2"] for box in headers.values() if box is not None]
        or [height * 0.12]
    )
    anchors = [
        box
        for box in boxes
        if box["y1"] > header_bottom
        and edges[4] <= box["x"] < edges[5]
        and re.fullmatch(r"[1-9][0-9]{0,3}", box["text"])
        and int(box["text"]) <= 999
    ]
    anchors.sort(key=lambda box: box["y"])
    unique = []
    for anchor in anchors:
        if unique and abs(anchor["y"] - unique[-1]["y"]) < 8:
            if anchor["score"] > unique[-1]["score"]:
                unique[-1] = anchor
        else:
            unique.append(anchor)
    anchors = unique
    gaps = [
        right["y"] - left["y"]
        for left, right in zip(anchors, anchors[1:])
        if right["y"] > left["y"]
    ]
    row_gap = statistics.median(gaps) if gaps else 80
    rows = []
    for index, anchor in enumerate(anchors):
        low = (
            (anchors[index - 1]["y"] + anchor["y"]) / 2
            if index
            else header_bottom
        )
        high = (
            (anchor["y"] + anchors[index + 1]["y"]) / 2
            if index + 1 < len(anchors)
            else min(height, anchor["y"] + row_gap / 2)
        )
        band = [
            box
            for box in boxes
            if low <= box["y"] < high and box is not anchor
        ]
        major = join_cell(band, "major", edges)
        subject = join_cell(band, "subject", edges)
        selection = join_cell(band, "selection", edges)
        language = join_cell(band, "language", edges)
        fee = join_cell(band, "fee", edges)
        reasons = []
        if len(major) < 2 or re.search(r"(招生专业|合计|总计)", major):
            reasons.append("专业名称异常")
        if not subject:
            reasons.append("科类缺失")
        if anchor["score"] < 0.85:
            reasons.append("计划人数置信度偏低")
        rows.append(
            {
                "admission_year": 2026,
                "school": "东北大学",
                "province": image_path.stem,
                "college_name": "",
                "major_code": "",
                "major_name": major,
                "subject_type": subject,
                "batch_name": "",
                "plan_type": "",
                "selection_subject": selection
                + (f"；语种:{language}" if language else ""),
                "fee_text": fee,
                "planned_count": int(anchor["text"]),
                "source_url": source_url,
                "source_image": str(image_path.relative_to(ROOT)).replace("\\", "/"),
                "source_row": index + 1,
                "source_box": [
                    round(anchor["x1"], 2),
                    round(anchor["y1"], 2),
                    round(anchor["x2"], 2),
                    round(anchor["y2"], 2),
                ],
                "extraction_method": "OCR",
                "review_status": "待复核" if reasons else "自动校验通过",
                "review_reason": "；".join(reasons),
            }
        )
    return rows


def parse_local() -> list[dict[str, object]]:
    sources = {}
    source_file = OUTPUT_ROOT / "source_pages.json"
    if source_file.exists():
        sources = json.loads(source_file.read_text(encoding="utf-8")).get(
            "provinces", {}
        )
    rows = []
    missing = []
    for province in PROVINCES:
        matches = sorted(IMAGE_ROOT.glob(f"{province}.*"))
        ocr_file = OCR_ROOT / f"{province}_res.json"
        if not matches or not ocr_file.exists():
            missing.append(province)
            continue
        source_url = sources.get(province, {}).get(
            "list_url", PLAN_LIST_URL
        )
        page_rows = parse_image(ocr_file, matches[0], source_url)
        print(province, len(page_rows), sum(row["planned_count"] for row in page_rows))
        rows.extend(page_rows)
    write_csv(OUTPUT_ROOT / "neu_candidates.csv", rows)
    write_csv(
        OUTPUT_ROOT / "neu_province_summary.csv",
        school_summary(rows),
        ["school", "province", "records", "planned_count"],
    )
    write_json(OUTPUT_ROOT / "parse_status.json", {"missing": missing})
    print("TOTAL", len(rows), sum(row["planned_count"] for row in rows))
    print("MISSING", missing)
    return rows


def main() -> None:
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--crawl", action="store_true", help="下载缺失官方图片")
    parser.add_argument("--download-only", action="store_true")
    parser.add_argument("--ocr-only", action="store_true")
    parser.add_argument("--write-db", action="store_true")
    args = parser.parse_args()
    session = make_session()
    if args.crawl or args.download_only:
        sources = discover_images(session)
        download_images(session, sources)
    if args.ocr_only or (args.crawl and not args.download_only):
        recognize_missing()
    rows = parse_local()
    if args.write_db:
        connection = connect_database()
        try:
            print("DB_UPSERTED", upsert_admission_records(connection, rows))
        finally:
            connection.close()


if __name__ == "__main__":
    main()
