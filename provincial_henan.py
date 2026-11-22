"""河南省阳光高考官方院校计划页面增量采集。

The official page embeds the current year's plan in a flat JavaScript list.
This module preserves the original HTML and records exactly what was parsed.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup

from admissions_common import (
    ROOT,
    make_session,
    request_with_retries,
    write_json,
)


SCHOOL_CODES = {
    "河北工业大学": "10080",
    "上海财经大学": "10272",
}
SOURCE_ROOT = ROOT / "evidence" / "official_sources" / "henan"
OUTPUT_ROOT = ROOT / "results" / "henan"


def _extract_array(text: str, marker: str) -> str:
    marker_index = text.find(marker)
    if marker_index < 0:
        raise ValueError(f"未找到 {marker}")
    start = text.find("[", marker_index)
    if start < 0:
        raise ValueError(f"{marker} 后没有数组")
    depth = 0
    quote = None
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return text[start + 1:index]
    raise ValueError(f"{marker} 数组未闭合")


def _parse_js_records(body: str) -> list[dict[str, str]]:
    records = []
    for match in re.finditer(r"\{([^{}]*)\}", body, re.S):
        object_text = match.group(1)
        fields = {}
        for field in re.finditer(
            r"""(?m)^\s*([A-Za-z_]\w*)\s*:\s*('(?:\\.|[^'])*'|"(?:\\.|[^"])*")\s*,?""",
            object_text,
        ):
            key = field.group(1)
            raw = field.group(2)[1:-1]
            value = (
                raw.replace("\\'", "'")
                .replace('\\"', '"')
                .replace("\\n", "\n")
                .replace("\\r", "")
            )
            fields[key] = value.strip()
        if fields:
            records.append(fields)
    return records


def fetch_official_plans(school: str) -> list[dict[str, object]]:
    if school not in SCHOOL_CODES:
        raise ValueError(f"不支持的学校: {school}")
    gb_code = SCHOOL_CODES[school]
    url = f"https://{gb_code}.gaokao.haedu.cn/schoolPlan.html"
    session = make_session()
    response = request_with_retries(session, url)
    response.encoding = response.apparent_encoding or "utf-8"
    html = response.text
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    if school not in title:
        raise ValueError(f"官方页面学校不匹配: {title}")

    data_script = next(
        (
            script.get_text()
            for script in soup.find_all("script")
            if "history_list" in script.get_text()
        ),
        None,
    )
    if not data_script:
        raise ValueError("官方页面没有 history_list")
    body = _extract_array(data_script, "history_list:")
    raw_records = _parse_js_records(body)
    total_match = re.search(r"total\s*:\s*(\d+)", data_script)
    declared_total = int(total_match.group(1)) if total_match else None
    year_records = [row for row in raw_records if row.get("year") == "2026"]
    if declared_total is not None and len(year_records) != declared_total:
        raise ValueError(
            f"2026 记录数 {len(year_records)} 与页面 total {declared_total} 不一致"
        )

    SOURCE_ROOT.mkdir(parents=True, exist_ok=True)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(response.content).hexdigest()
    html_path = SOURCE_ROOT / f"{gb_code}_{school}_2026.html"
    html_path.write_bytes(response.content)
    fetch_log = {
        "school": school,
        "source": url,
        "final_url": response.url,
        "fetched_at": datetime.now().astimezone().isoformat(),
        "http_status": response.status_code,
        "bytes": len(response.content),
        "sha256": digest,
        "title": title,
        "declared_total": declared_total,
        "parsed_2026": len(year_records),
        "html_snapshot": str(html_path.relative_to(ROOT)).replace("\\", "/"),
    }
    write_json(SOURCE_ROOT / f"{gb_code}_{school}_fetch.json", fetch_log)

    output = []
    for index, raw in enumerate(year_records, start=1):
        planned_count = re.sub(r"\D", "", raw.get("major_plan", ""))
        if not planned_count:
            continue
        notes = "；".join(
            value
            for value in (
                raw.get("major_group_code", ""),
                raw.get("direction", ""),
                raw.get("major_group_remark", ""),
                raw.get("major_remark", ""),
            )
            if value
        )
        output.append(
            {
                "admission_year": 2026,
                "school": school,
                "province": "河南",
                "college_name": "",
                "major_code": raw.get("major_nature_code", ""),
                "major_name": raw.get("major_name", ""),
                "subject_type": raw.get("first_choice", ""),
                "batch_name": raw.get("batch", ""),
                "plan_type": raw.get("ZYZBeizhu", ""),
                "selection_subject": raw.get("major_optional_require", ""),
                "fee_text": raw.get("tuition", ""),
                "planned_count": int(planned_count),
                "source_url": url,
                "source_image": "",
                "source_row": index,
                "source_box": [],
                "extraction_method": "HTML-JS",
                "review_status": "官方页面校验通过",
                "review_reason": notes,
            }
        )
    if len(output) != len(year_records):
        raise ValueError(
            f"有效计划记录 {len(output)} 少于官方 2026 总记录 {len(year_records)}"
        )
    return output
