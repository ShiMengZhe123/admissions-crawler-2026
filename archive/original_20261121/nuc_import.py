
import json
import getpass
from pathlib import Path

import mysql.connector

BASE_DIR = Path(__file__).resolve().parent
OCR_DIR = BASE_DIR / "ocr_results" / "nuc"

if not OCR_DIR.exists():
    raise FileNotFoundError(f"找不到 OCR 目录：{OCR_DIR}")

files = sorted(OCR_DIR.rglob("*_res.json"))

print(f"发现 {len(files)} 个 OCR 原始结果文件")

if not files:
    raise RuntimeError("没有找到 *_res.json 文件")

password = getpass.getpass("请输入 MySQL 密码：")

conn = mysql.connector.connect(
    host="127.0.0.1",
    port=3306,
    user="root",
    password=password,
    database="admissions"
)

cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS nuc_ocr_raw (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    admission_year INT NOT NULL,
    school VARCHAR(100) NOT NULL,
    province VARCHAR(30) NOT NULL,
    image_name VARCHAR(255) NOT NULL,
    box_index INT NOT NULL,
    recognized_text TEXT,
    confidence FLOAT,
    box_json TEXT,
    UNIQUE KEY uniq_image_box
        (province, image_name, box_index)
) CHARACTER SET utf8mb4
""")

sql = """
INSERT INTO nuc_ocr_raw (
    admission_year,
    school,
    province,
    image_name,
    box_index,
    recognized_text,
    confidence,
    box_json
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    recognized_text = VALUES(recognized_text),
    confidence = VALUES(confidence),
    box_json = VALUES(box_json)
"""

total = 0
success_files = 0
failed_files = []

for file in files:
    try:
        province = file.parent.name
        image_name = file.name.replace("_res.json", "")

        data = json.loads(file.read_text(encoding="utf-8"))
        data = data.get("res", data)

        texts = data.get("rec_texts", [])
        scores = data.get("rec_scores", [])
        boxes = data.get("rec_boxes", [])

        if len(texts) != len(scores):
            raise ValueError("文字数量与置信度数量不一致")

        rows = []

        for i, text in enumerate(texts):
            box = boxes[i] if i < len(boxes) else []

            if hasattr(box, "tolist"):
                box = box.tolist()

            rows.append((
                2026,
                "中北大学",
                province,
                image_name,
                i,
                str(text),
                float(scores[i]),
                json.dumps(box, ensure_ascii=False)
            ))

        if rows:
            cursor.executemany(sql, rows)

        conn.commit()
        total += len(rows)
        success_files += 1

        print(f"{province} / {image_name}: {len(rows)} 个文字框")

    except Exception as e:
        conn.rollback()
        failed_files.append((str(file), str(e)))
        print("处理失败：", file, e)

cursor.execute("""
SELECT province, COUNT(*)
FROM nuc_ocr_raw
WHERE admission_year = 2026
GROUP BY province
ORDER BY province
""")

print("\n========== 数据库统计 ==========")

for province, count in cursor.fetchall():
    print(f"{province}: {count} 个文字框")

print("\n成功处理文件：", success_files)
print("本次读取文字框：", total)
print("失败文件：", len(failed_files))

for name, error in failed_files:
    print("失败：", name, error)

cursor.close()
conn.close()

print("\nOCR 原始数据入库流程结束！")