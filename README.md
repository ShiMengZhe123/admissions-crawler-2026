# 2026 五校高校招生计划采集与 OCR

本项目采集并校验以下五所高校的 2026 年本科招生计划：

- 中北大学
- 山西师范大学
- 东北大学
- 上海财经大学
- 河北工业大学

项目保留官方来源、结构化 CSV、SQL、核验报告和验收截图。仓库不提交
虚拟环境、MySQL 密码、本地数据库备份以及体积较大的原始图片；原始图片
可由各校脚本重新下载。

## 当前真实状态

| 学校 | 官方来源 | 当前状态 |
|---|---|---|
| 中北大学 | 学校招生信息网 42 张官方图片 | 31 省，1486 条候选，7594 人；OCR 抽样通过，汇总差异待复核 |
| 山西师范大学 | 学校官方 HTML 主表 | 758 条，5100 人；官网合计和样例校验通过 |
| 东北大学 | 学校官方 31 张高清图片 | 31 省，746 条候选，4596 人；OCR 抽样通过 |
| 上海财经大学 | 河南阳光高考官方增量 | 河南 34 条/84 人；其余省份仍待补 |
| 河北工业大学 | 河南阳光高考官方增量 | 河南 23 条/73 人；其余省份仍待补 |

MySQL 已完成备份与五校官方数据入库：`admission_plan_v2` 共 3047 条，
计划合计 17447 人。原 `admission_plan` 未修改。

OCR 专用样本 144 条已逐行对照原图核验：144 条正确、0 条错误，
抽样准确率 100%，达到 95% 阈值。DataGrip 实际查询截图保存在
`results/database/datagrip_query_result.png`。

## 验收截图

- [MySQL/DataGrip 五校查询结果](docs/screenshots/mysql-query-result.png)
- [OCR 原图抽检总览](docs/screenshots/ocr-validation-sample.png)
- [项目交付报告总览](docs/screenshots/report-overview.png)

## 环境

- Windows 11
- Python 3.10.6
- 虚拟环境：`.venv`
- PaddlePaddle 3.2.0
- PaddleOCR 3.7.0
- MySQL 8.0

安装依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

项目优先使用现有 `.venv`，无需重建虚拟环境。

## 数据库配置

不要把密码写入源码或提交到版本库。任选一种方式：

```powershell
$env:MYSQL_PASSWORD = "你的密码"
```

或在项目根目录创建已被 `.gitignore` 排除的 `.env.local`：

```text
MYSQL_PASSWORD=你的密码
```

可选配置：

```text
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_DATABASE=admissions
```

未设置密码时，数据库脚本会安全地交互式询问，不会打印密码。

## 常用命令

五所学校分别对应以下独立脚本：

| 学校 | 脚本 |
|---|---|
| 中北大学 | `nuc.py` |
| 山西师范大学 | `sxnu.py` |
| 东北大学 | `neu.py` |
| 上海财经大学 | `sufe.py` |
| 河北工业大学 | `hebut.py` |

本地完整自检：

```powershell
.\.venv\Scripts\python.exe selftest.py
```

### 中北大学

默认只读取已有图片和 OCR：

```powershell
.\.venv\Scripts\python.exe nuc.py
```

仅增量下载和识别缺失图片：

```powershell
.\.venv\Scripts\python.exe nuc.py --crawl
```

解析后幂等写库：

```powershell
.\.venv\Scripts\python.exe nuc.py --write-db
```

### 山西师范大学

```powershell
.\.venv\Scripts\python.exe sxnu.py --check
.\.venv\Scripts\python.exe sxnu.py --write-db
```

### 东北大学

```powershell
.\.venv\Scripts\python.exe neu.py --download-only
.\.venv\Scripts\python.exe neu.py --ocr-only
.\.venv\Scripts\python.exe neu.py
.\.venv\Scripts\python.exe neu.py --write-db
```

### 上海财经大学

官方查询入口：

<https://zs.sufe.edu.cn/zsjh/list.htm>

查询要求人工完成四位数字验证码。完成校方查询后，将结果表保存为
HTML/CSV：

```powershell
.\.venv\Scripts\python.exe sufe.py --check-source
.\.venv\Scripts\python.exe sufe.py --input .\sufe_official_result.html
.\.venv\Scripts\python.exe sufe.py --input .\sufe_official_result.csv --write-db
```

已实现河南省级官方增量：

```powershell
.\.venv\Scripts\python.exe sufe.py --henan-official --write-db
```

### 河北工业大学

```powershell
.\.venv\Scripts\python.exe hebut.py --check-source
.\.venv\Scripts\python.exe hebut.py --input .\hebut_official_result.html
.\.venv\Scripts\python.exe hebut.py --input .\hebut_official_result.csv --write-db
```

河南省级官方增量：

```powershell
.\.venv\Scripts\python.exe hebut.py --henan-official --write-db
```

### 数据库审计与查询

```powershell
.\.venv\Scripts\python.exe db_tools.py audit
.\.venv\Scripts\python.exe db_tools.py migrate
.\.venv\Scripts\python.exe db_tools.py backup admission_plan
.\.venv\Scripts\python.exe db_tools.py import-csv .\results\nuc\nuc_candidates_final.csv
.\.venv\Scripts\python.exe db_tools.py queries
```

`migrate` 只创建缺失的 `admission_plan_v2`，不删除或覆盖旧
`admission_plan`。修改旧正式数据前必须先运行 `backup`。

查询 SQL 位于 `submission/sql/queries.sql`，五校汇总也可以使用：

```sql
SELECT school, COUNT(*) AS records, SUM(planned_count) AS planned_total
FROM admissions.admission_plan_v2
WHERE admission_year = 2026
GROUP BY school;
```

## OCR 核验

生成 200 条分层抽样和原图行裁切：

```powershell
.\.venv\Scripts\python.exe ocr_validation.py --sample 200
```

输出：

- `results/validation/ocr_validation_sample_200.csv`
- `results/validation/crops/`

OCR 专用样本已过滤 HTML 记录并保留原图裁切，逐行核验后统计：

```powershell
.\.venv\Scripts\python.exe ocr_validation.py --finalize results\validation\ocr_validation_sample_144.csv
```

程序不会把未人工核对的记录自动算作正确，也不会在样本未全部核验时
宣称达到 95%。

## 主要输出

- `results/nuc/nuc_candidates_final.csv`
- `results/nuc/nuc_province_summary.csv`
- `results/sxnu/sxnu_candidates.csv`
- `results/neu/neu_candidates.csv`
- `results/sufe/`
- `results/hebut/`
- `results/database/`
- `results/validation/`
- `PROJECT_AUDIT.md`

## 原始数据保护

原始脚本备份在 `archive/original_20261121/`。原始 42 张中北图片和
84 个 OCR 文件均保留。新增的 `_count_reocr` 仅是计划数列的旁路结果，
用于修正原 OCR 数字误识别，不覆盖原始文件。

GitHub 仓库为源码与验收快照，不包含本地 MySQL 密码、`.env.local`、
虚拟环境、缓存和数据库备份。
