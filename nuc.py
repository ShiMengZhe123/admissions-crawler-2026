"""中北大学 2026 招生计划：增量采集、PaddleOCR 与结构化重建。

默认只读取现有图片和 OCR 结果。--crawl 仅下载/识别缺失文件。
--write-db 将解析后的候选记录幂等写入 admissions.admission_plan_v2。
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from admissions_common import (
    ADMISSION_FIELDS,
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


INDEX_URL = "https://zbzs.nuc.edu.cn/info/1016/4547.htm"
IMAGE_ROOT = ROOT / "images" / "nuc"
OCR_ROOT = ROOT / "ocr_results" / "nuc"
COUNT_REOCR_ROOT = OCR_ROOT / "_count_reocr"
OUTPUT_ROOT = RESULTS / "nuc"
MANUAL_CORRECTIONS = ROOT / "data" / "nuc_manual_corrections.csv"
PROVINCES = [
    "山西", "北京", "天津", "河北", "内蒙古", "辽宁", "吉林", "黑龙江",
    "上海", "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南",
    "湖北", "湖南", "广东", "广西", "海南", "重庆", "四川", "贵州",
    "云南", "西藏", "陕西", "甘肃", "青海", "宁夏", "新疆",
]
DEFAULT_RATIOS = {
    "code": 0.04,
    "college": 0.145,
    "major": 0.31,
    "subject": 0.44,
    "batch": 0.54,
    "count": 0.64,
    "fee": 0.72,
    "selection": 0.88,
}


def load_boxes(path: Path) -> list[dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload = payload.get("res", payload)
    boxes = []
    for index, (text, score, raw_box) in enumerate(
        zip(
            payload.get("rec_texts", []),
            payload.get("rec_scores", []),
            payload.get("rec_boxes", []),
        )
    ):
        text = normalize(text)
        if not text:
            continue
        x1, y1, x2, y2 = map(float, raw_box)
        if x2 <= x1 or y2 <= y1:
            continue
        boxes.append(
            {
                "text": text,
                "score": float(score),
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "x": (x1 + x2) / 2,
                "y": (y1 + y2) / 2,
                "index": index,
            }
        )
    return boxes


def detect_header(boxes, width: float, height: float) -> dict[str, object]:
    header_boxes = [box for box in boxes if box["y"] < height * 0.40]

    def find(tokens, low, high):
        matches = [
            box
            for box in header_boxes
            if (
                box["text"] in tokens
                or ("收费" in tokens and "收费" in box["text"])
            )
            and low <= box["x"] / width <= high
        ]
        if not matches:
            return None
        return min(matches, key=lambda box: (box["y"], -box["score"]))

    selected = {
        "college": find(("学院名称", "学院名"), 0.08, 0.35),
        "major": find(("专业名称", "专业名"), 0.15, 0.62),
        "subject": find(("科类",), 0.30, 0.85),
        "batch": find(("录取批次", "批次"), 0.40, 0.82),
        "count": find(("计划", "计划数", "合计"), 0.50, 0.92),
        "fee": find(("收费标准", "收费标", "收费"), 0.65, 0.99),
        "selection": find(
            ("选考科目", "选考", "定向地区"),
            0.70,
            1.0,
        ),
        "code": find(("代码",), 0.0, 0.09),
    }
    centers = {
        key: box["x"] for key, box in selected.items() if box is not None
    }
    if "college" in centers:
        code_boxes = [
            box
            for box in header_boxes
            if box["text"] in {"学院", "代码"} and box["x"] < centers["college"]
        ]
        if code_boxes:
            centers["code"] = sum(box["x"] for box in code_boxes) / len(code_boxes)
    required = {"college", "major", "subject", "count", "fee"}
    if not required.issubset(centers):
        return {}
    if selected:
        centers["__header_bottom__"] = max(
            box["y2"] for box in selected.values() if box is not None
        )
    return centers


def build_profile(boxes, first_boxes):
    width = max(box["x2"] for box in boxes)
    height = max(box["y2"] for box in boxes)
    first_width = max(box["x2"] for box in first_boxes)
    first_height = max(box["y2"] for box in first_boxes)
    detected = detect_header(boxes, width, height)
    base = detect_header(first_boxes, first_width, first_height)
    centers = {}
    for key, ratio in DEFAULT_RATIOS.items():
        if key in detected:
            centers[key] = detected[key]
        elif key in base:
            centers[key] = base[key] / first_width * width
        else:
            centers[key] = (1.02 if key == "selection" else ratio) * width
    if (
        "batch" not in detected
        and "batch" not in base
        and "subject" in centers
        and "count" in centers
    ):
        centers["batch"] = (centers["subject"] + centers["count"]) / 2
    names = [
        "code", "college", "major", "subject",
        "batch", "count", "fee", "selection",
    ]
    ordered = [centers[name] for name in names]
    reliable = bool(base) or bool(detected)
    if any(left >= right for left, right in zip(ordered, ordered[1:])):
        ordered = [DEFAULT_RATIOS[name] * width for name in names]
        reliable = False
    edges = [(left + right) / 2 for left, right in zip(ordered, ordered[1:])]
    return {
        "width": width,
        "height": height,
        "centers": dict(zip(names, ordered)),
        "edges": edges,
        "header_bottom": float(detected.get("__header_bottom__", 0))
        if detected
        else 0,
        "reliable": reliable,
    }


def column_for(x: float, edges: list[float]) -> str:
    names = [
        "code", "college", "major", "subject",
        "batch", "count", "fee", "selection",
    ]
    for name, edge in zip(names, edges):
        if x < edge:
            return name
    return names[-1]


def join_cell(boxes, name, edges) -> str:
    selected = [box for box in boxes if column_for(box["x"], edges) == name]
    selected.sort(key=lambda box: (round(box["y"] / 2), box["x"]))
    return normalize("".join(box["text"] for box in selected))


def filter_sidecar_anchors(raw_numbers, boxes, profile):
    count_center = profile["centers"]["count"]
    original_numeric = [
        box
        for box in boxes
        if box["text"].isdigit()
        and 1 <= int(box["text"]) <= 999
        and abs(box["x"] - count_center) <= 40
        and box["y"] > profile["header_bottom"]
    ]
    if not original_numeric:
        return None
    minimum_y = min(box["y"] for box in original_numeric)
    filtered = []
    for item in raw_numbers:
        x1, y1, x2, y2 = map(float, item["box"])
        center_x = (x1 + x2) / 2
        if abs(center_x - count_center) > 35:
            continue
        if float(item["score"]) < 0.90 or float(item["y"]) < minimum_y - 20:
            continue
        filtered.append(item)
    deduped = []
    for item in sorted(filtered, key=lambda value: float(value["y"])):
        if deduped and abs(float(item["y"]) - float(deduped[-1]["y"])) < 10:
            if float(item["score"]) > float(deduped[-1]["score"]):
                deduped[-1] = item
        else:
            deduped.append(item)
    merged = []
    used = set()
    for original in original_numeric:
        nearby = [
            (index, item)
            for index, item in enumerate(deduped)
            if abs(float(item["y"]) - original["y"]) <= 25
        ]
        if nearby:
            index, item = min(
                nearby,
                key=lambda pair: abs(float(pair[1]["y"]) - original["y"]),
            )
            used.add(index)
            merged.append(item)
        else:
            merged.append(
                {
                    "text": original["text"],
                    "score": original["score"],
                    "box": [
                        original["x1"], original["y1"],
                        original["x2"], original["y2"],
                    ],
                    "y": original["y"],
                }
            )
    merged.extend(item for index, item in enumerate(deduped) if index not in used)
    result = []
    for item in sorted(merged, key=lambda value: float(value["y"])):
        if result and abs(float(item["y"]) - float(result[-1]["y"])) < 10:
            if float(item["score"]) > float(result[-1]["score"]):
                result[-1] = item
        else:
            result.append(item)
    return result


def parse_page(boxes, first_boxes, sidecar=None):
    profile = build_profile(boxes, first_boxes)
    if not profile["reliable"] and sidecar:
        profile = build_profile(boxes, first_boxes)
        profile["centers"]["count"] = float(sidecar["count_center"])
        names = [
            "code", "college", "major", "subject",
            "batch", "count", "fee", "selection",
        ]
        ordered = [profile["centers"][name] for name in names]
        profile["edges"] = [
            (left + right) / 2 for left, right in zip(ordered, ordered[1:])
        ]
    supplied = None
    if sidecar:
        supplied = filter_sidecar_anchors(
            sidecar.get("numbers", []),
            boxes,
            profile,
        )
    edges = profile["edges"]
    top = float(profile["header_bottom"]) + 1
    count_left, count_right = edges[4], edges[5]
    if supplied is not None:
        anchors = [
            {
                "text": str(item["text"]),
                "score": float(item["score"]),
                "x1": float(item["box"][0]),
                "y1": float(item["box"][1]),
                "x2": float(item["box"][2]),
                "y2": float(item["box"][3]),
                "x": (float(item["box"][0]) + float(item["box"][2])) / 2,
                "y": float(item["y"]),
                "index": -1,
            }
            for item in supplied
        ]
    else:
        anchors = [
            box
            for box in boxes
            if box["y1"] > top
            and count_left <= box["x"] < count_right
            and re.fullmatch(r"[1-9][0-9]{0,3}", box["text"])
            and int(box["text"]) <= 999
        ]
    anchors.sort(key=lambda box: box["y"])
    unique = []
    for anchor in anchors:
        if unique and abs(anchor["y"] - unique[-1]["y"]) < 3:
            if anchor["score"] > unique[-1]["score"]:
                unique[-1] = anchor
        else:
            unique.append(anchor)
    anchors = unique
    if not anchors:
        return [], None, ["未检测到计划人数锚点"]
    gaps = [
        right["y"] - left["y"]
        for left, right in zip(anchors, anchors[1:])
        if right["y"] > left["y"]
    ]
    row_gap = statistics.median(gaps) if gaps else 32
    rows = []
    summary_count = None
    for index, anchor in enumerate(anchors):
        low = (
            (anchors[index - 1]["y"] + anchor["y"]) / 2
            if index
            else max(top, anchor["y"] - row_gap / 2)
        )
        high = (
            (anchor["y"] + anchors[index + 1]["y"]) / 2
            if index + 1 < len(anchors)
            else anchor["y"] + row_gap / 2
        )
        band = [
            box
            for box in boxes
            if low <= box["y"] < high and box is not anchor and box["y"] > top
        ]
        college = re.sub(r"\d+", "", join_cell(band, "college", edges))
        major = join_cell(band, "major", edges)
        subject = join_cell(band, "subject", edges)
        batch = join_cell(band, "batch", edges)
        fee = join_cell(band, "fee", edges)
        selection = join_cell(band, "selection", edges)
        if re.search(r"(合计|总计|小计|总结)", college + major + subject + batch):
            summary_count = int(anchor["text"])
            continue
        reasons = []
        if not profile["reliable"]:
            reasons.append("列边界回退")
        if len(college) < 2:
            reasons.append("学院名称异常")
        if (
            len(major) < 2
            or len(major) > 80
            or re.search(r"(专业名称|合计|总计|小计|\d{5,})", major)
        ):
            reasons.append("专业名称异常")
        if not subject:
            reasons.append("科类缺失")
        if not batch:
            reasons.append("批次缺失")
        if anchor["score"] < 0.85:
            reasons.append("计划人数置信度偏低")
        rows.append(
            {
                "admission_year": 2026,
                "school": "中北大学",
                "province": "",
                "college_name": college,
                "major_code": "",
                "major_name": major,
                "subject_type": subject,
                "batch_name": batch,
                "plan_type": batch,
                "selection_subject": selection,
                "fee_text": fee,
                "planned_count": int(anchor["text"]),
                "source_url": "",
                "source_image": "",
                "source_row": len(rows) + 1,
                "source_box": [
                    round(anchor["x1"], 2),
                    round(anchor["y1"], 2),
                    round(anchor["x2"], 2),
                    round(anchor["y2"], 2),
                ],
                "extraction_method": "OCR",
                "review_status": "待复核" if reasons else "自动校验通过",
                "review_reason": "；".join(reasons),
                "_anchor_y": anchor["y"],
            }
        )
    return rows, summary_count, []


def header_groups(boxes):
    levels = sorted(box["y"] for box in boxes if box["text"] == "专业名称")
    groups = []
    for y in levels:
        if not groups or y - groups[-1][-1] > 20:
            groups.append([y])
        else:
            groups[-1].append(y)
    return groups


def parse_sections(boxes):
    groups = header_groups(boxes)
    if len(groups) < 2:
        return parse_page(boxes, boxes)
    rows = []
    summaries = []
    issues = []
    height = max(box["y2"] for box in boxes)
    for index, group in enumerate(groups):
        top = max(0, group[0] - 40)
        bottom = (
            groups[index + 1][0] - 150
            if index + 1 < len(groups)
            else height
        )
        section_boxes = []
        for box in boxes:
            if not top <= box["y"] < bottom:
                continue
            shifted = dict(box)
            shifted["y1"] = box["y1"] - top
            shifted["y2"] = box["y2"] - top
            shifted["y"] = box["y"] - top
            section_boxes.append(shifted)
        if not section_boxes:
            continue
        section_rows, summary, section_issues = parse_page(
            section_boxes,
            section_boxes,
        )
        label_candidates = [
            box["text"]
            for box in boxes
            if max(0, group[0] - 260) <= box["y"] < group[0]
            and len(box["text"]) >= 6
            and ("计划" in box["text"] or "本科" in box["text"])
        ]
        section_label = max(
            label_candidates,
            key=lambda text: len(text),
            default="",
        )
        offset = len(rows)
        for row_index, row in enumerate(section_rows, start=1):
            row["source_row"] = offset + row_index
            row["source_box"][1] += top
            row["source_box"][3] += top
            if not row.get("plan_type"):
                row["plan_type"] = section_label
            rows.append(row)
        summaries.append(summary)
        issues.extend(section_issues)
    summary_count = (
        sum(summaries)
        if summaries and all(value is not None for value in summaries)
        else None
    )
    return rows, summary_count, issues


def discover_province_urls(session) -> dict[str, str]:
    response = request_with_retries(session, INDEX_URL)
    response.encoding = response.apparent_encoding or "utf-8"
    soup = BeautifulSoup(response.text, "html.parser")
    links = {}
    for anchor in soup.find_all("a", href=True):
        name = normalize(anchor.get_text(" ", strip=True))
        if name in PROVINCES:
            links[name] = urljoin(INDEX_URL, anchor["href"])
    write_json(
        OUTPUT_ROOT / "source_urls.json",
        {"index_url": INDEX_URL, "provinces": links},
    )
    return links


def crawl_missing(session, run_ocr: bool = True) -> None:
    links = discover_province_urls(session)
    missing_links = [province for province in PROVINCES if province not in links]
    if missing_links:
        raise RuntimeError(f"官网缺少省份链接: {missing_links}")
    for province in PROVINCES:
        image_dir = IMAGE_ROOT / province
        ocr_dir = OCR_ROOT / province
        image_dir.mkdir(parents=True, exist_ok=True)
        ocr_dir.mkdir(parents=True, exist_ok=True)
        if any(image_dir.glob("page_*.png")):
            continue
        response = request_with_retries(session, links[province])
        response.encoding = response.apparent_encoding or "utf-8"
        soup = BeautifulSoup(response.text, "html.parser")
        image_urls = []
        for image in soup.find_all("img"):
            source = (
                image.get("data-src")
                or image.get("data-original")
                or image.get("src")
            )
            if not source:
                continue
            url = urljoin(response.url, source)
            if urlparse(url).scheme not in {"http", "https"}:
                continue
            if url not in image_urls:
                image_urls.append(url)
        for index, url in enumerate(image_urls, 1):
            image_response = session.get(url, timeout=45)
            image_response.raise_for_status()
            extension = Path(urlparse(url).path).suffix.lower()
            if extension not in {".png", ".jpg", ".jpeg", ".webp"}:
                continue
            target = image_dir / f"page_{index:03d}{extension}"
            if not target.exists() and len(image_response.content) >= 15000:
                target.write_bytes(image_response.content)
        print(f"{province}: 图片 {len(list(image_dir.glob('page_*')))} 张")
    if not run_ocr:
        return
    pending = [
        image
        for image in IMAGE_ROOT.glob("*/*")
        if image.is_file()
        and not (OCR_ROOT / image.parent.name / f"{image.stem}_res.json").exists()
    ]
    if not pending:
        return
    from paddleocr import PaddleOCR

    ocr = PaddleOCR(
        lang="ch",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )
    for image in pending:
        outputs = ocr.predict(str(image))
        target_dir = OCR_ROOT / image.parent.name
        for result in outputs:
            result.save_to_json(str(target_dir))
        print("OCR:", image)


def parse_local() -> list[dict[str, object]]:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    url_file = OUTPUT_ROOT / "source_urls.json"
    url_map = {}
    if url_file.exists():
        url_map = json.loads(url_file.read_text(encoding="utf-8")).get(
            "provinces", {}
        )
    all_rows = []
    summaries = []
    errors = []
    for province in PROVINCES:
        files = sorted((OCR_ROOT / province).glob("*_res.json"))
        if not files:
            errors.append({"province": province, "image_name": "", "problem": "缺少 OCR"})
            continue
        reference_boxes = load_boxes(files[0])
        for result_file in files:
            image_name = result_file.name.removesuffix("_res.json")
            boxes = load_boxes(result_file)
            current_has_header = bool(
                detect_header(
                    boxes,
                    max(box["x2"] for box in boxes),
                    max(box["y2"] for box in boxes),
                )
            )
            sidecar_file = (
                COUNT_REOCR_ROOT / province / f"{image_name}_counts.json"
            )
            sidecar = (
                json.loads(sidecar_file.read_text(encoding="utf-8"))
                if sidecar_file.exists()
                else None
            )
            if len(header_groups(boxes)) >= 2:
                rows, summary_count, issues = parse_sections(boxes)
            else:
                rows, summary_count, issues = parse_page(
                    boxes, reference_boxes, sidecar=sidecar
                )
            if current_has_header:
                reference_boxes = boxes
            source_url = url_map.get(province, INDEX_URL)
            parsed_count = sum(row["planned_count"] for row in rows)
            for row in rows:
                row["province"] = province
                row["source_url"] = source_url
                row["source_image"] = (
                    f"images/nuc/{province}/{image_name}.png"
                )
                if (
                    summary_count is not None
                    and parsed_count != summary_count
                ):
                    extra = (
                        f"页面明细合计 {parsed_count} 与页面汇总 "
                        f"{summary_count} 不一致，需复核"
                    )
                    row["review_reason"] = "；".join(
                        value
                        for value in (row["review_reason"], extra)
                        if value
                    )
                    if row["review_status"] == "自动校验通过":
                        row["review_status"] = "待复核"
            all_rows.extend(rows)
            summaries.append(
                {
                    "province": province,
                    "image_name": image_name,
                    "parsed_rows": len(rows),
                    "parsed_count": parsed_count,
                    "source_summary": summary_count,
                }
            )
            for issue in issues:
                errors.append(
                    {
                        "province": province,
                        "image_name": image_name,
                        "problem": issue,
                    }
                )
            print(province, image_name, len(rows), parsed_count)
    if MANUAL_CORRECTIONS.exists():
        with MANUAL_CORRECTIONS.open(
            encoding="utf-8-sig", newline=""
        ) as handle:
            corrections = list(csv.DictReader(handle))
        for correction in corrections:
            for row in all_rows:
                if (
                    row["province"] == correction["province"]
                    and Path(row["source_image"]).stem
                    == correction["image_name"]
                    and int(row["source_row"])
                    == int(correction["source_row"])
                ):
                    field = correction["field"]
                    if field not in ADMISSION_FIELDS:
                        raise ValueError(f"未知人工校正字段: {field}")
                    row[field] = correction["value"]
                    reason = correction["reason"]
                    row["review_reason"] = "；".join(
                        value
                        for value in (row["review_reason"], reason)
                        if value
                    )
                    row["review_status"] = "人工校正待复核"
                    break
    write_csv(OUTPUT_ROOT / "nuc_candidates_final.csv", all_rows)
    write_csv(
        OUTPUT_ROOT / "nuc_review_priority.csv",
        [
            row
            for row in all_rows
            if row["review_status"] != "自动校验通过"
        ],
    )
    write_csv(
        OUTPUT_ROOT / "nuc_page_summary.csv",
        summaries,
        [
            "province", "image_name", "parsed_rows",
            "parsed_count", "source_summary",
        ],
    )
    write_csv(
        OUTPUT_ROOT / "nuc_parse_errors.csv",
        errors,
        ["province", "image_name", "problem"],
    )
    write_csv(
        OUTPUT_ROOT / "nuc_province_summary.csv",
        school_summary(all_rows),
        ["school", "province", "records", "planned_count"],
    )
    print("TOTAL", len(all_rows), sum(row["planned_count"] for row in all_rows))
    print("PROVINCES", len({row["province"] for row in all_rows}))
    print("OUTPUT", OUTPUT_ROOT)
    return all_rows


def main() -> None:
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--crawl", action="store_true", help="增量下载缺失图片")
    parser.add_argument("--no-ocr", action="store_true", help="只下载不识别")
    parser.add_argument("--write-db", action="store_true", help="幂等写入 MySQL")
    args = parser.parse_args()
    session = make_session()
    if args.crawl:
        crawl_missing(session, run_ocr=not args.no_ocr)
    rows = parse_local()
    if args.write_db:
        connection = connect_database()
        try:
            count = upsert_admission_records(connection, rows)
            print("DB_UPSERTED", count)
        finally:
            connection.close()


if __name__ == "__main__":
    main()
