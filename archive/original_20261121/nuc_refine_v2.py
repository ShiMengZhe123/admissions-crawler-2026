# -*- coding: utf-8 -*-
"""Read existing admissions.nuc_ocr_raw. No downloading or OCR."""
import csv, json, re, getpass
from pathlib import Path
from collections import defaultdict
import mysql.connector

FIELDS=['admission_year','school','province','image_name','row_index','college_name','major_name','subject_type','batch_name','planned_count','review_status','review_reason']
OUT=Path(__file__).resolve().parent/'results'/'nuc_v2'
OUT.mkdir(parents=True,exist_ok=True)

def loadbox(r):
    try:
        a,b,c,d=map(float,json.loads(r['box_json']))
        if c<=a or d<=b: return None
        return {'text':re.sub(r'\\s+','',r['recognized_text'] or ''),'x':(a+c)/2,'y':(b+d)/2,'y1':b,'y2':d,'x2':c,'score':float(r['confidence'] or 0),'idx':r['box_index']}
    except (TypeError,ValueError,KeyError):return None

def extract(province,image,boxes):
    w=max(b['x2'] for b in boxes)
    h=max(b['y2'] for b in boxes)
    headers=[b for b in boxes if b['y']<h*.23 and b['text'] in ('学院名称','专业名称','科类','录取批次','计划数','收费标准')]
    top=max([b['y2'] for b in headers] or [h*.09])
    # fixed proportions are provisional, so all rows must be reviewed
    edges=[.085,.255,.445,.555,.650,.722,.815]
    names=['code','college','major','subject','batch','count','fee','other']
    def col(x):
        for i,e in enumerate(edges):
            if x/w<e:return names[i]
        return names[-1]
    anchors=sorted([b for b in boxes if b['y1']>top and col(b['x'])=='count' and re.fullmatch('[1-9][0-9]{0,3}',b['text']) and int(b['text'])<=999],key=lambda b:b['y'])
    uniq=[]
    for b in anchors:
        if uniq and abs(b['y']-uniq[-1]['y'])<3:
            if b['score']>uniq[-1]['score']:uniq[-1]=b
        else:uniq.append(b)
    anchors=uniq
    mids=[(a['y']+b['y'])/2 for a,b in zip(anchors,anchors[1:])]
    rows=[]
    for i,a in enumerate(anchors):
        low=mids[i-1] if i else max(top,a['y']-40)
        high=mids[i] if i<len(mids) else a['y']+40
        parts=defaultdict(list)
        for b in boxes:
            if b['idx']!=a['idx'] and low<=b['y']<high:
                parts[col(b['x'])].append(b)
        def cell(k):
            return ''.join(b['text'] for b in sorted(parts[k],key=lambda z:(z['y'],z['x'])))
        college=cell('college')
        college=re.sub(r'(?<![0-9])[0-9]{2}(?![0-9])','',college)
        major=cell('major')
        subject=cell('subject')
        batch=cell('batch')
        reasons=[]
        if not college:reasons.append('学院为空或合并单元格')
        if len(major)<2 or len(major)>35:reasons.append('专业名称异常')
        if not subject:reasons.append('科类为空')
        if not batch:reasons.append('批次为空')
        if a['score']<.9:reasons.append('计划数字低置信度')
        rows.append(dict(admission_year=2026,school='中北大学',province=province,image_name=image,row_index=i+1,college_name=college,major_name=major,subject_type=subject,batch_name=batch,planned_count=int(a['text']),review_status='待复核',review_reason='；'.join(reasons) if reasons else '需与原图核对'))
    return rows

def save_csv(path,rows,fields):
    with path.open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

def main():
    password=getpass.getpass('MySQL 密码：')
    db=mysql.connector.connect(host='127.0.0.1',port=3306,user='root',password=password,database='admissions',charset='utf8mb4')
    try:
        c=db.cursor(dictionary=True)
        c.execute("SELECT province,image_name,box_index,recognized_text,confidence,box_json FROM nuc_ocr_raw WHERE admission_year=2026 AND school='中北大学' ORDER BY province,image_name,box_index")
        pages=defaultdict(list)
        for r in c:
            b=loadbox(r)
            if b:pages[(r['province'],r['image_name'])].append(b)
        c.close()
        if not pages:raise RuntimeError('没有可用的历史 OCR 坐标')
        rows=[]
        for (province,image),boxes in sorted(pages.items()):
            chunk=extract(province,image,boxes)
            rows.extend(chunk)
            print(province,image,len(chunk),'条候选')
        save_csv(OUT/'nuc_candidates_v2.csv',rows,FIELDS)
        save_csv(OUT/'nuc_priority_review_v2.csv',[r for r in rows if r['review_reason']!='需与原图核对'],FIELDS)
        c=db.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS nuc_plan_v2(
          id BIGINT AUTO_INCREMENT PRIMARY KEY,
          admission_year INT,school VARCHAR(100),province VARCHAR(50),
          image_name VARCHAR(120),row_index INT,college_name TEXT,major_name TEXT,
          subject_type TEXT,batch_name TEXT,planned_count INT,
          review_status VARCHAR(20),review_reason TEXT,
          UNIQUE KEY unique_row(admission_year,school,province,image_name,row_index)
        ) CHARACTER SET utf8mb4""")
        q="""INSERT INTO nuc_plan_v2(admission_year,school,province,image_name,row_index,college_name,major_name,subject_type,batch_name,planned_count,review_status,review_reason)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE college_name=VALUES(college_name),major_name=VALUES(major_name),subject_type=VALUES(subject_type),batch_name=VALUES(batch_name),planned_count=VALUES(planned_count),review_status=VALUES(review_status),review_reason=VALUES(review_reason)"""
        if rows:c.executemany(q,[tuple(r[k] for k in FIELDS) for r in rows])
        db.commit()
        c.close()
        print('完成：',len(pages),'张图片，',len(rows),'条待复核候选。')
        print('新表：admissions.nuc_plan_v2；文件：',OUT)
        print('原表及原 OCR 数据不变；未验证 95% 准确率。')
    finally:db.close()
if __name__=='__main__':main()
