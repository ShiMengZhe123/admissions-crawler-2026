# -*- coding: utf-8 -*-
"""中北大学 OCR 后处理。仅读取已保存的 MySQL OCR 数据，不重爬、不重识别。
运行: .\.venv\Scripts\python.exe nuc_finish.py
输出: admissions.nuc_plan_parsed 和 nuc_output 中的 CSV。
警告: OCR 表格自动拼行存在误差，输出全部标注为“待复核”。
"""
import csv
import getpass
import json
import re
from pathlib import Path
from collections import defaultdict
import mysql.connector

BASE = Path(__file__).resolve().parent
OUTPUT = BASE / "nuc_output"
OUTPUT.mkdir(exist_ok=True)

HEADERS = {
    "college": ("学院名称", "学院名"),
    "major": ("专业名称", "专业名"),
    "subject": ("科类",),
    "batch": ("录取批次", "批次"),
    "count": ("计划数", "计划人数", "招生计划"),
    "fee": ("收费标准", "学费"),
}
FIELDS = ("college", "major", "subject", "batch", "count", "fee")
FRACTIONS = {"college": .17, "major": .36, "subject": .50,
             "batch": .60, "count": .68, "fee": .75}
OUTPUT_FIELDS = ["admission_year","school","province","image_name",
                 "row_index","college_name","major_name","subject_type",
                 "batch_name","planned_count","fee_text",
                 "review_status","review_reason"]

def norm(s):
    return re.sub(r"\s+", "", str(s or ""))

def header(t):
    t = norm(t)
    for c, names in HEADERS.items():
        if t in names:
            return c
    if t == "计划":
        return "count"
    return None

def to_box(rec):
    try:
        b = json.loads(rec["box_json"])
        x1,y1,x2,y2 = map(float,b)
        if x2 <= x1 or y2 <= y1: return None
        return dict(text=norm(rec["recognized_text"]),x1=x1,y1=y1,
                    x2=x2,y2=y2,x=(x1+x2)/2,y=(y1+y2)/2,
                    confidence=float(rec["confidence"] or 0),
                    index=int(rec["box_index"]))
    except (ValueError,TypeError,KeyError):
        return None

def parse_page(province, image, boxes):
    width=max(b["x2"] for b in boxes)
    height=max(b["y2"] for b in boxes)
    titles=defaultdict(list)
    for b in boxes:
        c=header(b["text"])
        if c and b["y"]<height*.20:
            titles[c].append(b)
    found={}
    for col, items in titles.items():
        found[col]=min(items,key=lambda z:abs(z["x"]/width-FRACTIONS[col]))["x"]
    reliable=("major" in found and "count" in found)
    centers={c:found.get(c,width*FRACTIONS[c]) for c in FIELDS}
    if any(centers[a]>=centers[b] for a,b in zip(FIELDS,FIELDS[1:])):
        centers={c:width*FRACTIONS[c] for c in FIELDS}
        reliable=False
    cuts=[(centers[a]+centers[b])/2 for a,b in zip(FIELDS,FIELDS[1:])]
    def column(x):
        for n,cut in enumerate(cuts):
            if x<cut:return FIELDS[n]
        return FIELDS[-1]
    # 山西省截图计划数列约位于图片宽度的 65%-72%。
    # 若无法识别页眉，不能将回退布局视为准确。
    lower,upper=(cuts[3],cuts[4]) if reliable else (width*.65,width*.725)
    title_bottom=max([b["y2"] for b in boxes if header(b["text"])] or [height*.08])
    anchors=sorted([
        b for b in boxes if b["y1"]>title_bottom+2
        and lower<=b["x"]<=upper
        and re.fullmatch(r"\d{1,3}",b["text"])
        and 0<int(b["text"])<=999
    ],key=lambda b:b["y"])
    unique=[]
    for a in anchors:
        if unique and abs(a["y"]-unique[-1]["y"])<3:
            if a["confidence"]>unique[-1]["confidence"]:unique[-1]=a
        else:unique.append(a)
    anchors=unique
    mids=[(a["y"]+b["y"])/2 for a,b in zip(anchors,anchors[1:])]
    result=[]
    for i,a in enumerate(anchors):
        top=mids[i-1] if i else max(title_bottom,a["y"]-35)
        bottom=mids[i] if i<len(mids) else a["y"]+35
        cells=defaultdict(list)
        for b in boxes:
            if b["index"]==a["index"] or not top<=b["y"]<bottom:
                continue
            if header(b["text"]) and b["y"]<title_bottom+10:
                continue
            cells[column(b["x"])].append(b)
        def joined(col):
            return "".join(b["text"] for b in sorted(cells[col],key=lambda b:(b["y"],b["x"])))
        college,major,subject,batch,fee=[joined(c) for c in ("college","major","subject","batch","fee")]
        problems=[]
        if not reliable:problems.append("表头定位不完整")
        if len(major)<2 or major in ("专业","专业名称","合计","小计","总计"):problems.append("专业名称异常")
        if not college:problems.append("学院可能是合并单元格")
        if not subject:problems.append("科类缺失")
        if a["confidence"]<.9:problems.append("计划人数置信度偏低")
        if len(major)>80:problems.append("专业字段疑似错行")
        result.append(dict(admission_year=2026,school="中北大学",
            province=province,image_name=image,row_index=i+1,
            college_name=college,major_name=major,subject_type=subject,
            batch_name=batch,planned_count=int(a["text"]),fee_text=fee,
            review_status="待复核",
            review_reason="；".join(problems) if problems else "需与原图逐行核对"))
    return result, reliable

def write_csv(path, rows, fields):
    with path.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

def main():
    pwd=getpass.getpass("请输入 MySQL 密码：")
    cn=mysql.connector.connect(host="127.0.0.1",port=3306,user="root",
                                password=pwd,database="admissions",charset="utf8mb4")
    try:
        cur=cn.cursor(dictionary=True)
        cur.execute("""SELECT province,image_name,box_index,recognized_text,
                              confidence,box_json
                       FROM nuc_ocr_raw
                       WHERE admission_year=2026 AND school='中北大学'
                       ORDER BY province,image_name,box_index""")
        pages=defaultdict(list)
        total=invalid=0
        for rec in cur:
            total+=1
            b=to_box(rec)
            if b:pages[rec["province"],rec["image_name"]].append(b)
            else:invalid+=1
        cur.close()
        if not pages:raise RuntimeError("找不到有效的已入库 OCR 坐标，请检查 nuc_ocr_raw。")
        rows=[]
        page_issues=[]
        for (province,image),boxes in sorted(pages.items()):
            parsed, reliable=parse_page(province,image,boxes)
            rows.extend(parsed)
            if not reliable or not parsed:
                page_issues.append(dict(province=province,image_name=image,
                   problem="表头定位不完整" if not reliable else "未检测到计划人数"))
            print(f"{province} / {image}: {len(parsed)} 条候选记录")
        write_csv(OUTPUT/"nuc_candidates.csv",rows,OUTPUT_FIELDS)
        write_csv(OUTPUT/"nuc_page_issues.csv",page_issues,["province","image_name","problem"])

        cur=cn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS nuc_plan_parsed(
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            admission_year INT NOT NULL,
            school VARCHAR(100) NOT NULL,
            province VARCHAR(50) NOT NULL,
            image_name VARCHAR(120) NOT NULL,
            row_index INT NOT NULL,
            college_name TEXT,
            major_name TEXT,
            subject_type TEXT,
            batch_name TEXT,
            planned_count INT,
            fee_text TEXT,
            review_status VARCHAR(20) NOT NULL,
            review_reason TEXT,
            UNIQUE KEY uniq_candidate(admission_year,school,province,image_name,row_index)
        ) CHARACTER SET utf8mb4""")
        query="""INSERT INTO nuc_plan_parsed
            (admission_year,school,province,image_name,row_index,college_name,
            major_name,subject_type,batch_name,planned_count,fee_text,
            review_status,review_reason)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE
            college_name=VALUES(college_name),major_name=VALUES(major_name),
            subject_type=VALUES(subject_type),batch_name=VALUES(batch_name),
            planned_count=VALUES(planned_count),fee_text=VALUES(fee_text),
            review_status=VALUES(review_status),review_reason=VALUES(review_reason)"""
        if rows:cur.executemany(query,[tuple(r[k] for k in OUTPUT_FIELDS) for r in rows])
        cn.commit()
        cur.close()
        print(f"\n完成：读取 {total} 个文字框；无效坐标 {invalid} 个；"
              f"处理 {len(pages)} 张图片；生成 {len(rows)} 条待复核候选记录。")
        print("结构化表：admissions.nuc_plan_parsed")
        print("CSV目录：",OUTPUT)
        print("重要：候选数据尚未逐行核对，不代表准确率达到95%。")
    finally:
        cn.close()

if __name__=="__main__":
    main()
