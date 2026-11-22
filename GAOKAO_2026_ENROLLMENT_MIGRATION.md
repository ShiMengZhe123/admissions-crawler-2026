# gaokao_2026_enrollment 迁移与验收

## 目标

按老板提供的字段结构建立 `gaokao_2026_enrollment`，将五校现有
2026 招生计划迁入，同时保留旧表 `admission_plan_v2`。

## 字段映射

| 现有字段 | 目标字段 |
|---|---|
| `admission_year` | `GAOKAO_DATE` |
| `school` | `UNIV_NAME` |
| `province` | `REGION_NAME` |
| `subject_type` | `BRANCH_NAME` |
| `batch_name` | `ADMISSIONBATCH_NAME` |
| `major_name` | `SPECIALTY_NAME` |
| `planned_count` | `ENROLLMENT_NUM` |
| `plan_type` + `selection_subject` | `ENROLLMENT_DESC` |

`ENROLLMENT_DESC` 格式为：

```text
招生类型：…，选课要求：…
```

只拼接源数据中存在的字段。

固定字段：

- `OPERATE_ID = 'GK010101000000000000'`
- `OPERATE_FLAG = '1'`
- `OPERATE_IP = '127.0.0.1'`
- `OPERATE_TIME`：实际入库时间，格式 `YYYY-MM-DD HH:MM:SS`

待确认字段：

- `UNIV_ID`：NULL，项目中没有覆盖五校的可靠编号映射。
- `ENROLLMENT_ID`：NULL，项目中没有覆盖五校的可靠招生计划编号规则。

## 表结构

- 目标表按照老板 DDL 创建。
- 表名、字段、长度、字符集和索引保留。
- 仅增加 `IF NOT EXISTS` 保证可重复执行。
- MySQL 8.0 会把 `utf8` 显示为 `utf8mb3`，把 `int(50)` 规范显示为 `int`；
  这是 MySQL 的同义类型规范化，并非本地修改。
- 旧表 `admission_plan_v2` 未修改。

## 无主键表的幂等方案

目标表没有主键和唯一键，增加独立辅助表：

`gaokao_2026_enrollment_import_ledger`

导入时：

1. 用 MySQL `GET_LOCK` 串行化导入；
2. 对目标业务字段生成 `TARGET_KEY_HASH`；
3. 如果账本已存在则跳过；
4. 如果目标表已有同一业务行则跳过并补记账本；
5. 目标数据和账本在同一事务写入；
6. 不同源记录映射成相同目标键时，不自动合并，写入冲突 CSV。

## 执行方式

```powershell
cd D:\PycharmProjects\PythonProject2

.\.venv\Scripts\python.exe migrate_gaokao_2026.py --run-number 1 --source table
.\.venv\Scripts\python.exe migrate_gaokao_2026.py --run-number 2 --source table
.\.venv\Scripts\python.exe verify_gaokao_2026.py
```

五校独立脚本的 `--write-db` 已统一调用
`gaokao_enrollment.write_gaokao_records()`：

```powershell
.\.venv\Scripts\python.exe nuc.py --write-db
.\.venv\Scripts\python.exe sxnu.py --write-db
.\.venv\Scripts\python.exe neu.py --write-db
.\.venv\Scripts\python.exe sufe.py --henan-official --write-db
.\.venv\Scripts\python.exe hebut.py --henan-official --write-db
```

## 两次迁移实际结果

| 次数 | 新增 | 跳过已有 | 账本新增 | 目标总行数 | 目标计划人数 |
|---|---:|---:|---:|---:|---:|
| 第 1 次 | 3047 | 0 | 3047 | 3047 | 17447 |
| 第 2 次 | 0 | 3047 | 0 | 3047 | 17447 |

完全重复目标业务行：0。

映射冲突：0。

## 逐校核对

| 学校 | 记录数 | 计划人数 | 覆盖地区数 |
|---|---:|---:|---:|
| 中北大学 | 1486 | 7594 | 31 |
| 山西师范大学 | 758 | 5100 | 29 |
| 东北大学 | 746 | 4596 | 31 |
| 上海财经大学 | 34 | 84 | 1 |
| 河北工业大学 | 23 | 73 | 1 |
| **合计** | **3047** | **17447** | **32** |

上海财经大学和河北工业大学仅覆盖河南省，其他省份待补齐。

## 缺失字段

| 数据项 | 数量 | 处理 |
|---|---:|---|
| 科类 `BRANCH_NAME` | 5 | 按源数据留空 |
| 录取批次 `ADMISSIONBATCH_NAME` | 1534 | 按源数据留空 |
| 招生类型 `plan_type` | 746 | `ENROLLMENT_DESC` 不写招生类型 |
| 选课要求 `selection_subject` | 800 | `ENROLLMENT_DESC` 不写选课要求 |

`ENROLLMENT_DESC` 最终空值：0。

## DataGrip

打开：

`submission/sql/gaokao_2026_enrollment_datagrip.sql`

建议截图：

1. 五校汇总；
2. 各校省份覆盖；
3. 招生明细；
4. 完全重复行检查。

## 结果文件

- `results/gaokao_2026_enrollment/run_1.json`
- `results/gaokao_2026_enrollment/run_2.json`
- `results/gaokao_2026_enrollment/final_verification.json`
- `results/gaokao_2026_enrollment/final_school_summary.csv`
- `results/gaokao_2026_enrollment/final_province_coverage.csv`
- `results/gaokao_2026_enrollment/conflicts_run_1.csv`
- `results/gaokao_2026_enrollment/conflicts_run_2.csv`
