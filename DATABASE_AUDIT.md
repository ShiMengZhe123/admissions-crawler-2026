# MySQL 数据库审计与入库结果

审计时间：2026-11-22

## 连接

- 地址：`127.0.0.1:3306`
- MySQL：8.0.41
- 当前用户：`root@localhost`
- 数据库：`admissions`
- 密码仅从 `.env.local` 读取，未写入源码或日志。

## 原有表

| 表 | 行数 | 说明 |
|---|---:|---|
| `admission_plan` | 758 | 山西师大；计划合计 5100 |
| `nuc_ocr_raw` | 16153 | 中北 OCR 原始文本框 |
| `nuc_ocr_validation` | 0 | 未进行真实人工核验 |
| `nuc_plan_parsed` | 1372 | 旧候选，含结构问题 |
| `nuc_plan_v2` | 1323 | 旧候选，仍有 29 条汇总/异常行 |

## 原正式表检查

- `admission_plan` 只有 2026 年山西师大 758 条。
- 分省 29 个（含“不分省”）。
- 计划合计 5100 人。
- 空专业、空省份、空计划类别、空来源、非法人数均为 0。
- 5 条空科类来自官网“不分省”计划类别。

## 安全备份

写入前创建：

`admission_plan_backup_20261122_091849`

备份行数：758。

原 `admission_plan` 表未被删除、清空或覆盖。

## 统一表 `admission_plan_v2`

实际入库汇总：

| 学校 | 行数 | 计划人数 | 数据状态 |
|---|---:|---:|---|
| 中北大学 | 1486 | 7594 | 419 自动校验、1066 待复核、1 人工校正待复核 |
| 山西师范大学 | 758 | 5100 | HTML 全量校验通过 |
| 东北大学 | 746 | 4596 | 自动结构校验通过 |
| 上海财经大学 | 34 | 84 | 河南官方页面校验通过 |
| 河北工业大学 | 23 | 73 | 河南官方页面校验通过 |
| **合计** | **3047** | **17447** | 五校官方数据已入库 |

## 老板目标表

`gaokao_2026_enrollment` 已按老板 DDL 建立并完成迁移：

- 3047 条，17447 人，5 所学校，32 个地区维度；
- 第一次迁移新增 3047 条；
- 第二次迁移新增 0 条、跳过 3047 条；
- 完全重复业务行为 0，映射冲突为 0；
- `UNIV_ID`、`ENROLLMENT_ID` 均为 NULL，待业务方确认；
- 固定操作字段全部符合要求，`OPERATE_TIME` 均符合时间格式。

目标表无主键，使用辅助账本
`gaokao_2026_enrollment_import_ledger` 实现幂等去重。旧
`admission_plan_v2` 和 `admission_plan` 均未删除或清空。

完整结果见
`results/gaokao_2026_enrollment/final_verification.json`。

数据库检查：

- 空专业名称：0。
- 空来源 URL：0。
- 非法计划人数：0。
- 业务键重复：0。

## 导出文件

- `results/database/school_summary.csv`
- `results/database/province_summary.csv`
- `results/database/null_check.csv`
- `results/database/duplicate_check.csv`
- `results/database/review_summary.csv`
- `results/database/database_audit.json`
- `results/database/existing_data_audit.json`
- `results/database/datagrip_query.sql`
- `results/database/datagrip_query_result.png`

DataGrip 截图是在实际本地 MySQL 连接中执行汇总 `SELECT` 后截取，结果
显示五校记录、计划人数、省级覆盖数和合计 3047 / 17447 / 5。

## 尚待补充

- 上海财经大学：河南已入库，其他省份仍待补。
- 河北工业大学：河南已入库，其他省份仍待补。

未使用第三方预测数据或其他年份数据填补缺口。
