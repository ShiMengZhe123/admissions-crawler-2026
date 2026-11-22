"""Render an image-only management report for the admissions project."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "boss_report"
PAGES = OUTPUT / "pages"
DATABASE_SCREENSHOT = (
    ROOT / "results" / "database" / "datagrip_query_result.png"
)
OCR_CONTACT_SHEET = (
    ROOT / "results" / "validation" / "contact_sheets" / "sheet_01.png"
)

WIDTH = 1920
HEIGHT = 1080

NAVY = "#0B1F3A"
NAVY_2 = "#123A5A"
BLUE = "#1687F8"
CYAN = "#37C2D9"
GREEN = "#1EAF78"
AMBER = "#F2B544"
RED = "#E15D5D"
INK = "#17263A"
MUTED = "#607089"
BG = "#F3F6FA"
CARD = "#FFFFFF"
LINE = "#DEE6EF"

FONT_REGULAR = Path(r"C:\Windows\Fonts\msyh.ttc")
FONT_BOLD = Path(r"C:\Windows\Fonts\msyhbd.ttc")


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_BOLD if bold else FONT_REGULAR), size)


def gradient(size: tuple[int, int], start: str, end: str) -> Image.Image:
    image = Image.new("RGB", size)
    top = tuple(int(start[i : i + 2], 16) for i in (1, 3, 5))
    bottom = tuple(int(end[i : i + 2], 16) for i in (1, 3, 5))
    pixels = image.load()
    for y in range(size[1]):
        ratio = y / max(1, size[1] - 1)
        color = tuple(
            int(top[index] * (1 - ratio) + bottom[index] * ratio)
            for index in range(3)
        )
        for x in range(size[0]):
            pixels[x, y] = color
    return image


def wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    text_font: ImageFont.FreeTypeFont,
    max_width: int,
) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines():
        if not paragraph:
            lines.append("")
            continue
        current = ""
        for char in paragraph:
            candidate = current + char
            if draw.textlength(candidate, font=text_font) <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = char
        if current:
            lines.append(current)
    return lines


def draw_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    text_font: ImageFont.FreeTypeFont,
    fill: str = INK,
    max_width: int | None = None,
    spacing: int = 8,
) -> int:
    x, y = xy
    if max_width is None:
        draw.text((x, y), text, font=text_font, fill=fill)
        return y + int(text_font.size)
    lines = wrap_text(draw, text, text_font, max_width)
    line_height = int(text_font.size * 1.38) + spacing
    for index, line in enumerate(lines):
        draw.text((x, y + index * line_height), line, font=text_font, fill=fill)
    return y + len(lines) * line_height


def rounded_card(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    fill: str = CARD,
    outline: str | None = None,
    radius: int = 22,
    width: int = 2,
) -> None:
    draw.rounded_rectangle(
        box,
        radius=radius,
        fill=fill,
        outline=outline,
        width=width if outline else 0,
    )


def pill(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    fill: str,
    text_fill: str = "white",
    size: int = 22,
) -> tuple[int, int, int, int]:
    text_font = font(size, True)
    padding_x = 20
    height = size + 20
    width = int(draw.textlength(text, font=text_font)) + padding_x * 2
    box = (xy[0], xy[1], xy[0] + width, xy[1] + height)
    draw.rounded_rectangle(box, radius=height // 2, fill=fill)
    draw.text(
        (xy[0] + padding_x, xy[1] + (height - size) // 2 - 2),
        text,
        font=text_font,
        fill=text_fill,
    )
    return box


def standard_page(title: str, subtitle: str, page_number: int) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, WIDTH, 12), fill=NAVY)
    draw.rectangle((0, 12, 270, 18), fill=CYAN)
    draw.rectangle((270, 12, 460, 18), fill=GREEN)
    draw.rectangle((460, 12, 590, 18), fill=AMBER)
    draw.text((88, 58), title, font=font(50, True), fill=NAVY)
    draw.text((90, 126), subtitle, font=font(24), fill=MUTED)
    draw.text(
        (WIDTH - 150, HEIGHT - 52),
        f"{page_number:02d}",
        font=font(24, True),
        fill=MUTED,
    )
    draw.line((88, 172, WIDTH - 88, 172), fill=LINE, width=2)
    return image


def fit_image(path: Path, size: tuple[int, int]) -> Image.Image:
    image = Image.open(path).convert("RGB")
    image.thumbnail(size, Image.Resampling.LANCZOS)
    return image


def paste_with_shadow(
    base: Image.Image,
    image: Image.Image,
    xy: tuple[int, int],
    radius: int = 18,
) -> None:
    x, y = xy
    shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle(
        (x + 8, y + 12, x + image.width + 8, y + image.height + 12),
        radius=radius,
        fill=(8, 26, 46, 38),
    )
    base.alpha_composite(shadow) if base.mode == "RGBA" else base.paste(
        Image.alpha_composite(base.convert("RGBA"), shadow).convert("RGB")
    )
    base.paste(image, (x, y))


def page_cover() -> Image.Image:
    image = gradient((WIDTH, HEIGHT), "#061629", "#123E5D").convert("RGB")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.ellipse((1320, -200, 2220, 700), fill=(55, 194, 217, 28))
    draw.ellipse((-220, 720, 660, 1600), fill=(22, 135, 248, 20))
    draw.line((90, 190, 430, 190), fill=CYAN, width=8)
    image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(image)

    pill(draw, (90, 82), "2026 招生计划 · 爬虫与 OCR", "#1A668A", size=24)
    draw.text(
        (90, 210),
        "五校招生计划采集与数据入库",
        font=font(72, True),
        fill="white",
    )
    draw.text(
        (94, 310),
        "项目交付汇报",
        font=font(46, True),
        fill="#7FE1EF",
    )
    draw.text(
        (96, 380),
        "Python / PaddleOCR / PaddlePaddle / MySQL",
        font=font(28),
        fill="#C8D8E7",
    )

    metrics = [
        ("5", "所高校"),
        ("3047", "入库存档记录"),
        ("17447", "计划人数"),
        ("144/144", "OCR 抽样正确"),
    ]
    positions = [90, 520, 950, 1380]
    widths = [360, 360, 360, 360]
    for (value, label), x, box_width in zip(metrics, positions, widths):
        rounded_card(draw, (x, 610, x + box_width, 842), "#0F2D47", "#2F617C")
        draw.text((x + 28, 642), value, font=font(48, True), fill="white")
        draw.text((x + 30, 718), label, font=font(23), fill="#AFC4D8")

    draw.text(
        (92, 930),
        "真实官方来源  ·  全量留痕  ·  不预测  ·  不伪造截图",
        font=font(26, True),
        fill="#D7E5F1",
    )
    draw.text(
        (92, 982),
        "报告日期  2026-11-22",
        font=font(22),
        fill="#9BB2C7",
    )
    return image


def page_requirements() -> Image.Image:
    image = standard_page(
        "题目要求原文",
        "保留原始任务口径，交付结果按此逐项核验",
        2,
    )
    draw = ImageDraw.Draw(image)
    rounded_card(draw, (88, 210, 1100, 942), NAVY, None, 26)
    draw.text((126, 244), "机试题原文", font=font(30, True), fill="#7FE1EF")
    original = (
        "基于开发环境Python/PaddleOCR/PaddlePaddle，实现爬虫程序，"
        "爬取当年招生计划，识别率达到95%。\n\n"
        "选择爬虫作为机试题，是因为它包含了数据获取、数据处理、数据存储等，"
        "算是最完整的一个项目。爬取成功后，插入MySQL数据库，查询结果集，"
        "截图发过来就可以。\n\n"
        "以中北大学、山西师范大学、东北大学、上海财经大学、河北工业大学"
        "官网为例。每个学校单独一个文件。"
    )
    draw_text(
        draw,
        (126, 310),
        original,
        font(29),
        fill="#EEF6FC",
        max_width=920,
        spacing=12,
    )
    pill(draw, (126, 858), "交付核心：能爬、能识别、能入库、能查询、能截图", "#1A668A", size=21)

    rounded_card(draw, (1145, 210, 1832, 942), CARD, LINE, 26)
    draw.text((1185, 245), "执行原则（来自追加要求）", font=font(30, True), fill=NAVY)
    principles = [
        ("01", "官方优先", "学校主站、招生网、官方公开附件优先。"),
        ("02", "合法增量", "官网不足时，采用各省考试院 2026 官方计划。"),
        ("03", "全程留痕", "保留 URL、时间、HTML/图片、日志和 SHA-256。"),
        ("04", "数据红线", "禁止预测数据、其他年份数据和伪造截图。"),
    ]
    y = 330
    for number, title, body in principles:
        draw.ellipse((1185, y, 1249, y + 64), fill=NAVY)
        draw.text((1205, y + 10), number, font=font(19, True), fill="white")
        draw.text((1271, y + 2), title, font=font(27, True), fill=NAVY)
        draw_text(
            draw,
            (1271, y + 42),
            body,
            font(22),
            fill=MUTED,
            max_width=500,
        )
        y += 133
    return image


def page_scorecard() -> Image.Image:
    image = standard_page(
        "交付总览",
        "核心功能已完成；数据范围为三校完整、两校省级官方增量",
        3,
    )
    draw = ImageDraw.Draw(image)
    rounded_card(draw, (88, 208, 660, 941), NAVY, None, 28)
    draw.text((128, 250), "当前结论", font=font(30, True), fill="#7FE1EF")
    draw_text(
        draw,
        (128, 330),
        "项目已经具备可运行、可复现、可入库、可验收的完整技术链路。",
        font(40, True),
        fill="white",
        max_width=480,
    )
    draw_text(
        draw,
        (128, 520),
        "三所学校完成较完整的官方数据采集；上海财经大学、河北工业大学"
        "目前仅有河南省级官方增量，尚不能申报全国完整。",
        font(25),
        fill="#C9D8E6",
        max_width=480,
    )
    pill(draw, (128, 810), "可用于项目演示与阶段验收", "#1A668A", size=22)

    items = [
        ("Python 爬虫与解析", "完成", GREEN),
        ("五校独立文件", "完成", GREEN),
        ("OCR 95% 抽样验收", "144/144", GREEN),
        ("MySQL 建表与入库", "3047 条", GREEN),
        ("查询结果截图", "真实 DataGrip", GREEN),
        ("五校官网完整范围", "3 完整 + 2 增量", AMBER),
    ]
    card_width = 540
    card_height = 210
    positions = [
        (720, 210), (1294, 210),
        (720, 458), (1294, 458),
        (720, 706), (1294, 706),
    ]
    for (title, status, color), (x, y) in zip(items, positions):
        rounded_card(draw, (x, y, x + card_width, y + card_height), CARD, LINE, 22)
        draw.text((x + 28, y + 28), title, font=font(25, True), fill=NAVY)
        pill(draw, (x + 28, y + 88), status, color, size=22)
        draw.line((x + 28, y + 155, x + card_width - 28, y + 155), fill=LINE, width=2)
        draw.text(
            (x + 28, y + 170),
            "验收证据已归档" if color == GREEN else "缺口已明确标注",
            font=font(20),
            fill=MUTED,
        )
    return image


def page_architecture() -> Image.Image:
    image = standard_page(
        "技术架构与可复现流程",
        "从官方来源到 MySQL 查询截图的全链路",
        4,
    )
    draw = ImageDraw.Draw(image)
    stages = [
        ("01", "官方来源", ["学校官网", "招生网 / 附件", "省级考试院"], BLUE),
        ("02", "数据获取", ["requests / HTML", "官方图片", "低频合法采集"], CYAN),
        ("03", "识别与解析", ["PaddleOCR", "动态列定位", "表格规则解析"], GREEN),
        ("04", "治理与入库", ["标准化 / 去重", "复核状态", "MySQL 幂等 upsert"], AMBER),
        ("05", "交付证明", ["CSV / JSON / SQL", "DataGrip 截图", "自动测试报告"], RED),
    ]
    x_positions = [88, 444, 800, 1156, 1512]
    box_width = 300
    box_height = 600
    for (number, title, bullets, color), x in zip(stages, x_positions):
        rounded_card(draw, (x, 245, x + box_width, 245 + box_height), CARD, LINE, 24)
        draw.ellipse((x + 24, 270, x + 92, 338), fill=color)
        draw.text((x + 43, 281), number, font=font(21, True), fill="white")
        draw.text((x + 24, 365), title, font=font(28, True), fill=NAVY)
        y = 435
        for bullet in bullets:
            draw.ellipse((x + 28, y + 8, x + 40, y + 20), fill=color)
            draw_text(
                draw,
                (x + 54, y),
                bullet,
                font(21),
                fill=MUTED,
                max_width=215,
            )
            y += 70
        draw.rectangle((x + 24, 720, x + box_width - 24, 728), fill=color)
        draw.text(
            (x + 24, 754),
            "可复现、可审计",
            font=font(20, True),
            fill=MUTED,
        )
        if x != x_positions[-1]:
            draw.line((x + 312, 545, x + 444, 545), fill="#9CB1C5", width=5)
            draw.polygon(
                [(x + 444, 545), (x + 425, 533), (x + 425, 557)],
                fill="#9CB1C5",
            )
    rounded_card(draw, (88, 890, 1832, 982), "#E8F1FA", None, 18)
    draw.text(
        (118, 914),
        "复现入口：selftest.py  →  各校独立脚本  →  MySQL 入库  →  db_tools.py queries  →  截图/报告",
        font=font(24, True),
        fill=NAVY,
    )
    return image


def page_results() -> Image.Image:
    image = standard_page(
        "五校数据结果",
        "数据库实际汇总：3047 条记录、17447 名计划人数",
        5,
    )
    draw = ImageDraw.Draw(image)
    cards = [
        ("5", "学校"),
        ("3047", "记录"),
        ("17447", "计划人数"),
        ("93", "省份维度记录"),
    ]
    for index, (value, label) in enumerate(cards):
        x = 88 + index * 430
        rounded_card(draw, (x, 210, x + 395, 330), CARD, LINE, 20)
        draw.text((x + 24, 232), value, font=font(40, True), fill=NAVY)
        draw.text((x + 26, 288), label, font=font(20), fill=MUTED)

    rounded_card(draw, (88, 365, 1140, 930), CARD, LINE, 24)
    draw.text((120, 395), "学校明细", font=font(28, True), fill=NAVY)
    headers = ["学校", "记录", "计划人数", "范围状态"]
    x_columns = [124, 600, 725, 875]
    for label, x in zip(headers, x_columns):
        draw.text((x, 454), label, font=font(20, True), fill=MUTED)
    draw.line((120, 494, 1104, 494), fill=LINE, width=2)
    rows = [
        ("中北大学", "1486", "7594", "31 省"),
        ("山西师范大学", "758", "5100", "官网全表"),
        ("东北大学", "746", "4596", "31 省"),
        ("上海财经大学", "34", "84", "河南增量"),
        ("河北工业大学", "23", "73", "河南增量"),
        ("合计", "3047", "17447", "五校"),
    ]
    y = 515
    for index, row in enumerate(rows):
        if index == len(rows) - 1:
            draw.rectangle((116, y - 10, 1110, y + 62), fill="#E9F3FC")
        text_fill = NAVY if index == len(rows) - 1 else INK
        draw.text((124, y), row[0], font=font(22, True if index == 5 else False), fill=text_fill)
        draw.text((600, y), row[1], font=font(22, True), fill=text_fill)
        draw.text((735, y), row[2], font=font(22, True), fill=text_fill)
        status_color = GREEN if "省" in row[3] or "全表" in row[3] else AMBER if "增量" in row[3] else BLUE
        draw.text((875, y), row[3], font=font(20, True), fill=status_color)
        y += 62

    rounded_card(draw, (1175, 365, 1832, 930), CARD, LINE, 24)
    draw.text((1210, 395), "计划人数对比", font=font(28, True), fill=NAVY)
    chart_rows = [
        ("中北大学", 7594, BLUE),
        ("山西师范", 5100, CYAN),
        ("东北大学", 4596, GREEN),
        ("上海财大", 84, AMBER),
        ("河北工大", 73, RED),
    ]
    y = 475
    max_value = 8000
    for name, value, color in chart_rows:
        draw.text((1210, y), name, font=font(20), fill=INK)
        draw.rounded_rectangle((1360, y + 3, 1760, y + 31), radius=14, fill="#E7EDF4")
        bar_width = max(12, int((value / max_value) * 400))
        draw.rounded_rectangle((1360, y + 3, 1360 + bar_width, y + 31), radius=14, fill=color)
        draw.text((1772, y), f"{value}", font=font(19, True), fill=NAVY)
        y += 82
    rounded_card(draw, (1210, 875, 1795, 915), "#FFF3D8", None, 16)
    draw.text(
        (1232, 884),
        "两校人数较低是因为目前仅覆盖河南官方增量",
        font=font(18, True),
        fill="#8A6117",
    )
    return image


def page_sources() -> Image.Image:
    image = standard_page(
        "官方来源与可追溯性",
        "数据来源、访问状态与留痕证据",
        6,
    )
    draw = ImageDraw.Draw(image)
    source_cards = [
        (
            "中北大学",
            "学校招生信息网",
            "42 张官方图片",
            "31 省 · 1486 条 / 7594 人",
            GREEN,
            "zbzs.nuc.edu.cn",
        ),
        (
            "山西师范大学",
            "学校官方 HTML 主表",
            "HTML 可复现解析",
            "758 条 / 5100 人",
            GREEN,
            "zsb.sxnu.edu.cn",
        ),
        (
            "东北大学",
            "学校官方 2026 图片页",
            "31 张高清图片 + OCR",
            "31 省 · 746 条 / 4596 人",
            GREEN,
            "zs.neu.edu.cn",
        ),
        (
            "上海财经大学",
            "校方查询 + 河南官方增量",
            "校方查询要求四位验证码",
            "河南 34 条 / 84 人",
            AMBER,
            "10272.gaokao.haedu.cn",
        ),
        (
            "河北工业大学",
            "校方官方路径 + 河南官方增量",
            "招生子站当前 WAF 403",
            "河南 23 条 / 73 人",
            AMBER,
            "10080.gaokao.haedu.cn",
        ),
    ]
    positions = [
        (88, 210, 890, 410),
        (950, 210, 1752, 410),
        (88, 435, 890, 635),
        (950, 435, 1752, 635),
        (88, 660, 1752, 860),
    ]
    for (name, source, method, volume, color, domain), box in zip(source_cards, positions):
        x1, y1, x2, y2 = box
        rounded_card(draw, box, CARD, LINE, 22)
        draw.rectangle((x1, y1, x1 + 10, y2), fill=color)
        draw.text((x1 + 30, y1 + 24), name, font=font(27, True), fill=NAVY)
        draw.text((x1 + 30, y1 + 65), source, font=font(20), fill=MUTED)
        draw.text((x1 + 30, y1 + 101), method, font=font(21, True), fill=color)
        draw.text((x1 + 30, y1 + 143), volume, font=font(21), fill=INK)
        draw.text((x2 - 260, y1 + 31), domain, font=font(17), fill="#8292A8")
    rounded_card(draw, (88, 892, 1752, 981), "#E8F1FA", None, 18)
    draw.text(
        (118, 916),
        "证据文件：原始 HTML / 图片 / OCR JSON / 来源 URL / 拉取日志 / SHA-256",
        font=font(24, True),
        fill=NAVY,
    )
    return image


def page_database() -> Image.Image:
    image = standard_page(
        "MySQL 入库与查询证明",
        "DataGrip 实际执行 SELECT 后的结果截图",
        7,
    )
    draw = ImageDraw.Draw(image)
    screenshot = fit_image(DATABASE_SCREENSHOT, (1390, 760))
    x, y = 88, 224
    draw.rounded_rectangle((x + 8, y + 12, x + screenshot.width + 8, y + screenshot.height + 12), radius=18, fill="#D6DFE8")
    draw.rounded_rectangle((x - 2, y - 2, x + screenshot.width + 2, y + screenshot.height + 2), radius=18, fill="white", outline=LINE, width=2)
    image.paste(screenshot, (x, y))

    rounded_card(draw, (1515, 224, 1832, 932), NAVY, None, 24)
    draw.text((1545, 255), "证明要点", font=font(26, True), fill="#7FE1EF")
    points = [
        ("数据库", "admissions"),
        ("统一表", "admission_plan_v2"),
        ("记录", "3047"),
        ("人数", "17447"),
        ("学校", "5"),
        ("原表", "已备份"),
    ]
    y2 = 325
    for label, value in points:
        draw.text((1545, y2), label, font=font(18), fill="#9EB7CC")
        draw_text(
            draw,
            (1545, y2 + 28),
            value,
            font(22, True),
            fill="white",
            max_width=245,
        )
        draw.line((1545, y2 + 82, 1800, y2 + 82), fill="#31516B", width=2)
        y2 += 102
    draw.text(
        (1545, 886),
        "截图非生成图",
        font=font(18, True),
        fill="#7FE1EF",
    )
    return image


def doughnut(
    draw: ImageDraw.ImageDraw,
    center: tuple[int, int],
    radius: int,
    thickness: int,
    color: str,
) -> None:
    box = (
        center[0] - radius,
        center[1] - radius,
        center[0] + radius,
        center[1] + radius,
    )
    draw.arc(box, start=-90, end=270, fill="#E2E9F0", width=thickness)
    draw.arc(box, start=-90, end=270, fill=color, width=thickness)


def page_ocr() -> Image.Image:
    image = standard_page(
        "OCR 95% 专项验收",
        "144 条官方原图样本逐行对照专业、科类与计划数",
        8,
    )
    draw = ImageDraw.Draw(image)
    rounded_card(draw, (88, 210, 760, 720), CARD, LINE, 26)
    doughnut(draw, (390, 445), 150, 30, GREEN)
    draw.text((303, 387), "100%", font=font(58, True), fill=NAVY)
    draw.text((322, 470), "样本准确率", font=font(22), fill=MUTED)
    pill(draw, (262, 600), "95% 阈值通过", GREEN, size=24)
    draw.text(
        (258, 660),
        "正确 144  ·  错误 0",
        font=font(24, True),
        fill=NAVY,
    )

    rounded_card(draw, (795, 210, 1832, 720), CARD, LINE, 26)
    draw.text((830, 246), "分层样本构成", font=font(28, True), fill=NAVY)
    draw.text((830, 316), "中北大学", font=font(22), fill=INK)
    draw.rounded_rectangle((1060, 319, 1700, 351), radius=16, fill="#E6EDF4")
    draw.rounded_rectangle((1060, 319, 1060 + int(640 * 82 / 144), 351), radius=16, fill=BLUE)
    draw.text((1720, 309), "82", font=font(26, True), fill=NAVY)
    draw.text((830, 400), "东北大学", font=font(22), fill=INK)
    draw.rounded_rectangle((1060, 403, 1700, 435), radius=16, fill="#E6EDF4")
    draw.rounded_rectangle((1060, 403, 1060 + int(640 * 62 / 144), 435), radius=16, fill=CYAN)
    draw.text((1720, 393), "62", font=font(26, True), fill=NAVY)
    draw.line((830, 493, 1785, 493), fill=LINE, width=2)
    notes = [
        "200 条跨数据集样本中，144 条具有官方原图裁切，56 条 HTML 记录未混入 OCR 分母。",
        "12 张原图对照总览图完整归档，核验字段包括专业名称、科类和计划人数。",
        "抽样通过不等同于全量证明：中北 26 页汇总差异仍有 1066 条待复核。",
    ]
    y = 525
    for note in notes:
        draw.ellipse((830, y + 7, 846, y + 23), fill=GREEN)
        y = draw_text(
            draw,
            (865, y),
            note,
            font(21),
            fill=MUTED,
            max_width=890,
        ) + 14

    rounded_card(draw, (88, 760, 900, 984), CARD, LINE, 20)
    sample1 = fit_image(ROOT / "results" / "validation" / "crops" / "001.png", (760, 130))
    image.paste(sample1, (130, 810))
    draw.text((130, 942), "样本 001 · 东北大学 · 能源与动力工程 · 物理类 · 3 人", font=font(18, True), fill=NAVY)
    rounded_card(draw, (930, 760, 1742, 984), CARD, LINE, 20)
    sample2 = fit_image(ROOT / "results" / "validation" / "crops" / "002.png", (760, 130))
    image.paste(sample2, (972, 810))
    draw.text((972, 942), "样本 002 · 中北大学 · 市场营销 · 物理类 · 2 人", font=font(18, True), fill=NAVY)
    return image


def page_delivery() -> Image.Image:
    image = standard_page(
        "交付清单与下一步",
        "建议直接提交完整压缩包，并按缺口决定是否继续补齐全国范围",
        9,
    )
    draw = ImageDraw.Draw(image)
    rounded_card(draw, (88, 210, 1090, 952), CARD, LINE, 26)
    draw.text((125, 246), "建议提交的 8 类成果", font=font(30, True), fill=NAVY)
    deliverables = [
        ("01", "五校独立爬虫源码", "nuc.py / sxnu.py / neu.py / sufe.py / hebut.py"),
        ("02", "各校结构化 CSV", "五校单独文件 + combined_candidates.csv"),
        ("03", "官方来源与原始证据", "图片 / HTML / OCR JSON / 日志 / SHA-256"),
        ("04", "MySQL 建表与入库", "admission_plan_v2 · 3047 条 · 17447 人"),
        ("05", "查询 SQL 与真实截图", "DataGrip 实际 SELECT 截图"),
        ("06", "OCR 95% 验收", "144/144 正确 · 12 张对照总览图"),
        ("07", "自动测试与日志", "selftest.py · ALL LOCAL CHECKS PASSED"),
        ("08", "最终说明与交付包", "README / FINAL_REPORT / submission.zip"),
    ]
    y = 320
    for number, title, detail in deliverables:
        draw.ellipse((125, y, 183, y + 58), fill=NAVY)
        draw.text((143, y + 12), number, font=font(16, True), fill="white")
        draw.text((205, y + 2), title, font=font(23, True), fill=NAVY)
        draw_text(
            draw,
            (205, y + 38),
            detail,
            font(18),
            fill=MUTED,
            max_width=770,
        )
        y += 76

    rounded_card(draw, (1125, 210, 1832, 600), "#FFF5E3", "#F2D29A", 26)
    draw.text((1160, 245), "仍需人工介入", font=font(30, True), fill="#8A5A00")
    blockers = [
        "上海财经大学校方查询要求四位验证码。",
        "河北工业大学招生子站当前 WAF 403。",
        "保存两校官方结果 HTML/CSV 后，可继续增量导入。",
    ]
    y = 320
    for blocker in blockers:
        draw.ellipse((1160, y + 8, 1178, y + 26), fill=AMBER)
        y = draw_text(
            draw,
            (1196, y),
            blocker,
            font(22),
            fill="#6E511C",
            max_width=570,
        ) + 28

    rounded_card(draw, (1125, 630, 1832, 952), NAVY, None, 26)
    draw.text((1160, 666), "数据质量边界", font=font(28, True), fill="#7FE1EF")
    draw_text(
        draw,
        (1160, 730),
        "OCR 抽样已达到 95%，但中北大学仍有 26 页汇总差异和 1066 条待复核。"
        "上海财大、河北工大目前只有河南官方增量。",
        font(24),
        fill="white",
        max_width=600,
        spacing=13,
    )
    draw_text(
        draw,
        (1160, 865),
        "建议：阶段验收可提交当前包；若要求五校全国完整，则先完成两校人工官方导出。",
        font(21, True),
        fill="#C9D8E6",
        max_width=600,
    )
    return image


def create_contact_sheet(pages: list[Image.Image]) -> Image.Image:
    thumb_width = 560
    thumb_height = 315
    margin = 28
    gap = 24
    title_height = 90
    canvas = Image.new(
        "RGB",
        (
            margin * 2 + thumb_width * 3 + gap * 2,
            title_height + margin + thumb_height * 3 + gap * 2,
        ),
        BG,
    )
    draw = ImageDraw.Draw(canvas)
    draw.text((margin, 24), "五校招生计划项目交付报告 · 页面总览", font=font(34, True), fill=NAVY)
    for index, page in enumerate(pages):
        row, column = divmod(index, 3)
        x = margin + column * (thumb_width + gap)
        y = title_height + row * (thumb_height + gap)
        thumb = page.resize((thumb_width, thumb_height), Image.Resampling.LANCZOS)
        canvas.paste(thumb, (x, y))
        draw.rounded_rectangle(
            (x, y, x + thumb_width, y + thumb_height),
            radius=12,
            outline="#C7D2DE",
            width=2,
        )
    return canvas


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    PAGES.mkdir(parents=True, exist_ok=True)
    pages = [
        page_cover(),
        page_requirements(),
        page_scorecard(),
        page_architecture(),
        page_results(),
        page_sources(),
        page_database(),
        page_ocr(),
        page_delivery(),
    ]
    for index, page in enumerate(pages, start=1):
        page.save(PAGES / f"{index:02d}.png", "PNG")
    pages[0].save(
        OUTPUT / "五校招生计划项目交付报告_纯图片版.pdf",
        "PDF",
        resolution=144.0,
        save_all=True,
        append_images=pages[1:],
    )
    contact = create_contact_sheet(pages)
    contact.save(OUTPUT / "报告页面总览.png", "PNG")
    print(OUTPUT / "五校招生计划项目交付报告_纯图片版.pdf")
    print(OUTPUT / "报告页面总览.png")
    print("PAGES", len(pages))


if __name__ == "__main__":
    main()
