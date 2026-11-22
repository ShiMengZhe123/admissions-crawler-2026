
import argparse
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from paddleocr import PaddleOCR


# ========== 1. 基础设置 ==========

BASE_DIR = Path(__file__).resolve().parent

IMAGE_DIR = BASE_DIR / "images" / "nuc"
RESULT_DIR = BASE_DIR / "ocr_results" / "nuc"

IMAGE_DIR.mkdir(parents=True, exist_ok=True)
RESULT_DIR.mkdir(parents=True, exist_ok=True)

INDEX_URL = "https://zbzs.nuc.edu.cn/info/1016/4547.htm"

PROVINCES = [
    "山西", "北京", "天津", "河北", "内蒙古",
    "辽宁", "吉林", "黑龙江", "上海", "江苏",
    "浙江", "安徽", "福建", "江西", "山东",
    "河南", "湖北", "湖南", "广东", "广西",
    "海南", "重庆", "四川", "贵州", "云南",
    "西藏", "陕西", "甘肃", "青海", "宁夏",
    "新疆"
]

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
})


# ========== 2. 请求网页 ==========

def get_page(url):
    print("正在访问：", url)

    response = session.get(url, timeout=30)
    response.raise_for_status()
    response.encoding = response.apparent_encoding

    return BeautifulSoup(response.text, "html.parser")


# ========== 3. 获取各省链接 ==========

def get_province_links():
    soup = get_page(INDEX_URL)
    links = {}

    for a in soup.find_all("a", href=True):
        name = a.get_text(" ", strip=True)
        name = re.sub(r"\s+", "", name)

        if name in PROVINCES:
            links[name] = urljoin(INDEX_URL, a["href"])

    print(f"发现 {len(links)} 个省份链接")
    return links


# ========== 4. 提取正文图片地址 ==========

def get_image_urls(page_url):
    soup = get_page(page_url)

    # 优先寻找学校新闻系统的正文区域
    selectors = [
        "#vsb_content",
        "#vsb_content_2",
        ".v_news_content",
        ".wp_articlecontent",
        ".article-content"
    ]

    content = None

    for selector in selectors:
        content = soup.select_one(selector)
        if content and content.find("img"):
            break
        content = None

    if content is None:
        print("未找到标准正文区域，尝试页面图片筛选")
        content = soup

    image_urls = []

    for img in content.find_all("img"):
        src = (
            img.get("data-src")
            or img.get("data-original")
            or img.get("src")
        )

        if not src:
            continue

        url = urljoin(page_url, src)

        if not url.startswith(("http://", "https://")):
            continue

        # 排除 data URL 和重复图片
        if url not in image_urls:
            image_urls.append(url)

    print("发现候选图片：", len(image_urls))
    return image_urls


# ========== 5. 自动下载图片 ==========

def download_images(province, page_url):
    folder = IMAGE_DIR / province
    folder.mkdir(parents=True, exist_ok=True)

    urls = get_image_urls(page_url)
    downloaded = []

    for index, url in enumerate(urls, 1):
        try:
            response = session.get(url, timeout=45)
            response.raise_for_status()

            content_type = response.headers.get(
                "Content-Type", ""
            ).lower()

            path = urlparse(url).path.lower()

            if "png" in content_type or path.endswith(".png"):
                ext = ".png"
            elif "jpeg" in content_type or "jpg" in content_type:
                ext = ".jpg"
            elif path.endswith((".jpg", ".jpeg")):
                ext = ".jpg"
            elif "webp" in content_type:
                ext = ".webp"
            else:
                continue

            # 排除网页图标等极小图片
            if len(response.content) < 15000:
                continue

            file_path = folder / f"page_{index:03d}{ext}"

            if not file_path.exists():
                file_path.write_bytes(response.content)

            downloaded.append(file_path)

            print("下载成功：", file_path.name)
            time.sleep(0.3)

        except requests.RequestException as e:
            print("图片下载失败：", url, e)

    print(f"{province}：保存 {len(downloaded)} 张候选图片")
    return downloaded


# ========== 6. OCR 识别 ==========

def recognize_images(ocr, province, files):
    province_result = RESULT_DIR / province
    province_result.mkdir(parents=True, exist_ok=True)

    for image_path in files:
        print("正在识别：", province, image_path.name)

        try:
            results = ocr.predict(str(image_path))

            all_lines = []

            for result in results:
                result.save_to_json(str(province_result))

                data = result.json
                data = data.get("res", data)

                texts = data.get("rec_texts", [])
                scores = data.get("rec_scores", [])

                for text, score in zip(texts, scores):
                    all_lines.append({
                        "text": str(text),
                        "confidence": float(score)
                    })

            output_file = (
                province_result
                / f"{image_path.stem}_ocr.json"
            )

            output_file.write_text(
                json.dumps(
                    all_lines,
                    ensure_ascii=False,
                    indent=2
                ),
                encoding="utf-8"
            )

            print("识别完成：", len(all_lines), "个文本框")

        except Exception as e:
            print("OCR 识别失败：", image_path, e)


# ========== 7. 主程序 ==========

def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--all",
        action="store_true",
        help="处理全部省份"
    )

    parser.add_argument(
        "--download-only",
        action="store_true",
        help="只下载图片，不执行OCR"
    )

    args = parser.parse_args()

    province_links = get_province_links()

    if args.all:
        selected = list(province_links.items())
    else:
        if "山西" not in province_links:
            raise RuntimeError("未找到山西省链接")

        selected = [("山西", province_links["山西"])]

    ocr = None

    if not args.download_only:
        print("正在初始化 PaddleOCR...")

        ocr = PaddleOCR(
            lang="ch",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False
        )

    for province, url in selected:
        try:
            print("\n==========", province, "==========")

            files = download_images(province, url)

            if ocr is not None and files:
                recognize_images(ocr, province, files)

            time.sleep(1)

        except Exception as e:
            print(province, "处理失败：", e)

    print("\n本轮处理结束")
    print("图片目录：", IMAGE_DIR)
    print("OCR目录：", RESULT_DIR)


if __name__ == "__main__":
    main()
