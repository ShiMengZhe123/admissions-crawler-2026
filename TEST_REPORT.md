# 自动测试与验收报告

执行时间：2026-11-22

## 已实际执行

### Python 语法

- 所有顶层 `.py` 文件可编译。
- 新增脚本：
  - `admissions_common.py`
  - `nuc.py`
  - `nuc_reocr_counts.py`
  - `sxnu.py`
  - `neu.py`
  - `neu_ocr_worker.py`
  - `sufe.py`
  - `hebut.py`
  - `provincial_henan.py`
  - `db_tools.py`
  - `db_connection_check.py`
  - `db_data_audit.py`
  - `ocr_validation.py`
  - `quality_report.py`
  - `selftest.py`

### 依赖导入

实际导入成功：

- BeautifulSoup4 4.15.0
- lxml 6.1.3
- mysql-connector-python 26.10.0
- NumPy 2.2.6
- PaddlePaddle 3.2.0
- PaddleOCR 3.7.0
- pandas 2.3.3
- Pillow 12.1.0
- requests 2.34.2

### 山西师范大学

实际执行：

```powershell
.\.venv\Scripts\python.exe sxnu.py --check
```

结果：

- 758 条明细；
- 5100 人；
- 分省合计与官网总计一致；
- 官网样例“经济学 62 人”一致。

### 中北大学

实际执行：

```powershell
.\.venv\Scripts\python.exe nuc.py
```

结果：

- 31 个省级地区；
- 1486 条候选；
- 计划合计 7594 人；
- 空专业名称 0；
- 明显重复业务键 0；
- 新疆 5 个表段恢复为 54 条/88 人；
- 图片和原 OCR 完整性测试通过。

### 上海财大/河北工大导入器

使用合成最小表格测试：

- 上海财大 HTML/CSV 字段映射通过；
- 河北工大 HTML/CSV 字段映射通过；
- 不代表两校真实数据已经取得。

### 网络安全声明检查

- 源码中未发现硬编码数据库密码。
- `.env.local` 已加入 `.gitignore`。
- 没有自动破解验证码或重置 MySQL。

## MySQL 实际测试

`.env.local` 配置完成后实际执行：

- `db_connection_check.py`：连接成功，MySQL 8.0.41；
- `db_tools.py audit`：读取 5 张现有表及字段结构；
- `db_data_audit.py`：只读核验旧数据；
- `db_tools.py backup admission_plan`：创建 758 行备份
  `admission_plan_backup_20261122_091849`；
- `db_tools.py migrate`：确保 `admission_plan_v2` 和
  `gaokao_2026_enrollment` 均存在；
- 三校完整数据脚本和两校河南官方增量脚本均 `--write-db` 幂等写入成功；
- `db_tools.py queries`：数据库端实际汇总、空值和重复检查成功。

数据库结果：

- 统一表总行数 3047；
- 计划总人数 17447；
- 空专业名称 0；
- 空来源 0；
- 非法计划人数 0；
- 明显重复业务键 0。

### 老板目标表迁移

- 首次迁移：新增 3047 条、17447 人；
- 第二次迁移：新增 0 条、跳过 3047 条；
- 目标表最终：3047 条、17447 人、5 所学校、32 个地区维度；
- 完全重复目标业务行 0；
- 映射冲突 0；
- `OPERATE_ID`、`OPERATE_FLAG`、`OPERATE_IP` 和
  `OPERATE_TIME` 全部通过检查；
- 五校独立脚本的 `--write-db` 均连续执行成功，第二次均新增 0 条。

老板目标表的 DataGrip 查询文件为
`submission/sql/gaokao_2026_enrollment_datagrip.sql`，包含五校汇总、
各校省份覆盖、招生明细和重复行检查。

## 数据源剩余状态

### 东北大学完整数据

31 张官方图片已下载，31 省 OCR 和解析完成：

- 北京 12 条/36 人；
- 上海 4 条/10 人；
- 云南 22 条/127 人。

完整结果：31 省、746 条、计划合计 4596 人，空专业/空科类/空来源
和明显重复业务键均为 0。

### 上海财经大学

校方查询验证码阻止无人值守自动化，未绕过。河南阳光高考官方页面已取得
34 条/84 人，页面声明总数与解析数一致。

### 河北工业大学

校方招生子站返回 403。河南阳光高考官方页面已取得 23 条/73 人，
页面声明总数与解析数一致。

## OCR 95% 验收

实际执行：

- 200 条跨数据集分层样本；
- 过滤出有官方原图裁切的 OCR 专用样本 144 条；
- 中北 82 条、东北大学 62 条；
- 逐行对照专业、科类和计划数；
- 正确 144 条，错误 0 条；
- 准确率 100%，95% 样本阈值通过。

统计文件：

- `results/validation/ocr_validation_sample_144.csv`
- `results/validation/ocr_validation_result.json`
- `results/validation/contact_sheets/`（12 张对照总览图）

该结论是抽样验收。中北 26 页汇总差异和 1066 条待复核记录仍保留，
不能据此宣称全量数据全部核验完成。
